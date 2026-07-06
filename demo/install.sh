#!/bin/bash
# ============================================================
# WHMC 工作坊 — 一键环境安装（两个独立虚拟环境）
# ============================================================
# FLUX 文生图和 Higgs TTS 存在 protobuf 依赖冲突，
# 必须分开两个 venv。脚本自动完成全部安装。
# ============================================================
set -e

echo "========================================"
echo " WHMC 工作坊 环境安装"
echo "========================================"
echo ""
echo "将创建两个虚拟环境："
echo "  flux-env → FLUX 文生图（:5500）"
echo "  tts-env  → Higgs TTS（:8100）"
echo ""

# ── FLUX 环境 ──────────────────────────────

echo "━━━ [1/2] FLUX 文生图环境 ━━━"
echo ""

if [ ! -d "flux-env" ]; then
    echo "[flux] 创建虚拟环境..."
    python3 -m venv flux-env
else
    echo "[flux] 虚拟环境已存在，跳过"
fi

source flux-env/bin/activate
echo "[flux] 安装 Python 依赖..."
pip install -r requirements-flux.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
echo "[flux] 安装 PyTorch（CUDA 12.4）..."
pip install torch --index-url https://download.pytorch.org/whl/cu124
deactivate

echo ""
echo "[flux] ✅ FLUX 环境完成"
echo ""

# ── TTS 环境 ──────────────────────────────

echo "━━━ [2/2] Higgs TTS 环境 ━━━"
echo ""

if [ ! -d "tts-env" ]; then
    echo "[tts] 创建虚拟环境..."
    python3 -m venv tts-env
else
    echo "[tts] 虚拟环境已存在，跳过"
fi

source tts-env/bin/activate
echo "[tts] 安装 Python 依赖..."
pip install -r requirements-tts.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
echo "[tts] 安装 PyTorch（CUDA 12.4）..."
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
echo "[tts] 安装 SGLang-Omni（GitHub）..."
pip install git+https://github.com/sgl-project/sglang-omni.git
deactivate

echo ""
echo "[tts] ✅ TTS 环境完成"
echo ""

# ── 完成 ──────────────────────────────────

echo "========================================"
echo " ✅ 全部安装完成！"
echo "========================================"
echo ""
echo "启动 FLUX 文生图："
echo "  tmux new -s flux"
echo "  source flux-env/bin/activate"
echo "  cd flux-inference-service"
echo "  python server.py --model-path ./models/FLUX.2-klein-9B --host 0.0.0.0 --port 5500"
echo ""
echo "启动 Higgs TTS："
echo "  tmux new -s tts"
echo "  source tts-env/bin/activate"
echo "  cd higgs-tts-service"
echo "  python server.py --model-path ./models/higgs-audio-v3-tts-4b --host 0.0.0.0 --port 8100"
echo ""
