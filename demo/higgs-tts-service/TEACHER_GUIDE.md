# Higgs Audio v3 TTS — 教师本地部署指南

> 目标：Windows + NVIDIA A4000（16GB）
> 前提：已部署模板系统，可访问清华镜像和 PyTorch 官方源

## 一、文件清单

管理员提供的文件夹：

```
higgs-tts-service/
├── models/higgs-audio-v3-tts-4b/    ← 模型权重（8.7GB，预先下载好）
├── server.py                          ← 推理服务
├── quick_tts.py                       ← 测试脚本
├── test_client.py                     ← 连通性测试
└── requirements.txt                   ← 依赖清单
```

## 二、安装

```bash
cd higgs-tts-service

# 创建虚拟环境
python -m venv tts-env
tts-env\Scripts\activate

# 安装
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
```

验证：

```bash
python -c "import torch; print('CUDA:', torch.cuda.is_available())"
# 应输出：CUDA: True
```

## 三、启动服务

```bash
tts-env\Scripts\activate
python server.py --model-path ./models/higgs-audio-v3-tts-4b --host 127.0.0.1 --port 8100
```

看到 `Uvicorn running on http://127.0.0.1:8100` 即成功。

## 四、测试

```bash
python quick_tts.py "你好世界，这是本地语音合成测试"
```

加效果：

```bash
python quick_tts.py "太厉害了哈哈哈" --emotion enthusiasm --sfx laughter
python quick_tts.py "从前有座山" --style whispering --slow
```

## 五、可调参数

| 参数 | 说明 |
|------|------|
| `--emotion` | elation / sadness / enthusiasm / fear / surprise 等 21 种 |
| `--style` | whispering / shouting / singing |
| `--sfx` | laughter / sigh / sneeze / cough 等 9 种 |
| `--slow / --fast` | 语速控制 |
| `--pitch high / low` | 音高控制 |
| `--temp 0.0-2.0` | 随机性（默认 1.0） |
| `-r audio.wav --ref-text "内容"` | 语音克隆 |
| `--play` | 生成后自动播放 |

详细运行 `python quick_tts.py --help`
