"""
动态队列压测 — 模拟教师在不同时间点涌入
==========================================
模拟真实上课场景：老师们在不同时间点提交任务，
队列动态扩张和收缩。实时显示队列深度变化。

用法：
  python dynamic_queue_test.py --url http://10.100.35.254:5500 --teachers 20 --duration 180
  python dynamic_queue_test.py --url http://10.100.35.254:5500 --teachers 40 --duration 300

场景说明：
  30个教师，在 3 分钟内陆续到来 → 队列先涨后消
  就像上课时老师轮流提交绘本生成任务
"""

import argparse
import base64
import json
import sys
import time
import random
import threading
import os
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("❌ pip install requests")
    sys.exit(1)

# ═════════════════════════════════════════════════════════
# 素材
# ═════════════════════════════════════════════════════════

T2I_PROMPTS = [
    "一只橘猫坐在窗台上看月亮，绘本插画风格",
    "春天的花园里孩子们在草地上读书",
    "月光洒在湖面上远山朦胧中国水墨画",
    "夕阳下的海滩椰子树剪影油画风格",
    "森林里的小木屋炊烟袅袅童话绘本",
    "熊猫在竹林里吃竹子可爱简笔画",
    "北极极光下的雪橇犬冰蓝色调",
    "深海里的美人鱼和水母梦幻蓝紫色",
    "秋天枫叶林金色阳光穿过树叶",
    "樱花树下少女穿着和服撑着纸伞",
    "宇航员在火星上种植向日葵科幻",
    "城市夜晚霓虹灯倒映在雨后街道",
    "蒸汽火车穿过雪山隧道蒸汽朋克",
    "热带雨林中的瀑布和彩虹写实",
    "街头咖啡馆雨中倒影电影感",
]

I2I_PROMPTS = [
    "添加金黄色夕阳光线温暖氛围",
    "变成黑白素描风格保留构图",
    "加上雪花飘落效果冬天氛围",
    "把背景换成星空保持主体不变",
    "添加电影暖色调色彩分级",
    "转换成动漫风格明亮色彩",
    "增加雨后湿润的光影效果",
    "Art nouveau decorative flowing lines",
]

# 参考图
REF_DIR = Path(__file__).parent / "ref"
REF_IMAGES = {}
if REF_DIR.exists():
    for f in sorted(REF_DIR.glob("*.png")):
        with open(f, "rb") as fh:
            REF_IMAGES[f.name] = base64.b64encode(fh.read()).decode()

# 输出目录
OUTPUT_DIR = Path(__file__).parent / "output_dynamic"
OUTPUT_DIR.mkdir(exist_ok=True)


# ═════════════════════════════════════════════════════════
# 队列监视器（后台线程，实时刷新）
# ═════════════════════════════════════════════════════════

class QueueMonitor:
    """实时显示队列深度 + 进度条"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.running = True
        self.history: list[tuple[float, int]] = []  # [(timestamp, queue_length)]
        self.max_depth = 0
        self.completed_total = 0
        self.thread = threading.Thread(target=self._watch, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.running = False

    def _watch(self):
        while self.running:
            try:
                r = requests.get(
                    f"{self.base_url}/v1/queue",
                    headers={"Accept": "application/json"},
                    timeout=5,
                ).json()
                depth = r["queue_length"]
                self.completed_total = r["total_completed"]
                self.max_depth = max(self.max_depth, depth)
                self.history.append((time.time(), depth))

                # 画实时柱状图
                bar = "█" * min(depth, 60)
                cur = r.get("current_job", {})
                cur_info = f"🎨 {cur['prompt'][:25]}… {cur.get('elapsed',0)}s" if cur else "😴 空闲"
                print(f"\r  📊 队列深度: {depth:>3} |{bar:<60}| {cur_info}   ", end="", flush=True)
            except Exception:
                pass
            time.sleep(1.5)


# ═════════════════════════════════════════════════════════
# 单个教师
# ═════════════════════════════════════════════════════════

class Teacher:
    def __init__(self, teacher_id: int, base_url: str, i2i_ratio: float = 0.3):
        self.id = teacher_id
        self.base_url = base_url
        self.i2i_ratio = i2i_ratio

        self.arrive_time = 0.0
        self.submit_time = 0.0
        self.complete_time = 0.0
        self.job_id = ""
        self.mode = ""
        self.prompt = ""
        self.ref_name = ""
        self.success = False
        self.elapsed = 0.0
        self.saved = ""

    def run(self):
        """完整流程"""
        self.arrive_time = time.time()

        # 决定模式
        is_i2i = REF_IMAGES and random.random() < self.i2i_ratio

        body: dict = {"size": "512x512", "response_format": "b64_json"}
        if is_i2i:
            self.ref_name = random.choice(list(REF_IMAGES.keys()))
            body["image"] = REF_IMAGES[self.ref_name]
            body["prompt"] = random.choice(I2I_PROMPTS)
            self.mode = f"🎨I2I"
        else:
            body["prompt"] = random.choice(T2I_PROMPTS)
            self.mode = "📝T2I"
        self.prompt = body["prompt"]

        # 提交
        try:
            r = requests.post(f"{self.base_url}/v1/images/generations", json=body, timeout=15)
            self.job_id = r.json()["job_id"]
            self.submit_time = time.time()
        except Exception as e:
            self.complete_time = time.time()
            return

        # 轮询
        while True:
            try:
                r = requests.get(f"{self.base_url}/v1/jobs/{self.job_id}", timeout=10)
                job = r.json()
                if job["status"] == "completed":
                    self.complete_time = time.time()
                    self.success = True
                    result = job.get("result", {})
                    self.elapsed = result.get("elapsed", 0)
                    # 保存
                    if result.get("b64_json"):
                        tag = "i2i" if is_i2i else "t2i"
                        ref_tag = f"_{self.ref_name.replace('.png','')}" if self.ref_name else ""
                        fname = f"{tag}{ref_tag}_T{self.id:02d}_{self.job_id[:8]}.png"
                        fpath = OUTPUT_DIR / fname
                        fpath.write_bytes(base64.b64decode(result["b64_json"]))
                        self.saved = str(fpath.name)
                    return
                elif job["status"] == "failed":
                    self.complete_time = time.time()
                    return
                time.sleep(2)
            except Exception:
                time.sleep(2)


# ═════════════════════════════════════════════════════════
# 主流程
# ═════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="动态队列压测 — 教师在不同时间点涌入",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
场景示例：
  30个教师，在 3 分钟内随机到达 → 队列先涨到 15-20 深度，再慢慢消化
  40个教师，5 分钟 → 模拟整节课的请求负载
        """,
    )
    parser.add_argument("--url", default="http://localhost:5500")
    parser.add_argument("--teachers", type=int, default=20, help="教师总数")
    parser.add_argument("--duration", type=int, default=180, help="教师到达的时间跨度（秒），默认180s=3分钟")
    parser.add_argument("--i2i", type=float, default=0.3, help="图生图比例（默认0.3=30%%）")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    print()
    print("=" * 65)
    print("🌊 动态队列压测")
    print("=" * 65)
    print(f"  👥 教师总数: {args.teachers}")
    print(f"  ⏱️  到达跨度: {args.duration}s（{args.duration/60:.0f}分钟）")
    print(f"  🎨 图生图比: {args.i2i*100:.0f}%")
    print(f"  📁 参考图  : {len(REF_IMAGES)} 张")
    print(f"  💾 输出目录: {OUTPUT_DIR}")
    print("=" * 65)
    print()
    print("  场景: 老师们在上课期间陆续提交任务")
    print("  队列会先涨后消，模拟真实教室负载")
    print()

    # 健康检查
    try:
        h = requests.get(f"{base_url}/health", timeout=10).json()
        print(f"  ✅ 服务器在线 | GPU: {h.get('gpu_name','?')} | "
              f"已完成: {h.get('total_completed',0)} 个")
    except Exception:
        print("  ❌ 服务器连不上！")
        return

    print()
    print("─" * 65)

    # 启动队列监视器
    monitor = QueueMonitor(base_url)
    monitor.start()

    # 为每个教师生成到达时间（在 duration 秒内随机分布）
    teachers = []
    for i in range(1, args.teachers + 1):
        t = Teacher(i, base_url, args.i2i)
        # 随机到达时间：均匀分布在 duration 内
        t.arrival_delay = random.uniform(0, args.duration)
        teachers.append(t)

    # 按到达时间排序
    teachers.sort(key=lambda t: t.arrival_delay)

    overall_start = time.time()
    print(f"\n  🚀 {args.teachers} 位教师将在 {args.duration}s 内陆续到达…")
    print(f"  📊 实时队列深度（每 1.5s 刷新）：")
    print()

    # 日志事件
    events: list[dict] = []

    # 用线程池启动所有教师（各自等待自己的到达时间）
    def teacher_task(t: Teacher):
        # 等待到达时间
        delay = t.arrival_delay
        elapsed = time.time() - overall_start
        if delay > elapsed:
            time.sleep(delay - elapsed)

        t_start = time.time()
        t.run()
        t_end = time.time()

        wait = t.submit_time - t.arrive_time if t.submit_time else 0
        total = t_end - t_start if t.success else 0
        ref_info = f" [{t.ref_name}]" if t.ref_name else ""
        saved_info = f" → {t.saved}" if t.saved else ""

        status = "✅" if t.success else "❌"
        print(f"\n  {status} 教师#{t.id:02d} {t.mode}{ref_info} | "
              f"等待{total:.0f}s 推理{t.elapsed:.1f}s{saved_info}",
              end="", flush=True)

        events.append({
            "teacher_id": t.id,
            "arrival_s": round(t.arrival_delay, 1),
            "mode": t.mode,
            "ref": t.ref_name,
            "prompt": t.prompt[:40],
            "success": t.success,
            "total_wait_s": round(total, 1),
            "inference_s": round(t.elapsed, 1),
            "saved": t.saved,
        })

    with ThreadPoolExecutor(max_workers=args.teachers) as executor:
        futures = [executor.submit(teacher_task, t) for t in teachers]
        for f in as_completed(futures):
            f.result()

    monitor.stop()
    total_time = time.time() - overall_start

    print("\n")
    print("─" * 65)
    print()

    # ── 汇总 ──
    successes = [e for e in events if e["success"]]
    failures = [e for e in events if not e["success"]]

    print("=" * 65)
    print("📊 动态队列压测报告")
    print("=" * 65)
    print(f"  👥 教师总数    : {args.teachers}")
    print(f"  ✅ 成功        : {len(successes)}")
    print(f"  ❌ 失败        : {len(failures)}")
    print(f"  ⏱️  总耗时      : {total_time:.0f}s")
    print(f"  📈 队列最深    : {monitor.max_depth} 个作业同时排队")
    print(f"  🔢 累计完成    : {monitor.completed_total} 个（含之前的作业）")

    if successes:
        waits = [e["total_wait_s"] for e in successes]
        inferences = [e["inference_s"] for e in successes]
        print(f"  ⚡ 推理耗时    : 最快{min(inferences):.1f}s 最慢{max(inferences):.1f}s "
              f"平均{sum(inferences)/len(inferences):.1f}s")
        print(f"  ⏳ 端到端等待  : 最快{min(waits):.0f}s 最慢{max(waits):.0f}s "
              f"平均{sum(waits)/len(waits):.0f}s")
        print(f"  📈 吞吐量      : {len(successes)/(total_time/60):.1f} 张/分钟")

        # 队列深度分布
        if monitor.history:
            depths = [d for _, d in monitor.history]
            print(f"  📊 队列统计    : 平均深度 {sum(depths)/len(depths):.1f} | "
                  f"峰值 {max(depths)} | 谷值 {min(depths)}")

    print()
    print(f"  📁 图片目录    : {OUTPUT_DIR.resolve()}")
    print(f"  🖼️  生成图片    : {len(successes)} 张")
    print("=" * 65)
    print()

    # 时间线摘要
    print("📅 到达时间线（前20位）：")
    print("─" * 50)
    for e in events[:20]:
        bar = "█" * max(1, int(e["total_wait_s"] / 2)) if e["success"] else "✗"
        status = "✅" if e["success"] else "❌"
        print(f"  {status} T{e['teacher_id']:02d} @{e['arrival_s']:>5.0f}s  "
              f"{e['mode']}  等待{e['total_wait_s']:>4.0f}s  {bar}")
    if len(events) > 20:
        print(f"  … 还有 {len(events)-20} 位")

    # 保存报告
    report = {
        "total_teachers": args.teachers,
        "duration_s": args.duration,
        "success": len(successes),
        "failed": len(failures),
        "max_queue_depth": monitor.max_depth,
        "total_time_s": round(total_time, 1),
        "events": events,
    }
    import json as _json
    rp = Path(f"dynamic_result_{int(time.time())}.json")
    rp.write_text(_json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n📄 详细报告: {rp}")
    print()


if __name__ == "__main__":
    main()
