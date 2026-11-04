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
- `--print-exposure`：**调亮度就调这个**。数字越大，成片越暗、越沉。暗调照片可以试 2～3
- `--ev`：相机曝光补偿。会被放大机自动抵消大部分，主要影响胶片的宽容度，不怎么改亮度
- `--format`：底片画幅（毫米），默认 35，改成 120 颗粒会变细
- `--maxside`：长边像素，默认 3000（越大越慢，3000 大约 40 秒一张）

## 许可

本仓库脚本按 GPL-3.0 发布，和 spektrafilm 一致。胶片与相纸数据为 CC BY-SA 4.0。film modeling powered by spektrafilm.
