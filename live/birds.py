"""找出照片里的鸟：比周围背景暗一截的小块。返回每只鸟的框和软遮罩。"""
import cv2, numpy as np

def find_birds(im, y_max, extra_zone=None, exclude_x=None):
    h, w = im.shape[:2]
    L = im @ np.array([.2126, .7152, .0722], np.float32)
    bg = cv2.medianBlur((L * 255).astype(np.uint8), 41).astype(np.float32) / 255
    d = np.clip(bg - L, 0, 1)
    m = (d > 0.10).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        x, y, bw, bh, a = st[i]
        if a < 4 or a > 3000 or (bh > 2.2 * bw and bh > 25):
            continue
        ok = y + bh < y_max
        if not ok and extra_zone and y + bh < extra_zone[1] and a >= extra_zone[0]:
            ok = not (exclude_x and exclude_x[0] < x + bw / 2 < exclude_x[1])
        if ok:
            out.append((int(x), int(y), int(bw), int(bh)))
    return out, d
