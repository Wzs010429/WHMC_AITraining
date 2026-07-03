# Higgs Audio v3 TTS — 教师本地部署指南

> 目标机器：Windows + NVIDIA A4000（16GB 显存）
> 前提：模型文件已由管理员预先拷贝到本机

---

## 一、确认文件就绪

先检查模型文件夹是否存在，管理员拷贝后路径类似：

```
D:\ai-models\higgs-audio-v3-tts-4b\
├── model.safetensors        ← 8.7GB
├── config.json
├── tokenizer.json
└── tokenizer_config.json
```

如果还没有模型文件，联系管理员获取。

---

## 二、安装 Python 环境

### 2.1 安装 Miniconda（如果没有 Python）

1. 下载：https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Windows-x86_64.exe
2. 安装时勾选 **"Add Miniconda3 to PATH"**
3. 完成后打开 **Anaconda Prompt**（从开始菜单）

### 2.2 拉取代码

```bash
cd D:\
git clone https://github.com/Wzs010429/WHMC_AITraining.git
cd WHMC_AITraining\demo\higgs-tts-service
```

> 如果 git 不可用，让管理员拷贝整个 `higgs-tts-service` 文件夹到本机。

### 2.3 创建虚拟环境

```bash
python -m venv tts-env
tts-env\Scripts\activate
```

看到命令提示符前面出现 `(tts-env)` 就成功了。

---

## 三、安装依赖

```bash
# 全部走清华镜像（校内网快）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# CUDA 版 PyTorch（A4000 需要）
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
```

安装完成后验证 GPU 可用：

```bash
python -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0))"
```

应该输出：
```
CUDA: True
GPU: NVIDIA RTX A4000
```

---

## 四、启动服务

```bash
# 假设模型在 D:\ai-models\higgs-audio-v3-tts-4b\
# 把路径换成你实际的模型位置

python server.py --model-path D:\ai-models\higgs-audio-v3-tts-4b --host 127.0.0.1 --port 8100
```

看到以下输出表示成功：

```
✅ SGLang-Omni 就绪
👷 Worker 已启动
INFO:     Uvicorn running on http://127.0.0.1:8100
```

---

## 五、测试

浏览器打开 http://127.0.0.1:8100/docs → 找到 `POST /v1/audio/speech` → "Try it out" → 输入：

```json
{
  "input": "你好！欢迎使用AI语音合成。"
}
```

点 Execute，等几秒，下载返回的 WAV 文件播放试听。

或者用命令行：

```bash
python test_client.py --url http://127.0.0.1:8100 --text "你好世界，这是本地TTS测试"
```

---

## 六、在代码中调用

```python
import time, base64, requests

# 提交 TTS 任务
r = requests.post("http://127.0.0.1:8100/v1/audio/speech", json={
    "input": "春天来了，花儿开了，小鸟在枝头唱歌。"
})
job_id = r.json()["job_id"]

# 等待完成
while True:
    j = requests.get(f"http://127.0.0.1:8100/v1/jobs/{job_id}").json()
    if j["status"] == "completed":
        audio = base64.b64decode(j["result"]["audio_b64_json"])
        with open("output.wav", "wb") as f:
            f.write(audio)
        print(f"✅ {j['result']['duration_s']}秒音频已保存")
        break
    time.sleep(1)
```

---

## 七、内联控制标签

在文本中插入标签控制语音表现：

```python
# 情感 + 笑声
"input": "<|emotion:enthusiasm|>哇，太棒了！<|sfx:laughter|>哈哈，真好玩！"

# 语速 + 风格
"input": "<|prosody:speed_slow|>从前有座山…<|prosody:speed_fast|>然后发生了什么？"

# 语音克隆
"input": "现在用克隆的声音说话。",
"reference_audio_b64": "base64编码的WAV音频...",
"reference_text": "参考音频的文字内容"
```

| 类别 | 可用标签 |
|------|---------|
| 情感 | `<\|emotion:joy\|>` `<\|emotion:sadness\|>` `<\|emotion:fear\|>` `<\|emotion:enthusiasm\|>` `<\|emotion:amusement\|>` `<\|emotion:surprise\|>` |
| 音效 | `<\|sfx:laughter\|>` `<\|sfx:sigh\|>` `<\|sfx:sneeze\|>` |
| 语速 | `<\|prosody:speed_slow\|>` `<\|prosody:speed_fast\|>` |
| 音高 | `<\|prosody:pitch_high\|>` `<\|prosody:pitch_low\|>` |
| 停顿 | `<\|prosody:long_pause\|>` `<\|prosody:short_pause\|>` |

---

## 八、常见问题

### Q: 显存不够？

A4000 有 16GB，Higgs v3 需要约 12GB，完全够用。如果同时跑其他程序导致不够：

```bash
# 设置环境变量限制显存
set PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128
python server.py ...
```

### Q: 端口被占用？

换一个端口：
```bash
python server.py --model-path D:\ai-models\higgs-audio-v3-tts-4b --host 127.0.0.1 --port 8200
```

### Q: 想开机自启？

创建 `start_tts.bat` 放到桌面：
```bat
@echo off
cd /d D:\WHMC_AITraining\demo\higgs-tts-service
call tts-env\Scripts\activate
python server.py --model-path D:\ai-models\higgs-audio-v3-tts-4b --host 127.0.0.1 --port 8100
pause
```

### Q: 局域网其他电脑能用吗？

把 `--host 127.0.0.1` 改成 `--host 0.0.0.0`，关闭 Windows 防火墙对应端口，其他电脑就能通过 IP 访问。
