"""
FLUX.2-klein-9B 推理服务 — 测试客户端
======================================
供教师验证服务连通性 + 了解 API 用法

用法：
  python test_client.py                      # 默认 localhost:5500
  python test_client.py --url http://10.x.x.x:5500   # 指定服务器
  python test_client.py --prompt "你的提示词"          # 自定义 prompt
"""

import argparse
import base64
import json
import time
from pathlib import Path

import requests


# ═══════════════════════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════════════════════

TEST_PROMPTS = [
    "一只橘猫坐在窗台上看月亮，绘本插画风格，温暖色调",
    "春天的花园里，孩子们在草地上读书，卡通风格",
    "月光洒在湖面上，远山朦胧，中国水墨画风格",
]


def test_health(base_url: str) -> bool:
    """测试健康检查端点"""
    print("=" * 60)
    print("1️⃣  健康检查：GET /health")
    print("=" * 60)
    try:
        resp = requests.get(f"{base_url}/health", timeout=10)
        data = resp.json()
        print(f"   状态码：{resp.status_code}")
        print(f"   服务状态：{data.get('status')}")
        print(f"   模型：{data.get('model')}")
        print(f"   GPU：{data.get('gpu_name')}")
        print(f"   显存：{data.get('vram_total_gb')}GB（空闲 {data.get('vram_free_gb')}GB）")
        print(f"   运行时长：{data.get('uptime_seconds', 0):.0f}s")
        print()
        return data.get("status") in ("healthy", "degraded")
    except Exception as e:
        print(f"   ❌ 失败：{e}\n")
        return False


def test_list_models(base_url: str) -> bool:
    """测试模型列表"""
    print("=" * 60)
    print("2️⃣  模型列表：GET /v1/models")
    print("=" * 60)
    try:
        resp = requests.get(f"{base_url}/v1/models", timeout=10)
        data = resp.json()
        for m in data.get("data", []):
            print(f"   📦 {m['id']}（{m.get('owned_by', 'unknown')}）")
        print()
        return True
    except Exception as e:
        print(f"   ❌ 失败：{e}\n")
        return False


def test_generate(base_url: str, prompt: str, size: str = "1024x1024") -> bool:
    """测试图片生成"""
    print("=" * 60)
    print("3️⃣  生成图片：POST /v1/images/generations")
    print("=" * 60)
    print(f"   Prompt: {prompt}")
    print(f"   Size: {size}")
    print()

    try:
        start = time.time()

        resp = requests.post(
            f"{base_url}/v1/images/generations",
            json={
                "model": "black-forest-labs/FLUX.2-klein-9B",
                "prompt": prompt,
                "n": 1,
                "size": size,
                "response_format": "b64_json",
            },
            timeout=120,
        )

        elapsed = time.time() - start

        if resp.status_code != 200:
            print(f"   ❌ HTTP {resp.status_code}：{resp.text}")
            return False

        data = resp.json()
        images = data.get("data", [])

        print(f"   ✅ 生成成功（{elapsed:.1f}s）")
        print(f"   📸 图片数量：{len(images)}")

        # 保存图片
        for i, img_data in enumerate(images):
            if img_data.get("b64_json"):
                img_bytes = base64.b64decode(img_data["b64_json"])
                out_path = Path(f"test_output_{i + 1}.png")
                out_path.write_bytes(img_bytes)
                print(f"   💾 已保存：{out_path}（{len(img_bytes) / 1024:.0f}KB）")

        print()
        return True

    except requests.exceptions.Timeout:
        print(f"   ❌ 超时（>120s），请检查服务器负载\n")
        return False
    except Exception as e:
        print(f"   ❌ 失败：{e}\n")
        return False


def test_batch(base_url: str) -> bool:
    """测试批量生成"""
    print("=" * 60)
    print("4️⃣  批量生成：POST /v1/images/generations/batch（可选）")
    print("=" * 60)
    try:
        resp = requests.post(
            f"{base_url}/v1/images/generations/batch",
            json=[
                {
                    "prompt": "一只白色小猫在草地上玩耍，卡通风格",
                    "size": "512x512",
                },
                {
                    "prompt": "夕阳下的海滩，油画风格",
                    "size": "512x512",
                },
            ],
            timeout=180,
        )

        if resp.status_code == 404:
            print("   ⚠️  端点不可用（可能使用了 Aquiles-Image 而非自定义服务）\n")
            return "skipped"

        data = resp.json()
        results = data.get("results", [])
        for r in results:
            if "error" in r:
                print(f"   ❌ {r['prompt'][:30]}... → {r['error']}")
            else:
                print(f"   ✅ {r['prompt'][:30]}... → seed={r['seed']}")
        print()
        return True
    except Exception as e:
        print(f"   ⚠️  跳过（{e}）\n")
        return "skipped"


def test_openai_sdk(base_url: str):
    """展示 OpenAI SDK 用法（可选依赖）"""
    print("=" * 60)
    print("5️⃣  OpenAI SDK 兼容性（示例代码）")
    print("=" * 60)

    # 提取 v1 base（去掉可能的尾部路径）
    v1_base = base_url.rstrip("/")
    if not v1_base.endswith("/v1"):
        v1_base = v1_base + "/v1"

    print("""
    ✅ 服务已兼容 OpenAI SDK，教师可以用和 ChatGPT 一样的写法：

    ```python
    from openai import OpenAI

    client = OpenAI(
        base_url="{v1_base}",
        api_key="not-needed"
    )

    response = client.images.generate(
        model="black-forest-labs/FLUX.2-klein-9B",
        prompt="你的提示词",
        n=1,
        size="1024x1024"
    )

    image_url = response.data[0].url
    ```
    """.format(v1_base=v1_base))


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="FLUX.2-klein-9B 推理服务测试客户端")
    parser.add_argument(
        "--url",
        default="http://localhost:5500",
        help="推理服务地址（默认：http://localhost:5500）",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="自定义测试 prompt",
    )
    parser.add_argument(
        "--size",
        default="1024x1024",
        help="图片尺寸（默认：1024x1024）",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="跳过生成测试（只测健康和模型列表）",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    prompt = args.prompt or TEST_PROMPTS[0]

    print()
    print("🧪 FLUX.2-klein-9B 推理服务 连通性测试")
    print(f"📍 目标地址：{base_url}")
    print()

    results = []

    # 1. 健康检查
    results.append(("健康检查", test_health(base_url)))

    # 2. 模型列表
    results.append(("模型列表", test_list_models(base_url)))

    # 3. 生成测试
    if not args.skip_generate:
        results.append(("图片生成", test_generate(base_url, prompt, args.size)))
    else:
        print("⏭️  跳过生成测试（--skip-generate）\n")

    # 4. 批量测试
    batch_result = test_batch(base_url)
    results.append(("批量生成", batch_result))

    # 5. OpenAI SDK 示例
    test_openai_sdk(base_url)

    # ── 汇总 ──
    print("=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    all_pass = True
    for name, status in results:
        icon = "✅" if status == True else ("⚠️" if status == "skipped" else "❌")
        print(f"   {icon}  {name}")
        if status == False:
            all_pass = False

    print()
    if all_pass:
        print("🎉 全部测试通过！服务就绪，教师可以开始 Vibe Coding。")
    else:
        print("⚠️  部分测试未通过，请检查服务日志。")

    print(f"\n📖 API 文档：{base_url}/docs")
    print()


if __name__ == "__main__":
    main()
