# WHMC 工作坊 — 统一环境配置指南

一个虚拟环境同时运行 **FLUX 文生图**（`:5500`）和 **Higgs TTS**（`:8100`）。

---

## 一、环境信息

| 项目 | 版本 |
|------|------|
| Python | 3.10+ |
| CUDA | 12.4 |
| PyTorch | 2.5+ |
| GPU 推荐 | L20 48GB / A4000 16GB |

---

## 二、一键安装（推荐）

```bash
cd ~/WHMC_AITraining/demo
chmod +x install.sh
./install.sh
```

> 自动完成：创建 venv → 装依赖 → 装 PyTorch → 装 sglang-omni

## 三、手动安装（如需 Conda）

### 方式 A：venv

```bash
cd ~/WHMC_AITraining/demo
python3 -m venv demo-env
source demo-env/bin/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install git+https://github.com/sgl-project/sglang-omni.git
```

### 方式 B：Conda

```bash
conda create -n whmc-demo python=3.10 -y
conda activate whmc-demo
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install git+https://github.com/sgl-project/sglang-omni.git
```

验证：

```bash
python -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0))"
```

### 完整依赖清单

| 包 | 版本要求 | 来源 | 用途 |
|------|---------|------|------|
| `fastapi` | `>=0.110.0` | PyPI | Web 框架 |
| `uvicorn` | `>=0.29.0` | PyPI | ASGI 服务器 |
| `pydantic` | `>=2.6.0` | PyPI | 数据校验 |
| `requests` | `>=2.28.0` | PyPI | HTTP 客户端 |
| `torch` | `>=2.5.0` | **PyTorch 官方** | GPU 推理 |
| `torchaudio` | `>=2.5.0` | **PyTorch 官方** | 音频处理（TTS） |
| `diffusers` | `>=0.32.0` | PyPI | FLUX 文生图管道 |
| `transformers` | `>=4.46.0` | PyPI | 模型加载（FLUX 依赖） |
| `accelerate` | `>=0.30.0` | PyPI | 分布式推理（FLUX 依赖） |
| `Pillow` | `>=10.0.0` | PyPI | 图片编解码 |
| `safetensors` | `>=0.4.0` | PyPI | 模型文件格式 |
| `modelscope` | `>=1.20.0` | PyPI | FLUX 模型下载（国内） |
| `huggingface_hub` | `>=1.0.0` | PyPI | HF 模型下载 |
| `sglang-omni` | — | **GitHub** | Higgs TTS 推理后端 |

> ⚠️ `torch` / `torchaudio` 需要 CUDA 专用索引，`sglang-omni` 只在 GitHub 上有

---

## 四、启动服务

两个 tmux 窗口，共享同一个环境：

```bash
# 终端1：FLUX 文生图（:5500）
tmux new -s flux
source ~/WHMC_AITraining/demo/demo-env/bin/activate   # 或 conda activate whmc-demo
cd ~/WHMC_AITraining/demo/flux-inference-service
python server.py --model-path ./models/FLUX.2-klein-9B --host 0.0.0.0 --port 5500
# Ctrl+B D 断开

# 终端2：Higgs TTS（:8100）
tmux new -s tts
source ~/WHMC_AITraining/demo/demo-env/bin/activate   # 或 conda activate whmc-demo
cd ~/WHMC_AITraining/demo/higgs-tts-service
python server.py --model-path ./models/higgs-audio-v3-tts-4b --host 0.0.0.0 --port 8100
# Ctrl+B D 断开
```

---

## 五、远程服务器快速搭建

全新服务器上从零开始：

```bash
# 1. 拉代码
cd ~ && git clone https://github.com/Wzs010429/WHMC_AITraining.git
cd WHMC_AITraining/demo

# 2. 建环境
python3 -m venv demo-env
source demo-env/bin/activate

# 3. 装包
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
# SGLang-Omni 不在 PyPI，从 GitHub 安装
pip install git+https://github.com/sgl-project/sglang-omni.git
# 如果 GitHub 连不上，在能翻的机器上下载源码后 pip install /path/to/sglang-omni

# 4. 下载 FLUX 模型（ModelScope）
pip install modelscope
modelscope download --model black-forest-labs/FLUX.2-klein-9B --local_dir ./flux-inference-service/models/FLUX.2-klein-9B

# 5. Higgs 模型由管理员拷贝 → ./higgs-tts-service/models/higgs-audio-v3-tts-4b/

# 6. 启动两个服务（见第四章）
```

---

## 六、目录结构

```
~/WHMC_AITraining/
├── demo/
│   ├── demo-env/                  # 统一虚拟环境（venv）
│   ├── requirements.txt           # 统一依赖清单
│   ├── ENV_SETUP.md               # 本文件
│   ├── README.md                  # 架构总览
│   │
│   ├── flux-inference-service/    # FLUX 文生图 :5500
│   │   ├── server.py
│   │   ├── models/FLUX.2-klein-9B/
│   │   └── ...
│   │
│   └── higgs-tts-service/        # Higgs TTS :8100
│       ├── server.py
│       ├── models/higgs-audio-v3-tts-4b/
│       └── ...
```
