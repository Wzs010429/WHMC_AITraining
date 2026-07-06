# WHMC 工作坊 — 环境配置指南

> FLUX 和 TTS 各自独立虚拟环境，互不干扰。

---

## 一、一键安装

```bash
cd ~/WHMC_AITraining/demo
chmod +x install.sh
./install.sh
```

自动创建 `flux-env` + `tts-env` 两个环境，装好全部依赖。

---

## 二、手动安装

### FLUX 文生图环境

```bash
cd ~/WHMC_AITraining/demo
python3 -m venv flux-env
source flux-env/bin/activate
pip install -r requirements-flux.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install torch --index-url https://download.pytorch.org/whl/cu124
```

| 包 | 来源 | 用途 |
|------|------|------|
| `fastapi`, `uvicorn`, `pydantic`, `requests` | PyPI | Web 框架 |
| `torch` | PyTorch 官方 | GPU 推理 |
| `diffusers`, `transformers`, `accelerate` | PyPI | FLUX 管道 |
| `Pillow` | PyPI | 图片处理 |
| `safetensors` | PyPI | 模型格式 |
| `modelscope` | PyPI | 模型下载（国内） |
| `huggingface_hub` | PyPI | HF 模型下载 |

### Higgs TTS 环境

```bash
cd ~/WHMC_AITraining/demo
python3 -m venv tts-env
source tts-env/bin/activate
pip install -r requirements-tts.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
```

| 包 | 来源 | 用途 |
|------|------|------|
| `fastapi`, `uvicorn`, `pydantic`, `requests` | PyPI | Web 框架 |
| `torch`, `torchaudio` | PyTorch 官方 | GPU 推理 + 音频 |
| `transformers` | `>=5.5.0` | PyPI | Higgs 模型加载 |

---

## 三、启动服务

两个 tmux，各自激活自己的环境：

```bash
# 终端1：FLUX（:5500）
tmux new -s flux
source ~/WHMC_AITraining/demo/flux-env/bin/activate
cd ~/WHMC_AITraining/demo/flux-inference-service
python server.py --model-path ./models/FLUX.2-klein-9B --host 0.0.0.0 --port 5500

# 终端2：TTS（:8100）
tmux new -s tts
source ~/WHMC_AITraining/demo/tts-env/bin/activate
cd ~/WHMC_AITraining/demo/higgs-tts-service
python server.py --model-path ./models/higgs-audio-v3-tts-4b --host 0.0.0.0 --port 8100
```

---

## 四、目录结构

```
~/WHMC_AITraining/demo/
├── flux-env/                     # FLUX 虚拟环境
├── tts-env/                      # TTS 虚拟环境
├── install.sh                    # 一键安装脚本
├── requirements-flux.txt         # FLUX 依赖
├── requirements-tts.txt          # TTS 依赖
├── ENV_SETUP.md                  # 本文件
│
├── flux-inference-service/
│   ├── server.py                 # FLUX 主程序 :5500
│   ├── models/FLUX.2-klein-9B/   # 模型权重（ModelScope 下载）
│   └── ...
│
└── higgs-tts-service/
    ├── server.py                 # TTS 主程序 :8100
    ├── models/higgs-audio-v3-tts-4b/  # 模型权重（管理员分发）
    └── ...
```
