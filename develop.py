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


BORDER_STYLE, DATE = None, False


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


def develop(src, dst_dir, film, paper, ev, fmt, maxside, print_exp, y_shift, m_shift, auto_exp=True,
            frame=None, brighten=0.0):
    from spektrafilm import simulate
    img, space, decode = load(src, maxside)
    if print_exp is None:
        print_exp = auto_print_exposure(img, (film, paper, space, decode, ev, fmt, y_shift, m_shift, auto_exp),
                                        brighten)
    out = simulate(img, _params(film, paper, space, decode, ev, fmt, print_exp, y_shift, m_shift, auto_exp))
    out = np.clip(out, 0, 1)
    from PIL import Image
    dst = Path(dst_dir) / f"{src.stem}_{film}.jpg"
    im = Image.fromarray((out * 255 + 0.5).astype(np.uint8))
    if frame is not None:
        from border import add_border
        im = add_border(im, film, frame, style=BORDER_STYLE, date=_date_text(src) if DATE else None,
                        seed=sum(map(ord, src.name)))
    im.save(dst, quality=97)
    return dst, print_exp


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
    ap.add_argument('--y', type=float, default=0)
    ap.add_argument('--m', type=float, default=0)
    a = ap.parse_args()
    global BORDER_STYLE, DATE
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
                            frame=(i + 1) if a.border else None, brighten=a.brighten)
            print(f"OK {f.name} -> {d.name}  相纸曝光 {pe:.2f}  ({time.time()-t:.0f}s)", flush=True)
        except Exception as e:
            print(f"FAIL {f.name}: {e}", flush=True)


if __name__ == '__main__':
    main()
