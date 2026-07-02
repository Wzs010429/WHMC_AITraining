"""
压力测试 / 并发队列测试脚本
=============================
模拟多教师同时提交，测试队列承载能力。

用法：
  python stress_test.py --url http://10.100.35.254:5500           # 默认 10 个作业
  python stress_test.py --url http://10.100.35.254:5500 --jobs 30 # 30 个作业
  python stress_test.py --url http://10.100.35.254:5500 --jobs 50 --concurrent 10  # 50个，10并发提交
  python stress_test.py --url http://10.100.35.254:5500 --mode all # 混合所有模式
"""

import argparse
import base64
import json
import sys
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from io import BytesIO

try:
    import requests
    from PIL import Image
except ImportError:
    print("❌ 需要 requests 和 Pillow：pip install requests Pillow")
    sys.exit(1)


# ═════════════════════════════════════════════════════════
# 测试数据
# ═════════════════════════════════════════════════════════

T2I_PROMPTS = [
    "一只橘猫坐在窗台上看月亮，绘本插画风格，温暖色调",
    "春天的花园里，孩子们在草地上读书，卡通风格",
    "月光洒在湖面上，远山朦胧，中国水墨画风格",
    "夕阳下的海滩，椰子树剪影，油画风格",
    "一只白色小狗在花丛中追蝴蝶，水彩风格",
    "森林里的小木屋，炊烟袅袅，童话绘本风格",
    "城市夜景，霓虹灯倒映在雨后的街道上，赛博朋克",
    "樱花树下，少女穿着和服撑着纸伞，浮世绘风格",
    "宇航员在火星上种植向日葵，科幻插画",
    "深海里的美人鱼和水母，梦幻蓝紫色调",
    "秋天的枫叶林，金色阳光穿过树叶，印象派",
    "熊猫在竹林里吃竹子，可爱简笔画风格",
    "城堡上空的烟花表演，童话梦幻风格",
    "热带雨林中的瀑布和彩虹，写实风格",
    "北极极光下的雪橇犬，冰蓝色调",
    "老北京胡同里的猫，午后阳光，生活气息",
    "蒸汽火车穿过雪山隧道，蒸汽朋克风格",
    "海底珊瑚礁和小丑鱼，明亮色彩",
    "草原上的蒙古包和星空，宁静夜晚",
    "街头咖啡馆，雨中倒影，电影感",
]

I2I_PROMPTS = [
    "Add a warm golden hour lighting, make it look like sunset",
    "变成黑白素描风格，保留原有的构图",
    "加上雪花飘落效果，冬天氛围",
    "把背景换成星空，保持主体不变",
    "增加电影感的色彩分级，暖色调",
    "Comic book style, bold outlines, pop art colors",
    "添加雨滴效果，让画面更有氛围感",
    "Art nouveau style, decorative borders, flowing lines",
]

MULTI_REF_PROMPTS = [
    "Combine the scene from image 1 with the style of image 2",
    "把图1的主体放到图2的背景里，保持图1的光影",
    "Mix the color palette of image 2 into the composition of image 1",
]


# ═════════════════════════════════════════════════════════
# 生成测试用参考图（不需要外部文件）
# ═════════════════════════════════════════════════════════

def generate_test_reference_image(size=(256, 256), color=None) -> str:
    """生成一张纯色测试图，返回 base64 字符串"""
    if color is None:
        color = (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200))
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def generate_gradient_test_image(size=(256, 256)) -> str:
    """生成一张渐变色测试图，返回 base64"""
    img = Image.new("RGB", size)
    pixels = img.load()
    for y in range(size[1]):
        r = int(200 * y / size[1]) + random.randint(0, 55)
        g = int(150 * (1 - y / size[1])) + random.randint(0, 50)
        b = random.randint(100, 200)
        for x in range(size[0]):
            pixels[x, y] = (r, g, b)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# 预生成几张测试参考图
TEST_REF_IMAGES = [generate_test_reference_image() for _ in range(4)]
TEST_GRADIENT_IMAGES = [generate_gradient_test_image() for _ in range(2)]


# ═════════════════════════════════════════════════════════
# 核心逻辑
# ═════════════════════════════════════════════════════════

class StressTest:
    def __init__(self, base_url: str, total_jobs: int, concurrent_submit: int, mode: str):
        self.base_url = base_url.rstrip("/")
        self.total_jobs = total_jobs
        self.concurrent_submit = concurrent_submit
        self.mode = mode  # t2i / i2i / multi / all

        self.job_ids: list[str] = []
        self.results: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.stats = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "total_elapsed": 0.0,
            "modes": {"T2I": 0, "I2I": 0, "Multi-Ref": 0},
        }
        self.start_time = 0.0

    # ── 生成请求体 ──────────────────────────────────

    def _make_request_body(self, index: int):
        """根据模式和索引生成请求体"""
        if self.mode == "t2i":
            return {"prompt": T2I_PROMPTS[index % len(T2I_PROMPTS)], "size": "512x512"}
        elif self.mode == "i2i":
            return {
                "prompt": I2I_PROMPTS[index % len(I2I_PROMPTS)],
                "image": TEST_REF_IMAGES[index % len(TEST_REF_IMAGES)],
                "size": "512x512",
            }
        elif self.mode == "multi":
            # 每 3 个作业用不同的参考图组合
            n_refs = (index % 3) + 2
            refs = [TEST_GRADIENT_IMAGES[i % 2] for i in range(n_refs)]
            return {
                "prompt": MULTI_REF_PROMPTS[index % len(MULTI_REF_PROMPTS)],
                "images": refs,
                "size": "512x512",
            }
        else:  # "all" — 混合
            r = index % 5
            if r < 3:
                return {"prompt": T2I_PROMPTS[index % len(T2I_PROMPTS)], "size": "512x512"}
            elif r == 3:
                return {
                    "prompt": I2I_PROMPTS[index % len(I2I_PROMPTS)],
                    "image": TEST_REF_IMAGES[index % len(TEST_REF_IMAGES)],
                    "size": "512x512",
                }
            else:
                return {
                    "prompt": MULTI_REF_PROMPTS[index % len(MULTI_REF_PROMPTS)],
                    "images": [TEST_GRADIENT_IMAGES[0], TEST_REF_IMAGES[index % 4]],
                    "size": "512x512",
                }

    # ── 提交作业 ────────────────────────────────────

    def _submit_one(self, index: int) -> tuple[int, str | None]:
        """提交一个作业，返回 (index, job_id or None)"""
        try:
            body = self._make_request_body(index)
            mode = "T2I" if "image" not in body or body.get("image") is None else (
                "I2I" if "image" in body else "Multi-Ref"
            )
            # 重新判断 mode
            if "images" in body:
                mode = "Multi-Ref"
            elif "image" in body:
                mode = "I2I"
            else:
                mode = "T2I"

            resp = requests.post(
                f"{self.base_url}/v1/images/generations",
                json=body,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                jid = data["job_id"]
                with self.lock:
                    self.stats["submitted"] += 1
                return index, jid, mode
            else:
                print(f"\n  ⚠️  提交 #{index} 失败 HTTP {resp.status_code}: {resp.text[:80]}")
                return index, None, "failed"
        except Exception as e:
            print(f"\n  ❌ 提交 #{index} 异常: {e}")
            return index, None, "failed"

    # ── 轮询作业 ────────────────────────────────────

    def _poll_one(self, job_id: str, index: int, timeout: int = 600):
        """轮询直到完成"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = requests.get(f"{self.base_url}/v1/jobs/{job_id}", timeout=10)
                if resp.status_code != 200:
                    time.sleep(2)
                    continue
                data = resp.json()
                status = data.get("status")

                if status == "completed":
                    result = data.get("result", {})
                    with self.lock:
                        self.stats["completed"] += 1
                        self.stats["total_elapsed"] += result.get("elapsed", 0)
                        mode = result.get("mode", "?")
                        self.stats["modes"][mode] = self.stats["modes"].get(mode, 0) + 1
                        self.results[job_id] = {
                            "index": index,
                            "elapsed": result.get("elapsed", 0),
                            "size": result.get("size", "?"),
                            "mode": mode,
                            "seed": result.get("seed", 0),
                        }
                    return True
                elif status == "failed":
                    with self.lock:
                        self.stats["failed"] += 1
                    print(f"\n  ❌ job #{index} ({job_id}) 失败: {data.get('error', '?')}")
                    return False
                time.sleep(2)
            except Exception:
                time.sleep(2)
        with self.lock:
            self.stats["failed"] += 1
        print(f"\n  ⏰ job #{index} ({job_id}) 超时")
        return False

    # ── 主流程 ──────────────────────────────────────

    def run(self):
        print()
        print("=" * 65)
        print("🧪 FLUX API 压力测试")
        print("=" * 65)
        print(f"  📍 服务器  : {self.base_url}")
        print(f"  📦 总作业  : {self.total_jobs}")
        print(f"  🔀 并发提交: {self.concurrent_submit}")
        print(f"  🎯 模式    : {self.mode}")
        print(f"  📐 尺寸    : 512x512（快速模式）")
        print("=" * 65)
        print()

        # 1. 检查健康
        try:
            health = requests.get(f"{self.base_url}/health", timeout=10).json()
            print(f"✅ 服务器在线 | GPU: {health.get('gpu_name', '?')} | "
                  f"显存: {health.get('vram_total_gb', '?')}GB | "
                  f"已完成: {health.get('total_completed', 0)} 个")
        except Exception:
            print("❌ 服务器连不上！")
            return

        # 2. 并发提交所有作业
        self.start_time = time.time()
        print(f"\n🚀 开始并发提交 {self.total_jobs} 个作业…")
        print("-" * 65)

        pending_jobs = []  # [(job_id, index, mode)]
        with ThreadPoolExecutor(max_workers=self.concurrent_submit) as executor:
            futures = {executor.submit(self._submit_one, i): i for i in range(self.total_jobs)}

            for future in as_completed(futures):
                index, job_id, mode = future.result()
                if job_id:
                    pending_jobs.append((job_id, index, mode))
                    icon = "📝" if mode == "T2I" else ("🎨" if mode == "I2I" else "🧩")
                    with self.lock:
                        n = self.stats["submitted"]
                    print(f"  [{n}/{self.total_jobs}] {icon} #{index} → {job_id[:10]}… ({mode})")

        submit_elapsed = time.time() - self.start_time
        print(f"\n✅ 提交完成: {len(pending_jobs)}/{self.total_jobs} 个成功 "
              f"({submit_elapsed:.1f}s)")

        if not pending_jobs:
            print("❌ 没有作业可执行")
            return

        # 3. 并发轮询所有作业
        print(f"\n⏳ 开始轮询 {len(pending_jobs)} 个作业…")
        print("-" * 65)

        poll_start = time.time()

        # 显示实时队列状态
        def queue_watcher():
            while True:
                try:
                    q = requests.get(
                        f"{self.base_url}/v1/queue",
                        headers={"Accept": "application/json"},
                        timeout=5,
                    ).json()
                    cur = q.get("current_job", {})
                    cur_str = f"🎨 {cur['prompt'][:40]}… ({cur.get('elapsed', 0)}s)" if cur else "😴 空闲"
                    with self.lock:
                        done = self.stats["completed"] + self.stats["failed"]
                    print(f"\r  📊 队列:{q.get('queue_length',0)} | "
                          f"当前:{cur_str} | "
                          f"完成:{done}/{self.total_jobs} | "
                          f"平均:{q.get('avg_generation_seconds',0)}s/张",
                          end="", flush=True)
                except Exception:
                    pass
                time.sleep(3)

        watcher_thread = threading.Thread(target=queue_watcher, daemon=True)
        watcher_thread.start()

        # 轮询所有作业
        with ThreadPoolExecutor(max_workers=min(self.concurrent_submit * 2, 20)) as executor:
            poll_futures = {
                executor.submit(self._poll_one, jid, idx): (jid, idx)
                for jid, idx, _ in pending_jobs
            }
            for future in as_completed(poll_futures):
                future.result()  # 等全部完成

        total_elapsed = time.time() - self.start_time
        print("\n")
        print("-" * 65)

        # 4. 汇总
        with self.lock:
            completed = self.stats["completed"]
            failed = self.stats["failed"]
            total_gen = self.stats["total_elapsed"]

        avg_elapsed = total_gen / completed if completed > 0 else 0

        print()
        print("=" * 65)
        print("📊 测试结果")
        print("=" * 65)
        print(f"  📦 提交     : {len(pending_jobs)} 个")
        print(f"  ✅ 成功     : {completed} 个")
        print(f"  ❌ 失败     : {failed} 个")
        print(f"  ⏱  总耗时   : {total_elapsed:.0f}s ({total_elapsed/60:.1f}分钟)")
        print(f"  ⚡ 单张平均  : {avg_elapsed:.1f}s")
        print(f"  📈 吞吐量    : {completed / (total_elapsed / 60):.1f} 张/分钟")
        print(f"  🎯 模式分布  :")

        with self.lock:
            modes = self.stats["modes"]
        for m, count in sorted(modes.items()):
            print(f"       {m}: {count} 张")

        # 显示每个作业耗时分布
        with self.lock:
            times = sorted([r["elapsed"] for r in self.results.values()])
        if times:
            print(f"  📊 耗时分布  :")
            print(f"       最快: {times[0]:.1f}s")
            print(f"       最慢: {times[-1]:.1f}s")
            mid = len(times) // 2
            print(f"       中位数: {times[mid]:.1f}s")
            if len(times) > 4:
                print(f"       P95: {times[int(len(times)*0.95)]:.1f}s")

        print("=" * 65)
        print()

        # 保存结果 JSON
        out = {
            "server": self.base_url,
            "total_jobs": self.total_jobs,
            "completed": completed,
            "failed": failed,
            "total_elapsed_s": round(total_elapsed, 1),
            "avg_per_image_s": round(avg_elapsed, 1),
            "throughput_per_min": round(completed / (total_elapsed / 60), 1),
            "modes": modes,
            "details": {
                jid: r for jid, r in sorted(
                    self.results.items(), key=lambda x: x[1]["elapsed"]
                )
            },
        }
        result_file = Path(f"stress_result_{int(time.time())}.json")
        result_file.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        print(f"📄 详细结果已保存：{result_file}")


# ═════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="FLUX API 压力测试 — 多教师并发模拟",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python stress_test.py --url http://10.100.35.254:5500 --jobs 20
  python stress_test.py --url http://10.100.35.254:5500 --jobs 50 --concurrent 10
  python stress_test.py --url http://10.100.35.254:5500 --mode i2i --jobs 15
  python stress_test.py --url http://10.100.35.254:5500 --mode all --jobs 30
        """,
    )
    parser.add_argument("--url", default="http://localhost:5500")
    parser.add_argument("--jobs", type=int, default=10, help="总作业数（默认 10）")
    parser.add_argument("--concurrent", type=int, default=5, help="并发提交数（默认 5）")
    parser.add_argument(
        "--mode", default="all",
        choices=["t2i", "i2i", "multi", "all"],
        help="测试模式：t2i=文生图, i2i=图生图, multi=多参考图, all=混合",
    )
    args = parser.parse_args()

    # 需要 Pillow 来生成测试参考图（i2i/multi/all 模式）
    if args.mode in ("i2i", "multi", "all"):
        try:
            from PIL import Image
        except ImportError:
            print("⚠️  i2i/multi/all 模式需要 Pillow")
            print("   安装：pip install Pillow")
            print("   或换用 --mode t2i")
            sys.exit(1)

    test = StressTest(
        base_url=args.url,
        total_jobs=args.jobs,
        concurrent_submit=args.concurrent,
        mode=args.mode,
    )
    test.run()


if __name__ == "__main__":
    main()
