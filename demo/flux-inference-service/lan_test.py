"""
局域网 API 测试脚本
====================
在你当前电脑上运行，测试同一局域网内的 FLUX 推理服务器。

用法：
  python lan_test.py                                    # 文生图测试
  python lan_test.py --url http://10.x.x.x:5500          # 指定服务器
  python lan_test.py --image ./cat.jpg                   # 图生图编辑测试
  python lan_test.py --image https://example.com/pic.jpg # 图生图（URL）
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
    print("❌ 请先安装 requests：pip install requests")
    sys.exit(1)


def test_health(base_url: str):
    """1. 健康检查"""
    print("=" * 50)
    print("1️⃣  健康检查")
    print("=" * 50)
    try:
        r = requests.get(f"{base_url}/health", timeout=10)
        d = r.json()
        print(f"   状态    : {d['status']}")
        print(f"   模型    : {d['model']}")
        print(f"   GPU     : {d.get('gpu_name', 'N/A')}")
        print(f"   排队    : {d.get('queue_length', 0)} 个作业")
        print(f"   已完成  : {d.get('total_completed', 0)} 个")
        return d["status"] in ("healthy", "degraded")
    except requests.exceptions.ConnectionError:
        print(f"   ❌ 无法连接！请检查 IP 和端口是否正确")
        print(f"   💡 提示：服务器上执行 python server.py --host 0.0.0.0 --port 5500")
        return False
    except Exception as e:
        print(f"   ❌ {e}")
        return False


def test_submit(base_url: str, prompt: str, size: str, image_path: str = None) -> str | None:
    """2. 提交作业（支持文生图/图生图）"""
    print("\n" + "=" * 50)
    print("2️⃣  提交作业")
    print("=" * 50)
    print(f"   Prompt : {prompt}")
    print(f"   Size   : {size}")

    body = {"prompt": prompt, "size": size, "response_format": "b64_json"}

    # 图生图模式
    if image_path:
        if image_path.startswith("http://") or image_path.startswith("https://"):
            body["image"] = image_path
            print(f"   模式    : 🎨 图生图（URL）")
        else:
            with open(image_path, "rb") as f:
                body["image"] = base64.b64encode(f.read()).decode()
            print(f"   模式    : 🎨 图生图（{Path(image_path).name}）")
    else:
        print(f"   模式    : 📝 文生图")

    try:
        r = requests.post(
            f"{base_url}/v1/images/generations",
            json=body,
            timeout=10,
        )
        d = r.json()
        job_id = d["job_id"]
        print(f"   job_id : {job_id}")
        print(f"   位置   : 第 {d['position']} 位")
        print(f"   预计等待: ~{d.get('estimated_wait_seconds', '?')}s")
        return job_id
    except Exception as e:
        print(f"   ❌ {e}")
        return None


def test_poll(base_url: str, job_id: str, timeout: int = 300) -> bool:
    """3. 轮询等待完成"""
    print("\n" + "=" * 50)
    print("3️⃣  等待生成…")
    print("=" * 50)

    start = time.time()
    dots = 0
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{base_url}/v1/jobs/{job_id}", timeout=10)
            d = r.json()
            status = d["status"]

            if status == "completed":
                result = d["result"]
                print(f"\n   ✅ 生成完成！")
                print(f"   推理耗时 : {result['elapsed']}s")
                print(f"   总等待   : {time.time() - start:.0f}s")
                print(f"   种子     : {result['seed']}")
                print(f"   尺寸     : {result['size']}")

                # 保存图片
                if result.get("b64_json"):
                    img_bytes = base64.b64decode(result["b64_json"])
                    out_name = f"lan_test_output.png"
                    Path(out_name).write_bytes(img_bytes)
                    print(f"   💾 已保存 : {out_name} ({len(img_bytes)/1024:.0f} KB)")
                return True

            elif status == "queued":
                dots = (dots + 1) % 30
                print(f"\r   ⏳ 排队中… 位置 #{d.get('position', '?')} {'·' * dots}", end="")
                time.sleep(2)

            elif status == "processing":
                dots = (dots + 1) % 30
                elapsed = int(time.time() - start)
                print(f"\r   🎨 生成中… 已等 {elapsed}s {'·' * dots}", end="")
                time.sleep(3)

            elif status == "failed":
                print(f"\n   ❌ 作业失败：{d.get('error')}")
                return False

            else:
                print(f"\n   ⚠️ 未知状态：{status}")
                time.sleep(2)

        except Exception as e:
            print(f"\n   ⚠️ 轮询出错：{e}，重试…")
            time.sleep(2)

    print(f"\n   ❌ 超时（>{timeout}s）")
    return False


def test_queue(base_url: str):
    """4. 队列状态"""
    print("\n" + "=" * 50)
    print("4️⃣  队列看板")
    print("=" * 50)
    try:
        r = requests.get(f"{base_url}/v1/queue", headers={"Accept": "application/json"}, timeout=10)
        d = r.json()
        print(f"   排队中   : {d['queue_length']} 个")
        print(f"   平均耗时 : {d['avg_generation_seconds']}s")
        print(f"   累计完成 : {d['total_completed']} 个")
        cur = d.get("current_job")
        if cur:
            print(f"   当前作业 : {cur['prompt'][:50]}...")
            print(f"   已耗时   : {cur.get('elapsed', 0)}s")
        else:
            print(f"   当前作业 : 无（空闲）")
        print(f"\n   🌐 看板地址：{base_url}/v1/queue")
    except Exception as e:
        print(f"   ⚠️ {e}")


def main():
    parser = argparse.ArgumentParser(description="FLUX API 局域网测试")
    parser.add_argument("--url", default="http://localhost:5500", help="服务器地址（默认 localhost:5500）")
    parser.add_argument("--prompt", default="一只可爱的橘猫坐在窗台上看月亮，绘本插画风格，温暖色调，Chinese illustration")
    parser.add_argument("--size", default="512x512", help="图片尺寸（512x512 快一些，1024x1024 质量更高）")
    parser.add_argument("--image", default=None, help="参考图路径或 URL（提供则进入图生图编辑模式）")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    print()
    print("🧪 FLUX API 局域网连通性测试")
    print(f"📍 服务器：{base_url}")
    print(f"🖼️  Prompt：{args.prompt}")
    print(f"📐 Size   ：{args.size}")
    print()

    # 1. 健康检查
    if not test_health(base_url):
        print("\n" + "=" * 50)
        print("❌ 健康检查失败，请确认：")
        print("   1. 服务器已启动：python server.py --host 0.0.0.0 --port 5500")
        print("   2. 防火墙已放行端口 5500")
        print("   3. 两台电脑在同一局域网")
        print("   4. IP 地址正确（ifconfig 查看）")
        print("=" * 50)
        return

    # 2. 提交作业
    job_id = test_submit(base_url, args.prompt, args.size, args.image)
    if not job_id:
        return

    # 3. 轮询
    success = test_poll(base_url, job_id)

    # 4. 队列
    test_queue(base_url)

    # 结果
    print("\n" + "=" * 50)
    if success:
        print("🎉 测试通过！API 工作正常，图片已保存为 lan_test_output.png")
    else:
        print("⚠️  测试未通过，请检查服务器日志")
    print("=" * 50)
    print()


if __name__ == "__main__":
    main()
