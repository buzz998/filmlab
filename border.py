"""给冲好的照片加 135 胶卷边框：齿孔、片边字、格数。

尺寸按真实 135 胶卷：片宽 35mm，画幅 36x24mm，齿孔 2.8x1.98mm、间距 4.75mm、每格 8 个。
单独用:  python border.py 输入.jpg 输出.jpg --text "KODAK PORTRA 400" --frame 12
"""
import argparse, random
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = Path(__file__).with_name('fonts') / 'DejaVuSansCondensed-Bold.ttf'

# 每款胶片的片基色（扫描后边框的颜色）和片边字颜色
LOOKS = {
    'negative': dict(base=(24, 16, 12), text=(232, 150, 60), hole=(248, 246, 240)),
    'slide':    dict(base=(8, 8, 9),    text=(225, 190, 120), hole=(250, 250, 250)),
}
SLIDE_STOCKS = ('provia', 'velvia', 'ektachrome', 'kodachrome')


def stock_label(film):
    """kodak_portra_400 -> KODAK PORTRA 400"""
    return film.replace('_', ' ').upper().replace('FUJIFILM', 'FUJI')


def _font(px):
    try:
        return ImageFont.truetype(str(FONT), px)
    except OSError:
        return ImageFont.load_default(px)


def add_border(img, text='', frame=None, look='negative', seed=None):
    """img: PIL.Image（已冲好的照片）。返回加了边框的新图。"""
    rnd = random.Random(seed)
    portrait = img.height > img.width
    if portrait:
        img = img.rotate(90, expand=True)

    # 裁成 3:2（135 画幅），和真胶卷一样
    w, h = img.size
    if w / h > 1.5:
        nw = int(h * 1.5); img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    elif w / h < 1.5:
        nh = int(w / 1.5); img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    w, h = img.size
    mm = w / 36.0                                   # 每毫米多少像素

    c = LOOKS[look]
    frame_w = 38.0                                  # 画幅 36mm + 两边各 1mm 间隔
    W, H = int(frame_w * mm), int(35.0 * mm)
    canvas = Image.new('RGB', (W, H), c['base'])

    # 片基不是纯色：轻微的明暗起伏
    rng = np.random.default_rng(seed)
    blot = Image.fromarray(rng.normal(128, 40, (max(2, H // 40), max(2, W // 40))).clip(0, 255).astype(np.uint8))
    blot = np.asarray(blot.resize((W, H), Image.BICUBIC), dtype=np.float32)[..., None]
    fine = rng.normal(0, 2.0, (H, W, 1))
    base = np.asarray(canvas, dtype=np.float32) + (blot - 128) * 0.06 + fine
    canvas = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))

    # 画面：边缘稍微柔一点，像片门投下的影子
    x0, y0 = int(1.0 * mm), int(5.5 * mm)
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=int(0.35 * mm), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(0.12 * mm))
    canvas.paste(img, (x0, y0), mask)

    d = ImageDraw.Draw(canvas)
    # 齿孔：每格 8 个，间距 4.75mm，上下各一排；起点随机偏一点，每张不一样
    # KS 标准孔：沿片长 1.98mm，沿片宽 2.794mm，离片边 2.01mm
    hw, hh, r = 1.98 * mm, 2.794 * mm, 0.5 * mm
    start = rnd.uniform(0, 4.75) * mm
    x = start - 4.75 * mm
    while x < W:
        for yc in (2.01 * mm + hh / 2, H - 2.01 * mm - hh / 2):
            d.rounded_rectangle((x, yc - hh / 2, x + hw, yc + hh / 2), radius=r, fill=c['hole'])
        x += 4.75 * mm

    # 片边字：外侧印型号，内侧印格数和箭头
    f_big, f_small = _font(int(1.5 * mm)), _font(int(1.25 * mm))
    if text:
        d.text((rnd.uniform(3, 10) * mm, 0.25 * mm), text, font=f_big, fill=c['text'])
    if frame is not None:
        n = f"{frame}"
        d.text((x0 + 4 * mm, H - 1.75 * mm), f"▶ {n}", font=f_small, fill=c['text'])
        d.text((x0 + 22 * mm, H - 1.75 * mm), f"{n}A", font=f_small, fill=c['text'])
        # 上边内侧再印一小串，像真片那样
        d.text((x0 + 26 * mm, 0.25 * mm), f"{n}  ▶", font=f_small, fill=c['text'])

    # 字和孔边有一点点晕开
    canvas = canvas.filter(ImageFilter.GaussianBlur(0.03 * mm))
    if portrait:
        canvas = canvas.rotate(-90, expand=True)
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--text', default='KODAK PORTRA 400')
    ap.add_argument('--frame', type=int, default=None)
    ap.add_argument('--look', default='negative', choices=list(LOOKS))
    a = ap.parse_args()
    add_border(Image.open(a.src).convert('RGB'), a.text, a.frame, a.look).save(a.dst, quality=94)


if __name__ == '__main__':
    main()
