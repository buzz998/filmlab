"""冲洗照片：把 RAW / JPG 用 spektrafilm 引擎模拟成胶片 + 相纸的效果。

用法:
  python develop.py 输入文件或文件夹 输出文件夹 [--film kodak_portra_400] [--paper kodak_portra_endura]
                   [--ev 0] [--format 35] [--maxside 3000]
"""
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path
import numpy as np

RAW_EXT = {'.arw', '.cr2', '.cr3', '.nef', '.dng', '.raf', '.orf', '.rw2'}
IMG_EXT = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.heic'}


def load(path, maxside):
    from PIL import Image
    ext = path.suffix.lower()
    if ext in RAW_EXT:
        from spektrafilm.utils.raw_file_processor import load_and_process_raw_file
        img = load_and_process_raw_file(str(path), white_balance='as_shot',
                                        output_colorspace='ProPhoto RGB')
        space, decode = 'ProPhoto RGB', False
    else:
        if ext == '.heic':
            from pillow_heif import register_heif_opener
            register_heif_opener()
        from PIL import ImageOps
        im = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
        img = np.asarray(im).astype(np.float32) / 255.0
        space, decode = 'sRGB', True
    h, w = img.shape[:2]
    scale = min(1.0, maxside / max(h, w))
    if scale < 1.0:
        from skimage.transform import resize
        img = resize(img, (int(h * scale), int(w * scale)), anti_aliasing=True).astype(np.float32)
    return img, space, decode


BORDER_STYLE, DATE, MIX = None, False, 1.0


def _date_text(src):
    """从照片的拍摄时间生成老相机那种日期：'26 11 05"""
    try:
        from PIL import Image
        t = Image.open(src).getexif().get(306) or ''
        y, m, d = t[:10].split(':')
        return f"'{y[2:]} {int(m)} {int(d):02d}"
    except Exception:
        return None


TARGET = 0.49      # 成片亮度中位数的目标，按调好的样片校准
SLOPE = 0.84       # 亮度大约和 相纸曝光^-0.84 成正比


def _params(film, paper, space, decode, ev, fmt, print_exp, y_shift, m_shift, auto_exp):
    from spektrafilm import init_params
    p = init_params(film_profile=film, print_profile=paper)
    p.io.input_color_space = space
    p.io.input_cctf_decoding = decode
    p.settings.use_enlarger_lut = True
    p.settings.use_scanner_lut = True
    p.film_render.grain.sublayers_active = True
    p.camera.auto_exposure = auto_exp
    p.camera.exposure_compensation_ev = ev
    p.camera.film_format_mm = fmt
    p.enlarger.print_exposure = print_exp
    p.enlarger.y_filter_shift = y_shift
    p.enlarger.m_filter_shift = m_shift
    return p


def auto_print_exposure(img, args, brighten=0.0):
    """用小图试冲两三次，找到让成片亮度中位数接近 TARGET 的相纸曝光。
    brighten: 想整体再亮/暗一点就给正/负数（单位约等于档）。"""
    from spektrafilm import simulate
    from skimage.transform import resize
    h, w = img.shape[:2]
    s = 500 / max(h, w)
    small = resize(img, (max(8, int(h * s)), max(8, int(w * s))), anti_aliasing=True).astype(np.float32)
    target = min(0.75, TARGET * 2 ** (brighten * 0.5))
    pe = 1.0
    for _ in range(3):
        out = np.clip(simulate(small, _params(*args[:6], pe, *args[6:])), 0, 1)
        lum = float(np.median(out @ np.array([0.2126, 0.7152, 0.0722])))
        if abs(lum - target) < 0.02:
            break
        pe = float(np.clip(pe * (max(lum, 1e-3) / target) ** (1 / SLOPE), 0.1, 6.0))
    return pe


FACE_TARGET = 0.50   # 遮挡后人脸亮度中位数的目标
DODGE_STRENGTH = 1.0  # 遮挡力度，0.5 就是减半
MAX_DODGE = 0.45     # 人脸最多少给这么多相纸曝光（0.45 ≈ 一档多一点）


YUNET = Path(__file__).with_name('models') / 'face_detection_yunet_2023mar.onnx'


def find_faces(img, decode):
    """在原图上找人脸（OpenCV 的 YuNet 模型），返回 [(x, y, w, h), ...]。
    背景路人的小脸不管：只留不小于最大那张脸一半的。"""
    import cv2
    a = np.clip(img, 0, 1)
    if not decode:                     # RAW 读进来是线性的，转成看着正常的亮度再找
        a = a ** (1 / 2.2)
    bgr = np.ascontiguousarray((a * 255).astype(np.uint8)[..., ::-1])
    h, w = bgr.shape[:2]
    s = min(1.0, 1600 / max(h, w))     # 太大的图先缩小再找，快很多
    small = cv2.resize(bgr, (int(w * s), int(h * s))) if s < 1 else bgr
    det = cv2.FaceDetectorYN.create(str(YUNET), '', (small.shape[1], small.shape[0]), 0.7)
    _, r = det.detect(small)
    if r is None:
        return []
    faces = [tuple(int(v / s) for v in f[:4]) for f in r]
    big = max(f[2] for f in faces)
    return [f for f in faces if f[2] >= big * 0.5]


def face_mask(shape, faces):
    """人脸周围一个柔和的椭圆，包住头发和脖子，边缘慢慢过渡，像冲印师傅手里晃动的遮挡片。"""
    import cv2
    h, w = shape[:2]
    m = np.zeros((h, w), np.float32)
    for x, y, fw, fh in faces:
        c = (int(x + fw / 2), int(y + fh * 0.55))
        ax = (int(fw * 0.7), int(fh * 0.85))
        cv2.ellipse(m, c, ax, 0, 0, 360, 1.0, -1)
    k = int(max(15, max((f[2] for f in faces), default=40) * 0.6)) | 1
    m = cv2.GaussianBlur(m, (0, 0), k / 2.5)
    return np.clip(m / max(m.max(), 1e-6), 0, 1)[..., None]


def _lum(x):
    return x @ np.array([0.2126, 0.7152, 0.0722])


def develop(src, dst_dir, film, paper, ev, fmt, maxside, print_exp, y_shift, m_shift, auto_exp=True,
            frame=None, brighten=0.0, dodge=True):
    from spektrafilm import simulate
    img, space, decode = load(src, maxside)
    if print_exp is None:
        print_exp = auto_print_exposure(img, (film, paper, space, decode, ev, fmt, y_shift, m_shift, auto_exp),
                                        brighten)
    out = simulate(img, _params(film, paper, space, decode, ev, fmt, print_exp, y_shift, m_shift, auto_exp))
    out = np.clip(out, 0, 1)
    if dodge:
        out = _dodge_faces(img, out, decode, print_exp,
                           (film, paper, space, decode, ev, fmt), (y_shift, m_shift, auto_exp))
    if MIX < 1.0:   # 只上一部分胶片味：和原图按比例混合
        orig = np.clip(img, 0, 1) if decode else np.clip(__import__('colour').RGB_to_RGB(
            img, 'ProPhoto RGB', 'sRGB', apply_cctf_encoding=True), 0, 1)
        out = orig * (1 - MIX) + out * MIX
    from PIL import Image
    dst = Path(dst_dir) / f"{src.stem}_{film}.jpg"
    im = Image.fromarray((out * 255 + 0.5).astype(np.uint8))
    if frame is not None:
        from border import add_border
        im = add_border(im, film, frame, style=BORDER_STYLE, date=_date_text(src) if DATE else None,
                        seed=sum(map(ord, src.name)))
    im.save(dst, quality=97)
    return dst, print_exp


def _dodge_faces(img, out, decode, print_exp, a1, a2):
    """暗房遮挡：脸太暗就给脸那一块少一点相纸曝光，再放一次，按柔和遮罩拼回去。
    颗粒用的是固定种子，两次放出来的颗粒完全一样，接缝看不出来。"""
    from spektrafilm import simulate
    faces = find_faces(img, decode)
    if not faces:
        return out
    m = face_mask(out.shape, faces)
    # 只量脸中间的皮肤，不算头发和背景
    skin = np.concatenate([_lum(out[y + fh // 4: y + fh * 3 // 4, x + fw // 4: x + fw * 3 // 4]).ravel()
                           for x, y, fw, fh in faces])
    lum = float(np.median(skin))
    if lum >= FACE_TARGET - 0.03:
        return out
    factor = max(1 - MAX_DODGE, (lum / FACE_TARGET) ** (1 / SLOPE))
    factor = 1 - (1 - factor) * DODGE_STRENGTH
    bright = np.clip(simulate(img, _params(*a1, print_exp * factor, *a2)), 0, 1)
    # 本来就亮的地方（天空、白衣服）不跟着提，免得头周围冒一圈光
    keep_hi = np.clip((0.78 - _lum(out)) / 0.3, 0, 1)[..., None]
    m = m * keep_hi
    print(f"   遮挡了 {len(faces)} 张脸，脸 {lum:.2f} -> 相纸曝光 ×{factor:.2f}", flush=True)
    return out * (1 - m) + bright * m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--film', default='kodak_portra_400')
    ap.add_argument('--paper', default='kodak_portra_endura')
    ap.add_argument('--ev', type=float, default=0.0)
    ap.add_argument('--format', type=float, default=35)
    ap.add_argument('--maxside', type=int, default=6000)
    ap.add_argument('--print-exposure', type=float, default=None,
                    help='相纸曝光，越大越暗；不填就自动定亮度')
    ap.add_argument('--brighten', type=float, default=0.0, help='自动亮度基础上再亮(正)/暗(负)，单位约等于档')
    ap.add_argument('--no-auto', action='store_true', help='关掉自动测光，按原片亮度')
    ap.add_argument('--border', action='store_true', help='加胶卷边框（齿孔、片边字）')
    ap.add_argument('--style', choices=['kodak', 'fuji', 'cine'], default=None,
                    help='边框样式，不填就按胶片自动选')
    ap.add_argument('--date', action='store_true', help='右下角印拍摄日期，像老相机的日期后背')
    ap.add_argument('--mix', type=float, default=1.0, help='胶片味浓度，1 是全胶片，0.6 就是六成胶片四成原图')
    ap.add_argument('--no-dodge', action='store_true', help='不给人脸做遮挡提亮')
    ap.add_argument('--dodge', type=float, default=1.0, help='人脸遮挡力度，默认 1，整个人在背光里的照片试 0.5')
    ap.add_argument('--y', type=float, default=0)
    ap.add_argument('--m', type=float, default=0)
    a = ap.parse_args()
    global BORDER_STYLE, DATE, DODGE_STRENGTH, MIX
    MIX = a.mix
    DODGE_STRENGTH = a.dodge
    BORDER_STYLE, DATE = a.style, a.date
    os.makedirs(a.dst, exist_ok=True)
    src = Path(a.src)
    files = sorted(f for f in (src.iterdir() if src.is_dir() else [src])
                   if f.suffix.lower() in RAW_EXT | IMG_EXT)
    for i, f in enumerate(files):
        t = time.time()
        try:
            d, pe = develop(f, a.dst, a.film, a.paper, a.ev, a.format, a.maxside,
                            a.print_exposure, a.y, a.m, not a.no_auto,
                            frame=(i + 1) if a.border else None, brighten=a.brighten,
                            dodge=not a.no_dodge)
            print(f"OK {f.name} -> {d.name}  相纸曝光 {pe:.2f}  ({time.time()-t:.0f}s)", flush=True)
        except Exception as e:
            print(f"FAIL {f.name}: {e}", flush=True)


if __name__ == '__main__':
    main()
