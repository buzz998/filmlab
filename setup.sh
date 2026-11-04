#!/usr/bin/env bash
# 一键装好冲印环境（Linux / WSL / macOS），需要先装好 uv：https://docs.astral.sh/uv/
set -e
cd "$(dirname "$0")"
[ -d spektrafilm ] || git clone --depth 1 https://github.com/andreavolpato/spektrafilm.git
uv venv --python 3.13 .venv
source .venv/bin/activate
uv pip install -e ./spektrafilm pillow-heif "opencv-python-headless<5"
echo "装好了。用法：source .venv/bin/activate && python develop.py 照片文件夹 输出文件夹"
