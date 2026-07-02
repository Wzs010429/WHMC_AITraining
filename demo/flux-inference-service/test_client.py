"""
FLUX.2-klein-9B 推理服务 — 测试客户端（v2 任务队列版）
======================================================
用法：
  python test_client.py                              # 异步作业模式（默认）
  python test_client.py --sync                       # 同步模式
  python test_client.py --url http://10.x.x.x:5500   # 指定服务器
  python test_client.py --batch                      # 批量提交测试
"""

import argparse
import base64
import json
import time
from pathlib import Path

import requests


TEST_PROMPTS = [
    "一只橘猫坐在窗台上看月亮，绘本插画风格，温暖色调",
    "春天的花园里，孩子们在草地上读书，卡通风格",
    "月光洒在湖面上，远山朦胧，中国水墨画风格",
]


def test_health(base_url: str) -> bool:
    print("=" * 60)
    print("1️⃣  健康检查：GET /health")
    print("=" * 60)
    try:
        resp = requests.get(f"{base_url}/health", timeout=10)
        data = resp.json()
        print(f"   状态：{data.get('status')}")
        print(f"   GPU：{data.get('gpu_name')}")
        print(f"   排队：{data.get('queue_length')} 个作业")
        print(f"   已完成：{data.get('total_completed')} 个")
        print(f"   运行时长：{data.get('uptime_seconds', 0):.0f}s")
        print()
        return data.get("status") in ("healthy", "degraded")
    except Exception as e:
        print(f"   ❌ 失败：{e}\n")
        return False


def test_list_models(base_url: str) -> bool:
    print("=" * 60)
    print("2️⃣  模型列表：GET /v1/models")
    print("=" * 60)
    try:
        resp = requests.get(f"{base_url}/v1/models", timeout=10)
        for m in resp.json().get("data", []):
            print(f"   📦 {m['id']}")
        print()
        return True
    except Exception as e:
        print(f"   ❌ 失败：{e}\n")
        return False


def test_submit_job(base_url: str, prompt: str, size: str = "1024x1024") -> str | None:
    """提交异步作业，返回 job_id"""
    print("=" * 60)
    print("3️⃣  提交作业：POST /v1/images/generations")
    print("=" * 60)
    print(f"   Prompt: {prompt}")
    print(f"   Size: {size}")
    try:
        resp = requests.post(
            f"{base_url}/v1/images/generations",
            json={
                "model": "black-forest-labs/FLUX.2-klein-9B",
                "prompt": prompt,
                "n": 1,
                "size": size,
                "response_format": "b64_json",
            },
            timeout=10,
        )
        data = resp.json()
        job_id = data.get("job_id")
        print(f"   ✅ 作业已提交")
        print(f"   job_id: {job_id}")
        print(f"   排队位置: {data.get('position')}")
        print(f"   队列长度: {data.get('queue_length')}")
        print(f"   预计等待: {data.get('estimated_wait_seconds')}s")
        print()
        return job_id
    except Exception as e:
        print(f"   ❌ 失败：{e}\n")
        return None


def test_poll_job(base_url: str, job_id: str, timeout: int = 180) -> bool:
    """轮询作业直到完成"""
    print("=" * 60)
    print(f"4️⃣  轮询作业：GET /v1/jobs/{job_id}")
    print("=" * 60)

    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{base_url}/v1/jobs/{job_id}", timeout=10)
            data = resp.json()
            status = data["status"]

            if status == "queued":
                elapsed = int(time.time() - start)
                print(f"   ⏳ 排队中… 位置 #{data.get('position')}（已等 {elapsed}s）")
                time.sleep(2)
                continue

            elif status == "processing":
                elapsed = int(time.time() - start)
                print(f"   🎨 生成中…（已等 {elapsed}s）")
                time.sleep(3)
                continue

            elif status == "completed":
                result = data.get("result", {})
                elapsed_total = time.time() - start
                print(f"   ✅ 生成完成！")
                print(f"   总等待: {elapsed_total:.0f}s")
                print(f"   推理耗时: {result.get('elapsed')}s")
                print(f"   种子: {result.get('seed')}")
                print(f"   尺寸: {result.get('size')}")

                # 保存图片
                if result.get("b64_json"):
                    img_bytes = base64.b64decode(result["b64_json"])
                    out_path = Path("test_output_async.png")
                    out_path.write_bytes(img_bytes)
                    print(f"   💾 已保存：{out_path}（{len(img_bytes)/1024:.0f}KB）")
                print()
                return True

            elif status == "failed":
                print(f"   ❌ 作业失败：{data.get('error')}")
                return False

            elif status == "cancelled":
                print(f"   🚫 作业已取消")
                return False

        except Exception as e:
            print(f"   ⚠️ 轮询出错：{e}，重试…")
            time.sleep(2)

    print(f"   ❌ 超时（>{timeout}s）\n")
    return False


def test_sync_generate(base_url: str, prompt: str, size: str = "1024x1024") -> bool:
    """同步模式生成（?sync=true）"""
    print("=" * 60)
    print("5️⃣  同步生成：POST /v1/images/generations?sync=true")
    print("=" * 60)
    print(f"   Prompt: {prompt}")
    try:
        start = time.time()
        resp = requests.post(
            f"{base_url}/v1/images/generations?sync=true",
            json={
                "model": "black-forest-labs/FLUX.2-klein-9B",
                "prompt": prompt,
                "n": 1,
                "size": size,
                "response_format": "b64_json",
            },
            timeout=180,
        )
        elapsed = time.time() - start

        if resp.status_code == 429:
            print(f"   ⚠️ GPU 正忙，跳过同步测试（这是正常的）\n")
            return "skipped"

        data = resp.json()
        images = data.get("data", [])
        print(f"   ✅ 生成成功（{elapsed:.1f}s）")
        for i, img in enumerate(images):
            if img.get("b64_json"):
                img_bytes = base64.b64decode(img["b64_json"])
                out_path = Path(f"test_output_sync_{i+1}.png")
                out_path.write_bytes(img_bytes)
                print(f"   💾 {out_path}（{len(img_bytes)/1024:.0f}KB）")
        print()
        return True
    except requests.exceptions.Timeout:
        print(f"   ❌ 超时\n")
        return False
    except Exception as e:
        print(f"   ❌ 失败：{e}\n")
        return False


def test_queue_dashboard(base_url: str) -> bool:
    """测试队列看板"""
    print("=" * 60)
    print("6️⃣  队列看板：GET /v1/queue")
    print("=" * 60)
    try:
        # JSON 模式
        resp = requests.get(
            f"{base_url}/v1/queue",
            headers={"Accept": "application/json"},
            timeout=10,
        )
        data = resp.json()
        print(f"   队列长度: {data['queue_length']}")
        print(f"   平均耗时: {data['avg_generation_seconds']}s")
        print(f"   已完成: {data['total_completed']}")
        if data["current_job"]:
            print(f"   当前作业: {data['current_job']['prompt'][:50]}...")
        else:
            print(f"   当前作业: 无（空闲）")
        print(f"   🌐 HTML 看板: {base_url}/v1/queue")
        print()
        return True
    except Exception as e:
        print(f"   ❌ 失败：{e}\n")
        return False


def test_batch_submit(base_url: str) -> bool:
    """批量提交"""
    print("=" * 60)
    print("7️⃣  批量提交：POST /v1/images/generations/batch")
    print("=" * 60)
    try:
        resp = requests.post(
            f"{base_url}/v1/images/generations/batch",
            json=[
                {"prompt": "一只白色小猫在草地上玩耍，卡通风格", "size": "512x512"},
                {"prompt": "夕阳下的海滩，油画风格", "size": "512x512"},
            ],
            timeout=10,
        )
        data = resp.json()
        print(f"   已提交: {len(data.get('jobs', []))} 个作业")
        for j in data.get("jobs", []):
            print(f"   📝 {j['job_id']} — {j['prompt'][:40]}...")
        print()
        return True
    except Exception as e:
        print(f"   ❌ 失败：{e}\n")
        return False


def test_cancel_job(base_url: str, job_id: str) -> bool:
    """测试取消排队中的作业"""
    print("=" * 60)
    print(f"8️⃣  取消作业：DELETE /v1/jobs/{job_id}")
    print("=" * 60)
    try:
        resp = requests.delete(f"{base_url}/v1/jobs/{job_id}", timeout=10)
        data = resp.json()
        print(f"   状态: {data.get('status')}")
        print(f"   消息: {data.get('message')}")
        print()
        return True
    except Exception as e:
        print(f"   ❌ 失败：{e}\n")
        return False


# ═════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="FLUX.2-klein-9B 推理服务测试客户端（v2）")
    parser.add_argument("--url", default="http://localhost:5500")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--sync", action="store_true", help="使用同步模式")
    parser.add_argument("--batch", action="store_true", help="批量提交测试")
    parser.add_argument("--skip-generate", action="store_true")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    prompt = args.prompt or TEST_PROMPTS[0]

    print()
    print("🧪 FLUX.2-klein-9B 推理服务 连通性测试（v2 任务队列）")
    print(f"📍 目标：{base_url}")
    print()

    results = []

    # 1. 健康检查
    results.append(("健康检查", test_health(base_url)))

    # 2. 模型列表
    results.append(("模型列表", test_list_models(base_url)))

    # 3. 队列看板
    results.append(("队列看板", test_queue_dashboard(base_url)))

    if not args.skip_generate:
        if args.sync:
            # 同步模式
            results.append(("同步生成", test_sync_generate(base_url, prompt, args.size)))
        else:
            # 异步模式（默认）
            if args.batch:
                results.append(("批量提交", test_batch_submit(base_url)))

            job_id = test_submit_job(base_url, prompt, args.size)
            if job_id:
                results.append(("作业提交", True))
                results.append(("轮询完成", test_poll_job(base_url, job_id)))

                # 测试取消（提交一个快速作业然后立即取消）
                cancel_jid = test_submit_job(base_url, TEST_PROMPTS[2], "512x512")
                if cancel_jid:
                    results.append(("取消作业", test_cancel_job(base_url, cancel_jid)))
            else:
                results.append(("作业提交", False))

    # 汇总
    print("=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    all_pass = True
    for name, status in results:
        if status == True:
            icon = "✅"
        elif status == "skipped":
            icon = "⚠️"
        else:
            icon = "❌"
            all_pass = False
        print(f"   {icon}  {name}")

    print()
    if all_pass:
        print("🎉 全部测试通过！")
    else:
        print("⚠️  部分测试未通过，请检查服务日志。")

    print(f"\n📖 API 文档：{base_url}/docs")
    print(f"📊 队列看板：{base_url}/v1/queue")
    print()


if __name__ == "__main__":
    main()
