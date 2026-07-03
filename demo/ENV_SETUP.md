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

## 二、创建环境（二选一）

### 方式 A：venv（推荐，简单）

```bash
cd ~/WHMC_AITraining/demo
python3 -m venv demo-env
source demo-env/bin/activate
```

### 方式 B：Conda

```bash
conda create -n whmc-demo python=3.10 -y
conda activate whmc-demo
```

---

## 三、安装依赖

```bash
# 1. 基础依赖（fastapi, diffusers, transformers 等）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. PyTorch（CUDA 12.4 版）
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124

# 3. SGLang-Omni（Higgs TTS 后端）
# SGLang-Omni 不在 PyPI，从 GitHub 安装
pip install git+https://github.com/sgl-project/sglang-omni.git
# 如果 GitHub 连不上，在能翻的机器上下载源码后 pip install /path/to/sglang-omni
```

验证：

```bash
python -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0))"
```

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
