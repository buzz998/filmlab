"""给冲好的照片加胶卷边框，模仿真胶片扫描出来的样子。

三种样式（按胶片自动选，也可以用 --style 指定）:
  kodak  柯达负片：上面印型号和格数，下面一排 DX 条码，齿孔完整
  fuji   富士：扫描仪裁掉齿孔，只留上沿一条细细的片边字，可加日期
  cine   电影卷（Vision3）：竖排 EASTMAN 52xx，字是浅灰色

真实感主要来自三样东西：片基边缘透出来的橙色光、齿孔周围的光晕、片边字小而等宽。
尺寸按 135 标准：片宽 35mm，画幅 36x24mm，KS 孔 1.98x2.794mm，孔距 4.75mm。

单独用: python border.py 输入.jpg 输出.jpg --film kodak_gold_200 --frame 12 [--date "'26 11 05"]
"""
import argparse, random
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = Path(__file__).with_name('fonts')
FONT_SANS = FONTS / 'DejaVuSansCondensed-Bold.ttf'
FONT_MONO = FONTS / 'DejaVuSansMono-Bold.ttf'

CINE_CODES = {'50d': '5203', '250d': '5207', '200t': '5213', '500t': '5219'}
SLIDE_STOCKS = ('provia', 'velvia', 'ektachrome', 'kodachrome')


def stock_label(film):
    """kodak_portra_400 -> KODAK PORTRA 400"""
    return film.replace('_', ' ').upper().replace('FUJIFILM', 'FUJI')


def style_for(film):
    if 'vision3' in film:
        return 'cine'
    if film.startswith('fujifilm'):
        return 'fuji'
    return 'kodak'


def _font(path, px):
    try:
        return ImageFont.truetype(str(path), max(6, int(px)))
    except OSError:
        return ImageFont.load_default(max(6, int(px)))


def _to_32(img):
    """裁成 3:2，和真胶卷画幅一样。"""
    w, h = img.size
    if w / h > 1.5:
        nw = int(h * 1.5); img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    elif w / h < 1.5:
        nh = int(w / 1.5); img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return img


def _film_base(W, H, rng, color):
    """片基：接近黑色，但有轻微的明暗起伏和颗粒。"""
    blot = rng.normal(0, 1, (max(2, H // 60), max(2, W // 60)))
    blot = Image.fromarray(((blot - blot.min()) / (np.ptp(blot) + 1e-6) * 255).astype(np.uint8))
    blot = np.asarray(blot.resize((W, H), Image.BICUBIC), dtype=np.float32)[..., None] / 255 - 0.5
    base = np.array(color, np.float32)[None, None, :] * (1 + blot * 0.5)
    base += rng.normal(0, 1.6, (H, W, 1))
    return base


def _glow(mask_img, radius, strength, color):
    """从亮的地方（画面、齿孔）往外渗的光。返回 float 数组。"""
    g = np.asarray(mask_img.filter(ImageFilter.GaussianBlur(radius)), np.float32) / 255
    return g[..., None] ** 1.3 * strength * np.array(color, np.float32)[None, None, :]


def _soft(layer_l, r):
    return layer_l.filter(ImageFilter.GaussianBlur(r))


def add_border(img, film='kodak_portra_400', frame=1, style=None, date=None, seed=None, text=None, glow=1.0):
    """img: 冲好的 PIL.Image。返回加了边框的新图。"""
    style = style or style_for(film)
    rng = np.random.default_rng(seed)
    rnd = random.Random(seed)
    portrait = img.height > img.width
    if portrait:
        img = img.rotate(90, expand=True)
    img = _to_32(img)
    w, h = img.size
    mm = w / 36.0

    if style == 'fuji':
        return _fuji(img, film, frame, date, rng, rnd, mm, portrait, text, glow)

    W, H = int(37.6 * mm), int(35.0 * mm)
    x0, y0 = int(0.8 * mm), int(5.5 * mm)
    base = _film_base(W, H, rng, (14, 9, 7) if style != 'cine' else (12, 8, 6))

    # 亮区遮罩：画面 + 齿孔，用来算光晕
    bright = Image.new('L', (W, H), 0)
    bd = ImageDraw.Draw(bright)
    bd.rectangle((x0, y0, x0 + w, y0 + h), fill=255)
    holes = Image.new('L', (W, H), 0)
    hd = ImageDraw.Draw(holes)
    hw, hh, r = 1.98 * mm, 2.794 * mm, 0.55 * mm
    x = rnd.uniform(0, 4.75) * mm - 4.75 * mm
    while x < W:
        for yc in (2.01 * mm + hh / 2, H - 2.01 * mm - hh / 2):
            hd.rounded_rectangle((x, yc - hh / 2, x + hw, yc + hh / 2), radius=r, fill=255)
        x += 4.75 * mm
    bright.paste(255, mask=holes)

    # 橙色光：画面边缘渗出来最强，齿孔周围也有一圈
    orange = (255, 120, 40)
    base += _glow(bright, 1.6 * mm * glow ** 0.5, 0.22 * glow, orange)
    base += _glow(bright, 0.45 * mm, 0.18 * glow, orange)
    # 一端轻微漏光（胶卷头尾常见）
    side = rnd.choice([0, 1])
    xs = np.linspace(0, 1, W)[None, :, None]
    leak = np.exp(-(xs if side == 0 else 1 - xs) / 0.06)
    base += leak * rnd.uniform(25, 60) * glow * np.array((1.0, 0.45, 0.15))[None, None, :]

    canvas = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))

    # 齿孔本身：透光，暖白，边缘柔
    hole_col = Image.new('RGB', (W, H), (252, 244, 230))
    canvas.paste(hole_col, mask=_soft(holes, 0.06 * mm))

    # 片边字
    txt = Image.new('L', (W, H), 0)
    td = ImageDraw.Draw(txt)
    if style == 'kodak':
        col = (240, 148, 70)
        label = text or stock_label(film)
        f_big = _font(FONT_SANS, 1.35 * mm)
        f_num = _font(FONT_SANS, 1.25 * mm)
        f_small = _font(FONT_SANS, 0.95 * mm)
        td.text((rnd.uniform(3, 8) * mm, 0.32 * mm), label, font=f_big, fill=255)
        td.text((x0 + 30 * mm, 0.32 * mm), f"{frame}", font=f_num, fill=255)
        # 下沿：DX 条码 + 格数
        yb, bh = H - 1.55 * mm, 1.35 * mm
        bx = 0.0
        code = rng.integers(0, 2, 64)
        cell = 0.55 * mm
        segs = [(0, 13.5), (19.5, 33.5)]  # 两段条码，中间留给格数，单位 mm
        for s0, s1 in segs:
            bx = s0 * mm
            i = 0
            while bx < s1 * mm:
                wbar = cell * (1 + code[i % 64])
                if i % 2 == 0:
                    td.rectangle((bx, yb, bx + wbar - 0.12 * mm, yb + bh), fill=255)
                bx += wbar; i += 1
        td.text((14.5 * mm, yb - 0.1 * mm), f"{frame}A", font=f_num, fill=255)
        td.text((17.6 * mm, yb + 0.05 * mm), "→", font=f_num, fill=255)
        td.text((34.2 * mm, yb - 0.1 * mm), f"{frame + 1}", font=f_num, fill=255)
    else:  # cine
        col = (205, 200, 195)
        code = CINE_CODES.get(film.split('_')[-1], '5207')
        f = _font(FONT_MONO, 1.15 * mm)
        # 片边字印在上沿（竖图转过来就成了竖排，和电影卷扫描一样）
        td.text((rnd.uniform(6, 14) * mm, 0.35 * mm), f"EASTMAN {code}", font=f, fill=255)
        td.rectangle((0.2 * mm, 0.0, 0.45 * mm, 1.6 * mm), fill=255)   # 片头刻痕
    txt = _soft(txt, 0.035 * mm)
    canvas.paste(Image.new('RGB', (W, H), col), mask=txt)
    # 字也有一点光晕
    glow_txt = np.asarray(canvas, np.float32) + _glow(txt, 0.3 * mm, 0.35 * glow, orange)
    canvas = Image.fromarray(np.clip(glow_txt, 0, 255).astype(np.uint8))

    _paste_photo(canvas, img, x0, y0, mm, date)
    if portrait:
        canvas = canvas.rotate(-90, expand=True)
    return canvas


def _fuji(img, film, frame, date, rng, rnd, mm, portrait, text, glow=1.0):
    """富士样式：扫描仪裁掉齿孔，只剩上沿一条片边字。"""
    w, h = img.size
    pad, top, bot = int(0.35 * mm), int(1.45 * mm), int(0.55 * mm)
    W, H = w + 2 * pad, h + top + bot
    x0, y0 = pad, top
    base = _film_base(W, H, rng, (16, 12, 10))
    bright = Image.new('L', (W, H), 0)
    ImageDraw.Draw(bright).rectangle((x0, y0, x0 + w, y0 + h), fill=255)
    base += _glow(bright, 0.5 * mm, 0.28 * glow, (255, 130, 50))
    canvas = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))

    name = text or film.replace('fujifilm_', '').replace('_', '').upper()
    name = {'PRO400H': 'PRO400H', 'XTRA400': 'X-TRA400', 'C200': 'C200',
            'PROVIA100F': 'RDP III', 'VELVIA100': 'RVP100'}.get(name, name)
    lot = ''.join(rnd.choice('ABCDEF') for _ in range(6))
    f = _font(FONT_MONO, 0.78 * mm)
    txt = Image.new('L', (W, H), 0)
    td = ImageDraw.Draw(txt)
    y = 0.38 * mm
    unit = [(f"{name}", 0.0), (lot, 6.5), ("FUJI", 13.0), (f"{frame}  ◀■", 16.5),
            (name, 22.0), (lot, 28.5), (f"{rnd.randint(100, 999)}", 34.0)]
    off = -rnd.uniform(0, 10)
    for k in range(2):
        for s, dx in unit:
            xx = (off + dx + k * 38.0) * mm
            if -5 * mm < xx < W:
                td.text((xx, y), s, font=f, fill=255)
    txt = _soft(txt, 0.03 * mm)
    canvas.paste(Image.new('RGB', (W, H), (238, 196, 92)), mask=txt)
    _paste_photo(canvas, img, x0, y0, mm, date)
    if portrait:
        canvas = canvas.rotate(-90, expand=True)
    return canvas


def _paste_photo(canvas, img, x0, y0, mm, date):
    img = img.copy()
    if date:
        _date_imprint(img, date, mm)
    w, h = img.size
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=int(0.3 * mm), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(0.1 * mm))
    canvas.paste(img, (x0, y0), mask)


def _date_imprint(img, date, mm):
    """老相机日期后背：右下角橙红色小数字，透过底片背面曝光，所以边缘发散。"""
    w, h = img.size
    f = _font(FONT_MONO, 1.0 * mm)
    layer = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(layer)
    tw = d.textlength(date, font=f)
    d.text((w - tw - 2.2 * mm, h - 2.3 * mm), date, font=f, fill=255)
    halo = np.asarray(layer.filter(ImageFilter.GaussianBlur(0.25 * mm)), np.float32)[..., None] / 255
    core = np.asarray(layer.filter(ImageFilter.GaussianBlur(0.04 * mm)), np.float32)[..., None] / 255
    a = np.asarray(img, np.float32)
    col = np.array((255, 110, 30), np.float32)
    a = a + halo * col * 0.6
    a = a * (1 - core * 0.85) + core * 0.85 * np.array((255, 170, 90))
    img.paste(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--film', default='kodak_portra_400')
    ap.add_argument('--style', choices=['kodak', 'fuji', 'cine'], default=None)
    ap.add_argument('--frame', type=int, default=1)
    ap.add_argument('--date', default=None, help="日期印记，比如 \"'26 11 05\"")
    ap.add_argument('--text', default=None, help='自定义片边字')
    ap.add_argument('--glow', type=float, default=1.0, help='边框橙色透光和漏光的强度，想更浓试 1.6')
    ap.add_argument('--sharpen', type=float, default=0.0, help='加框前先锐化照片，0.6 左右比较自然')
    a = ap.parse_args()
    im = Image.open(a.src).convert('RGB')
    if a.sharpen > 0:
        r = max(1.0, max(im.size) / 1500)
        im = im.filter(ImageFilter.UnsharpMask(radius=r, percent=int(160 * a.sharpen), threshold=3))
    out = add_border(im, a.film, a.frame, a.style, a.date, text=a.text, glow=a.glow)
    out.save(a.dst, quality=97)


if __name__ == '__main__':
    main()
