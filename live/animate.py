"""把一张冲好的照片做成 3 秒无缝循环的"实况"小动效，带胶卷边框。

动的东西（都很轻）：
  鸟     抠出来，背景补好；每只鸟翅膀上下扇（以身体为轴，翅尖位移最大），位置轻轻飘
  水面   高光处一闪一闪
  草     很小的横向摆动，像风吹过
  雾     远山那条雾带，明暗慢慢往一边流
  胶片   每帧颗粒都不一样、画面在片门里轻微晃、整体亮度轻微闪烁

所有周期都是 3 秒的整数分之一，所以首尾帧接得上，循环看不出接缝。

python live/animate.py 冲好的照片.jpg 输出.mp4 --film kodak_gold_200 --frame 12
"""
import argparse, math, os, subprocess, sys
from pathlib import Path
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from birds import find_birds
from border import add_border

T, FPS = 3.0, 30
N = int(T * FPS)
LUM = np.array([.2126, .7152, .0722], np.float32)


def periodic(k, t, phase=0.0):
    return np.sin(2 * math.pi * k * t / T + phase)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--film', default='kodak_gold_200')
    ap.add_argument('--frame', type=int, default=1)
    ap.add_argument('--width', type=int, default=1350, help='照片部分的宽度（像素）')
    ap.add_argument('--bird-ymax', type=float, default=0.629, help='鸟只在这个高度以上找（占原图高度的比例）')
    ap.add_argument('--glow', type=float, default=1.7)
    ap.add_argument('--still', default=None, help='同时导出第一帧当封面照片')
    a = ap.parse_args()

    full = np.asarray(Image.open(a.src).convert('RGB')).astype(np.float32) / 255
    H0, W0 = full.shape[:2]
    # 找鸟（在原尺寸上找，更准），地平线附近只要大一点的，避开骑马人
    birds, _ = find_birds(full, int(a.bird_ymax * H0), extra_zone=(150, int(0.658 * H0)),
                          exclude_x=(int(0.446 * W0), int(0.563 * W0)))
    # 裁成 3:2，保留下面
    ch = int(W0 / 1.5); cy = H0 - ch
    full = full[cy:]
    birds = [(x, y - cy, bw, bh) for x, y, bw, bh in birds if y - cy > 0]
    s = a.width / W0
    w, h = a.width, int(round(ch * s))
    img = cv2.resize(full, (w, h), interpolation=cv2.INTER_AREA)
    birds = [(x * s, y * s, bw * s, bh * s) for x, y, bw, bh in birds]
    print(f"{len(birds)} 只鸟，画面 {w}x{h}")

    L = img @ LUM
    bgL = cv2.medianBlur((L * 255).astype(np.uint8), 21).astype(np.float32) / 255
    dark = np.clip(bgL - L, 0, 1)

    # ---- 鸟：抠图 + 补背景 ----
    hole = np.zeros((h, w), np.uint8)
    sprites = []
    rng = np.random.default_rng(7)
    for x, y, bw, bh in birds:
        pad = int(max(3, 0.5 * max(bw, bh))) + 2
        x0, y0 = max(0, int(x) - pad), max(0, int(y) - pad)
        x1, y1 = min(w, int(x + bw) + pad + 1), min(h, int(y + bh) + pad + 1)
        al = np.clip((dark[y0:y1, x0:x1] - 0.025) / 0.09, 0, 1)
        if al.max() < 0.3:
            continue
        hole[y0:y1, x0:x1] |= (cv2.dilate((al > 0.05).astype(np.uint8), np.ones((5, 5), np.uint8)) * 255)
        size = max(bw, bh)
        sprites.append(dict(
            x0=x0, y0=y0, col=img[y0:y1, x0:x1].copy(), al=al,
            cx=x + bw / 2 - x0, cy=y + bh / 2 - y0, hw=max(2.0, bw / 2),
            amp=0.42 * max(bh, 0.35 * bw),                      # 翅尖上下的幅度
            k=int(rng.integers(4, 7)) if size > 12 else int(rng.integers(6, 9)),   # 大鸟扇得慢
            ph=rng.uniform(0, 2 * math.pi),
            dx=rng.uniform(1.5, 3.5) * (size / 15) ** 0.5, dy=rng.uniform(0.8, 2.0),
            ph2=rng.uniform(0, 2 * math.pi)))
    plate = cv2.inpaint((img * 255).astype(np.uint8), hole, 4, cv2.INPAINT_TELEA).astype(np.float32) / 255
    # 补过的地方加回颗粒，不然是一块块光滑的
    grain_fix = rng.normal(0, 0.012, (h, w, 1)).astype(np.float32)
    plate = np.where(hole[..., None] > 0, plate + grain_fix, plate)

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    horizon = h * 0.62
    sat = img.max(2) - img.min(2)
    # ---- 水面高光 ----
    water = ((L > 0.74) & (sat < 0.18) & (yy > horizon)).astype(np.float32)
    water = cv2.GaussianBlur(water, (0, 0), 0.8)
    twinkle_ph = cv2.GaussianBlur(rng.uniform(0, 2 * math.pi, (h, w)).astype(np.float32), (0, 0), 1.2)
    twinkle_ph = (twinkle_ph - twinkle_ph.mean()) * 9
    # ---- 草（暖色、不太暗、地平线以下）----
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    grass = ((r > g) & (g > b) & (b < 0.85 * r) & (L > 0.22) & (L < 0.7) & (yy > horizon + 5)).astype(np.float32)
    grass = cv2.GaussianBlur(grass, (0, 0), 4)
    grass *= np.clip((yy - horizon) / (0.25 * h), 0, 1)          # 越近摆得越明显
    # ---- 雾带 ----
    mist = np.exp(-((yy - 0.56 * h) / (0.09 * h)) ** 2) * np.clip((L - 0.4) / 0.2, 0, 1)

    # ---- 胶卷边框（只做一次）----
    border = add_border(Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)), a.film, a.frame,
                        seed=12, glow=a.glow)
    border = np.asarray(border).astype(np.float32) / 255
    mm = w / 36.0
    bx, by = int(0.8 * mm), int(5.5 * mm)
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=int(0.3 * mm), fill=255)
    mask = np.asarray(mask.filter(ImageFilter.GaussianBlur(0.1 * mm))).astype(np.float32)[..., None] / 255
    BH, BW = border.shape[:2]
    BH2, BW2 = BH - BH % 2, BW - BW % 2

    os.makedirs(os.path.dirname(os.path.abspath(a.dst)), exist_ok=True)
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                           '-s', f'{BW2}x{BH2}', '-r', str(FPS), '-i', '-',
                           '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p',
                           '-movflags', '+faststart', a.dst], stdin=subprocess.PIPE)
    for i in range(N):
        t = i / FPS
        fr = plate.copy()
        # 草：横向轻摆，一阵阵从左往右
        wave = (np.sin(2 * math.pi * (t / T) * 2 - xx * 0.012 + yy * 0.006) * 0.7
                + np.sin(2 * math.pi * (t / T) * 3 - xx * 0.031) * 0.3)
        disp = (1.6 * grass * wave).astype(np.float32)
        fr = cv2.remap(fr, xx + disp, yy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        # 水面高光闪烁
        fr = fr * (1 + (0.16 * water * np.sin(twinkle_ph + 2 * math.pi * 3 * t / T)
                        )[..., None])
        # 雾慢慢流动
        flow = (np.sin(2 * math.pi * (xx / w * 1.3 - t / T) + yy * 0.01) * 0.6
                + np.sin(2 * math.pi * (xx / w * 2.7 - 2 * t / T) + 1.7) * 0.4)
        fr = fr + (0.022 * mist * flow)[..., None]
        # 鸟
        for sp in sprites:
            ph = 2 * math.pi * sp['k'] * t / T + sp['ph']
            flap = math.sin(ph)
            ox = sp['dx'] * math.sin(2 * math.pi * t / T + sp['ph2'])
            oy = sp['dy'] * math.sin(2 * math.pi * 2 * t / T + sp['ph2'] * 1.7) + 0.12 * sp['amp'] * flap
            pad = int(sp['amp'] + max(sp['dx'], sp['dy']) + 3)
            ch_, cw_ = sp['al'].shape
            gh, gw = ch_ + 2 * pad, cw_ + 2 * pad
            gy, gx = np.mgrid[0:gh, 0:gw].astype(np.float32)
            u = gx - pad - ox
            rel = np.clip(np.abs(u - sp['cx']) / sp['hw'], 0, 1.3)
            v = gy - pad - oy + sp['amp'] * flap * rel ** 1.4   # 翅尖动得多，身体几乎不动
            colp = cv2.remap(sp['col'], u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            alp = cv2.remap(sp['al'], u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            X0, Y0 = sp['x0'] - pad, sp['y0'] - pad
            sx0, sy0 = max(0, -X0), max(0, -Y0)
            X1, Y1 = min(w, X0 + gw), min(h, Y0 + gh)
            if X1 <= max(0, X0) or Y1 <= max(0, Y0):
                continue
            reg = fr[max(0, Y0):Y1, max(0, X0):X1]
            al_ = alp[sy0:sy0 + reg.shape[0], sx0:sx0 + reg.shape[1], None]
            cl_ = colp[sy0:sy0 + reg.shape[0], sx0:sx0 + reg.shape[1]]
            fr[max(0, Y0):Y1, max(0, X0):X1] = reg * (1 - al_) + cl_ * al_
        # 片门晃动（不到一个像素）+ 每帧新颗粒 + 轻微闪烁
        gx_ = 0.5 * math.sin(2 * math.pi * t / T) + 0.25 * math.sin(2 * math.pi * 5 * t / T + 1)
        gy_ = 0.4 * math.sin(2 * math.pi * 2 * t / T + 2) + 0.2 * math.sin(2 * math.pi * 7 * t / T)
        fr = cv2.warpAffine(fr, np.float32([[1, 0, gx_], [0, 1, gy_]]), (w, h), borderMode=cv2.BORDER_REFLECT)
        gr = np.random.default_rng(100 + i).normal(0, 1, (h, w)).astype(np.float32)
        gr = cv2.GaussianBlur(gr, (0, 0), 0.7) * 0.022
        fr = fr + gr[..., None] * (0.5 + 0.5 * (1 - np.abs(fr @ LUM - 0.5)[..., None] * 2))
        fr *= 1 + 0.012 * math.sin(2 * math.pi * 4 * t / T) + 0.006 * math.sin(2 * math.pi * 9 * t / T)
        # 锐化一点
        bl = cv2.GaussianBlur(fr, (0, 0), 1.0)
        fr = fr + 0.6 * (fr - bl)
        out = border.copy()
        reg = out[by:by + h, bx:bx + w]
        out[by:by + h, bx:bx + w] = reg * (1 - mask) + np.clip(fr, 0, 1) * mask
        frame8 = (np.clip(out[:BH2, :BW2], 0, 1) * 255 + 0.5).astype(np.uint8)
        if i == 0 and a.still:
            Image.fromarray(frame8).save(a.still, quality=96)
        ff.stdin.write(frame8.tobytes())
        if i % 15 == 0:
            print(f"  帧 {i}/{N}", flush=True)
    ff.stdin.close(); ff.wait()
    print('完成', a.dst)


if __name__ == '__main__':
    main()
