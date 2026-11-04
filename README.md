# filmlab

把数码照片（RAW / JPG / HEIC）按真实胶片和相纸的光谱数据"冲洗"出来。底层引擎是 Andrea Volpato 的 [spektrafilm](https://github.com/andreavolpato/spektrafilm)，SpektraLab 用的也是它。

## 安装

```bash
./setup.sh
```

## 用法

```bash
source .venv/bin/activate
python develop.py 照片文件夹 输出文件夹 --film kodak_portra_400 --print-exposure 1.0
```

常用参数：

- `--film`：胶片，比如 `kodak_portra_400`、`kodak_gold_200`、`kodak_ektar_100`、`fujifilm_pro_400h`、`fujifilm_velvia_100`、`kodak_kodachrome_64`。完整列表在 `spektrafilm/src/spektrafilm/data/profiles/`
- `--paper`：相纸，默认 `kodak_portra_endura`
- `--print-exposure`：相纸曝光，数字越大越暗。**一般不用填**，不填会自动定亮度：先用小图试冲两三次，把成片亮度调到合适（逆光、大片天空也不会被骗）
- `--brighten`：在自动亮度基础上再亮一点（正数）或暗一点（负数），单位大约一档，比如 `--brighten 0.5`
- `--m` / `--y`：放大机的品红/黄滤镜，用来偏色。港风青绿调可以试 `--m 8 --y -4`
- `--ev`：相机曝光补偿。会被放大机自动抵消大部分，主要影响胶片的宽容度，不怎么改亮度
- `--format`：底片画幅（毫米），默认 35，改成 120 颗粒会变细
- `--border`：加 135 胶卷边框，有齿孔、片边印胶片型号、格数按文件顺序自动往上数。竖图会把胶卷转过来；非 3:2 的照片会裁成 3:2，和真胶卷一样
- `--maxside`：长边像素，默认 6000，基本就是原图尺寸（越大越慢；2500 像素大约 40 秒一张）

## 胶卷边框

`--border` 会按胶片自动选样式，也可以用 `--style` 指定：

- `kodak`：柯达负片，上沿印型号和格数，下沿一排 DX 条码，齿孔完整
- `fuji`：富士，扫描仪裁掉了齿孔，只剩上沿一条细细的等宽片边字
- `cine`：电影卷（Vision3），印 EASTMAN 52xx，浅灰色字

真实感来自三样：画面边缘和齿孔透出来的橙色光、胶卷一端的漏光、小而等宽的片边字。加 `--date` 会从照片拍摄时间生成老相机那种橙红色日期。

边框是自己写的（`border.py`），SpektraLab 的边框功能只在 Mac 上能用。尺寸按 135 标准：片宽 35mm、画幅 36×24mm、KS 孔 1.98×2.794mm、孔距 4.75mm。单独给任意照片加框：

```bash
python border.py 输入.jpg 输出.jpg --film fujifilm_pro_400h --frame 14 --date "'26 11 05"
```

## 许可

本仓库脚本按 GPL-3.0 发布，和 spektrafilm 一致。胶片与相纸数据为 CC BY-SA 4.0。字体 DejaVu Sans 为其自由许可。film modeling powered by spektrafilm.
