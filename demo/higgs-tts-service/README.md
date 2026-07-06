# Higgs Audio v3 TTS 推理服务

面向 WHMC 工作坊的 OpenAI 兼容 TTS API。基于 Boson AI Higgs Audio v3（4B 参数），100+ 语言、零样本语音克隆、情感控制。

> 服务端口：`8100` | 推理后端：纯 `transformers`

## 模型信息

| 属性 | 说明 |
|------|------|
| 模型 | `bosonai/higgs-audio-v3-tts-4b`（Boson AI） |
| 参数 | 4B（LLM + Audio Codec） |
| 语言 | 100+ 语言，中文优秀 |
| 语音克隆 | ✅ 零样本（给一段 WAV 即可克隆） |
| 情感控制 | 21 种情感标签 + 3 种风格 + 8 种 SFX |
| 推理后端 | 纯 `transformers` |
| API | OpenAI 兼容 `/v1/audio/speech` + 作业队列 |
| 许可 | 非商业研究 |

## 硬件要求

| 配置 | 推荐 |
|------|------|
| GPU | **L20 48GB** / RTX 4090 / A100 |
| 显存 | BF16 ~12GB，推荐 24GB+ |
| RAM | 32GB+ |
| 存储 | 模型 ~8GB |

---

## 🚀 服务器部署

### 1. 克隆 + 安装

```bash
cd ~/WHMC_AITraining/demo/higgs-tts-service
python3 -m venv tts-env
source tts-env/bin/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
```

### 2. 下载模型（二选一）

```bash
# A. HuggingFace 镜像
export HF_ENDPOINT=https://hf-mirror.com
huggingface-cli download bosonai/higgs-audio-v3-tts-4b --local-dir ./models/higgs-audio-v3-tts-4b

# B. 手动拷贝（U盘/SCP 传到服务器）
# 把模型文件放到 ./models/higgs-audio-v3-tts-4b/
```

### 3. 启动

```bash
tmux new -s tts
source tts-env/bin/activate
python server.py --model-path ./models/higgs-audio-v3-tts-4b --host 0.0.0.0 --port 8100
# Ctrl+B D 断开
```

---

## 📖 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/audio/speech` | POST | 提交 TTS 作业（异步） |
| `/v1/audio/speech?sync=true` | POST | 同步模式 |
| `/v1/jobs/{job_id}` | GET | 查询作业（完成后返回音频） |
| `/v1/queue` | GET | 队列看板 |
| `/health` | GET | 健康检查 |

---

## 🎤 内联控制标签

在 `input` 文本中直接插入：

| 类别 | 标签 |
|------|------|
| **情感** | `<\|emotion:joy\|>` `<\|emotion:sadness\|>` `<\|emotion:fear\|>` `<\|emotion:enthusiasm\|>` `<\|emotion:amusement\|>` `<\|emotion:awe\|>` `<\|emotion:surprise\|>` `<\|emotion:curiosity\|>` |
| **风格** | `<\|style:whispering\|>` `<\|style:shouting\|>` `<\|style:singing\|>` |
| **SFX** | `<\|sfx:laughter\|>` `<\|sfx:sigh\|>` `<\|sfx:sneeze\|>` `<\|sfx:cough\|>` |
| **语速** | `<\|prosody:speed_slow\|>` `<\|prosody:speed_fast\|>` |
| **音高** | `<\|prosody:pitch_high\|>` `<\|prosody:pitch_low\|>` |
| **停顿** | `<\|prosody:long_pause\|>` `<\|prosody:short_pause\|>` |

---

## 调用示例

### Python

```python
import time, base64, requests

BASE = "http://10.100.35.254:8100"

# 普通 TTS
r = requests.post(f"{BASE}/v1/audio/speech", json={
    "input": "你好！欢迎来到AI素养工作坊。"
})
job_id = r.json()["job_id"]

# 带情感
r = requests.post(f"{BASE}/v1/audio/speech", json={
    "input": "<|emotion:enthusiasm|>哇！这个AI太厉害了！<|sfx:laughter|>哈哈，真有意思！"
})

# 语音克隆
with open("reference.wav", "rb") as f:
    ref_b64 = base64.b64encode(f.read()).decode()
r = requests.post(f"{BASE}/v1/audio/speech", json={
    "input": "现在我用克隆的声音说话。",
    "reference_audio_b64": ref_b64,
    "reference_text": "参考音频的文字内容"
})

# 轮询
while True:
    j = requests.get(f"{BASE}/v1/jobs/{job_id}").json()
    if j["status"] == "completed":
        audio = base64.b64decode(j["result"]["audio_b64_json"])
        with open("output.wav", "wb") as f: f.write(audio)
        print(f"✅ {j['result']['duration_s']}s 音频已保存")
        break
    elif j["status"] == "failed":
        print(f"❌ {j['error']}"); break
    time.sleep(1)
```

### curl

```bash
# 提交
JOB_ID=$(curl -s -X POST http://10.100.35.254:8100/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"你好世界"}' | python3 -c "import json,sys;print(json.load(sys.stdin)['job_id'])")

# 轮询 + 保存
while true; do
  STATUS=$(curl -s http://10.100.35.254:8100/v1/jobs/$JOB_ID | python3 -c "import json,sys;print(json.load(sys.stdin)['status'])")
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 1
done
curl -s http://10.100.35.254:8100/v1/jobs/$JOB_ID | python3 -c "
import json,base64,sys
d=json.load(sys.stdin)['result']
open('out.wav','wb').write(base64.b64decode(d['audio_b64_json']))
print(f'✅ {d[\"duration_s\"]}s')
"
```
