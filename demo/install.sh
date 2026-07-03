#!/bin/bash
# ============================================================
# WHMC 工作坊 — 一键环境安装脚本（Linux 服务器）
# ============================================================
# 用法：
#   chmod +x install.sh
#   ./install.sh
# ============================================================
set -e

echo "========================================"
echo " WHMC 工作坊 环境安装"
echo "========================================"

# 建虚拟环境
if [ ! -d "demo-env" ]; then
    echo "[1/4] 创建虚拟环境..."
    python3 -m venv demo-env
else
    echo "[1/4] 虚拟环境已存在，跳过"
fi

source demo-env/bin/activate

# 基础依赖
echo "[2/4] 安装 Python 依赖..."
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# PyTorch（CUDA 12.4）
echo "[3/4] 安装 PyTorch（CUDA 12.4）..."
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124

# SGLang-Omni
echo "[4/4] 安装 SGLang-Omni..."
pip install git+https://github.com/sgl-project/sglang-omni.git

echo ""
echo "========================================"
echo " 安装完成！"
echo "========================================"
echo ""
echo "启动 FLUX 文生图："
echo "  tmux new -s flux"
echo "  source demo-env/bin/activate"
echo "  cd flux-inference-service"
echo "  python server.py --model-path ./models/FLUX.2-klein-9B --host 0.0.0.0 --port 5500"
echo ""
echo "启动 Higgs TTS："
echo "  tmux new -s tts"
echo "  source demo-env/bin/activate"
echo "  cd higgs-tts-service"
echo "  python server.py --model-path ./models/higgs-audio-v3-tts-4b --host 0.0.0.0 --port 8100"
echo ""
