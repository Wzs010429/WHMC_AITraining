#!/bin/bash
# ============================================================
# WHMC 工作坊 — 一键环境安装
# ============================================================
# FLUX（:5500）+ Higgs TTS（:8100），各自独立 venv
# ============================================================
set -e

echo "WHMC 工作坊 环境安装"
echo "  flux-env → FLUX 文生图（:5500）"
echo "  tts-env  → Higgs TTS（:8100）"
echo ""

# ── FLUX ──
echo "━━━ [1/2] FLUX ━━━"
[ ! -d "flux-env" ] && python3 -m venv flux-env
source flux-env/bin/activate
pip install -r requirements-flux.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install torch --index-url https://download.pytorch.org/whl/cu124
deactivate
echo "[flux] ✅"
echo ""

# ── TTS ──
echo "━━━ [2/2] TTS ━━━"
[ ! -d "tts-env" ] && python3 -m venv tts-env
source tts-env/bin/activate
pip install -r requirements-tts.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
deactivate
echo "[tts] ✅"
echo ""

echo "========================================"
echo " ✅ 全部完成！"
echo "========================================"
echo ""
echo "启动 FLUX："
echo "  tmux new -s flux"
echo "  source flux-env/bin/activate"
echo "  cd flux-inference-service"
echo "  python server.py --model-path ./models/FLUX.2-klein-9B --host 0.0.0.0 --port 5500"
echo ""
echo "启动 TTS："
echo "  tmux new -s tts"
echo "  source tts-env/bin/activate"
echo "  cd higgs-tts-service"
echo "  python server.py --model-path ./models/higgs-audio-v3-tts-4b --host 0.0.0.0 --port 8100"
echo ""
