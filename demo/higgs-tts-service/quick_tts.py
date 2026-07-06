"""
一键 TTS：提交 + 等待 + 保存 + 自动播放
用法：
  python quick_tts.py "你好世界"
  python quick_tts.py "春天来了花儿开了" --emotion joy
  python quick_tts.py "从前有座山" --slow
  python quick_tts.py "哈哈哈" --sfx laughter
"""
import base64, json, sys, time, argparse, subprocess, os
import requests

BASE = os.environ.get("TTS_URL", "http://10.100.35.254:8100")

parser = argparse.ArgumentParser(description="一键 TTS")
parser.add_argument("text", help="要合成的文本")
parser.add_argument("--url", default=BASE, help=f"TTS 服务地址（默认 {BASE}）")
parser.add_argument("--temp", type=float, default=1.0, help="随机性 (0-2)")
parser.add_argument("--emotion", default=None, help="情感: joy, sadness, enthusiasm, amusement, fear, surprise")
parser.add_argument("--sfx", default=None, help="音效: laughter, sigh, sneeze")
parser.add_argument("--slow", action="store_true", help="慢速朗读")
parser.add_argument("--fast", action="store_true", help="快速朗读")
parser.add_argument("--output", default="tts_output.wav", help="输出文件名")
parser.add_argument("--play", action="store_true", default=True, help="生成后自动播放")
args = parser.parse_args()

# 构建带标签的文本
text = args.text
if args.emotion:
    text = f"<|emotion:{args.emotion}|>" + text
if args.sfx:
    text += f"<|sfx:{args.sfx}|>"
if args.slow:
    text = "<|prosody:speed_slow|>" + text
if args.fast:
    text = "<|prosody:speed_fast|>" + text

print(f"Text : {text[:80]}...")
print(f"Temp : {args.temp}")
print()

# 提交
r = requests.post(f"{args.url}/v1/audio/speech", json={
    "input": text,
    "temperature": args.temp,
}, timeout=10)
job = r.json()
job_id = job["job_id"]
print(f"job_id: {job_id}  position: {job.get('position','?')}")

# 轮询
start = time.time()
while True:
    r = requests.get(f"{args.url}/v1/jobs/{job_id}", timeout=10)
    j = r.json()
    if j["status"] == "completed":
        audio = base64.b64decode(j["result"]["audio_b64_json"])
        with open(args.output, "wb") as f:
            f.write(audio)
        elapsed = time.time() - start
        print(f"Done: {j['result']['duration_s']}s audio | "
              f"inference {j['result']['elapsed_s']}s | "
              f"total wait {elapsed:.0f}s")
        print(f"Saved: {args.output}")

        # 自动播放
        if args.play:
            os.startfile(args.output)
        break
    elif j["status"] == "failed":
        print(f"FAIL: {j.get('error')}")
        break
    elapsed = int(time.time() - start)
    print(f"\r  {j['status']}... {elapsed}s", end="")
    time.sleep(1)
