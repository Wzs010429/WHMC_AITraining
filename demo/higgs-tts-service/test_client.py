"""
Higgs Audio v3 TTS 连通性测试
===============================
用法：
  python test_client.py --url http://10.100.35.254:8100
  python test_client.py --url http://10.100.35.254:8100 --text "你好世界"
  python test_client.py --url http://10.100.35.254:8100 --clone ./reference.wav --ref-text "参考文本"
"""

import argparse
import base64
import json
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ pip install requests")
    sys.exit(1)


def test_health(base_url: str) -> bool:
    print("=" * 50)
    print("1️⃣  健康检查")
    print("=" * 50)
    try:
        r = requests.get(f"{base_url}/health", timeout=10)
        d = r.json()
        print(f"   状态    : {d['status']}")
        print(f"   模型    : {d['model']}")
        print(f"   SGLang  : {'✅' if d.get('sglang_ok') else '❌'}")
        print(f"   排队    : {d.get('queue_length', 0)} 个")
        print(f"   已完成  : {d.get('total_completed', 0)} 个")
        return d["status"] in ("healthy", "degraded")
    except requests.exceptions.ConnectionError:
        print(f"   ❌ 无法连接！请确认：python server.py --host 0.0.0.0 --port 8100")
        return False
    except Exception as e:
        print(f"   ❌ {e}")
        return False


def test_submit(base_url: str, text: str, clone_path: str = None, ref_text: str = None) -> str | None:
    print("\n" + "=" * 50)
    print("2️⃣  提交 TTS 作业")
    print("=" * 50)
    print(f"   文本    : {text[:60]}...")

    body = {"input": text, "response_format": "wav"}

    if clone_path:
        with open(clone_path, "rb") as f:
            body["reference_audio_b64"] = base64.b64encode(f.read()).decode()
        if ref_text:
            body["reference_text"] = ref_text
        print(f"   模式    : 🎤 语音克隆 ({Path(clone_path).name})")

    try:
        r = requests.post(f"{base_url}/v1/audio/speech", json=body, timeout=10)
        d = r.json()
        job_id = d["job_id"]
        print(f"   job_id  : {job_id}")
        print(f"   位置    : #{d.get('position', '?')}")
        print(f"   预计等待: ~{d.get('estimated_wait_s', '?')}s")
        return job_id
    except Exception as e:
        print(f"   ❌ {e}")
        return None


def test_poll(base_url: str, job_id: str, timeout: int = 120) -> bool:
    print("\n" + "=" * 50)
    print("3️⃣  等待合成…")
    print("=" * 50)

    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{base_url}/v1/jobs/{job_id}", timeout=10)
            d = r.json()
            status = d["status"]

            if status == "completed":
                result = d["result"]
                print(f"\n   ✅ 合成完成！")
                print(f"   推理耗时 : {result['elapsed_s']}s")
                print(f"   音频时长 : {result['duration_s']}s")
                print(f"   总等待   : {time.time() - start:.0f}s")

                if result.get("audio_b64_json"):
                    audio_bytes = base64.b64decode(result["audio_b64_json"])
                    out = Path(f"tts_output.wav")
                    out.write_bytes(audio_bytes)
                    print(f"   💾 已保存 : {out} ({len(audio_bytes)/1024:.0f}KB)")
                return True

            elif status == "queued":
                elapsed = int(time.time() - start)
                print(f"\r   ⏳ 排队中… #{d.get('position','?')} 已等{elapsed}s", end="")
                time.sleep(1)
            elif status == "processing":
                elapsed = int(time.time() - start)
                print(f"\r   🔊 合成中… 已等{elapsed}s", end="")
                time.sleep(1)
            elif status == "failed":
                print(f"\n   ❌ {d.get('error')}")
                return False
        except Exception as e:
            time.sleep(2)
    print(f"\n   ❌ 超时")
    return False


def main():
    parser = argparse.ArgumentParser(description="Higgs Audio v3 TTS 测试")
    parser.add_argument("--url", default="http://localhost:8100")
    parser.add_argument("--text", default="你好！欢迎使用Higgs Audio v3语音合成服务，今天天气真好呀！")
    parser.add_argument("--clone", default=None, help="参考音频路径（语音克隆）")
    parser.add_argument("--ref-text", default=None, help="参考音频文本内容")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    print()
    print("🎙️  Higgs Audio v3 TTS 测试")
    print(f"📍 {base_url}")
    print()

    if not test_health(base_url):
        return

    job_id = test_submit(base_url, args.text, args.clone, args.ref_text)
    if not job_id:
        return

    success = test_poll(base_url, job_id)

    print()
    if success:
        print("🎉 测试通过！音频已保存为 tts_output.wav")
    else:
        print("⚠️  未通过")


if __name__ == "__main__":
    main()
