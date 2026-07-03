"""
多客户端模拟压测
=================
模拟 N 个独立教师终端，各自提交作业、等待返回。
每个客户端互相独立 — 就像真实的教室场景。

用法：
  python multi_client_test.py --url http://10.100.35.254:5500 --clients 5
  python multi_client_test.py --url http://10.100.35.254:5500 --clients 20 --mode mixed
  python multi_client_test.py --url http://10.100.35.254:5500 --clients 30 --delay 2
"""

import argparse
import base64
import json
import sys
import time
import random
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("❌ pip install requests")
    sys.exit(1)


# ═════════════════════════════════════════════════════════
# 测试素材
# ═════════════════════════════════════════════════════════

T2I_PROMPTS = [
    "一只橘猫坐在窗台上看月亮，绘本插画风格",
    "春天的花园里，孩子们在草地上读书，卡通风格",
    "月光洒在湖面上，中国水墨画风格",
    "夕阳下的海滩，油画风格",
    "森林里的小木屋，童话绘本风格",
    "熊猫在竹林里吃竹子，可爱简笔画",
    "北极极光下的雪橇犬，冰蓝色调",
    "深海里的美人鱼和水母，梦幻风格",
    "秋天枫叶林，金色阳光，印象派",
    "樱花树下穿和服的少女，浮世绘",
    "宇航员在火星种向日葵，科幻插画",
    "城市夜晚霓虹灯街道，赛博朋克",
    "蒸汽火车穿过雪山，蒸汽朋克",
    "热带雨林瀑布彩虹，写实风格",
    "街头咖啡馆雨中倒影，电影感",
]

I2I_PROMPTS = [
    "添加金黄色夕阳光线，温暖氛围",
    "变成黑白素描风格",
    "加上雪花飘落效果",
    "背景换成星空",
    "添加电影暖色调色彩分级",
    "转换成动漫风格",
    "增加雨后湿润的光影效果",
    "Art nouveau decorative style",
]

# 读取 ref 文件夹中的参考图
REF_DIR = Path(__file__).parent / "ref"
REF_IMAGES = {}
if REF_DIR.exists():
    for f in sorted(REF_DIR.glob("*.png")):
        with open(f, "rb") as fh:
            REF_IMAGES[f.name] = base64.b64encode(fh.read()).decode()
    if REF_IMAGES:
        print(f"📁 加载 {len(REF_IMAGES)} 张参考图：{list(REF_IMAGES.keys())}")
else:
    print("⚠️  ref/ 文件夹不存在，图生图模式将不可用")


# ═════════════════════════════════════════════════════════
# 单个客户端
# ═════════════════════════════════════════════════════════

# 输出目录
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


class TeacherClient:
    """模拟一位教师的完整调用流程"""

    def __init__(self, client_id: int, base_url: str, mode: str, size: str):
        self.id = client_id
        self.base_url = base_url.rstrip("/")
        self.mode = mode        # t2i / i2i / mixed
        self.size = size

        self.start_time = 0.0
        self.submit_time = 0.0
        self.complete_time = 0.0
        self.job_id: str = ""
        self.request_mode: str = ""
        self.prompt: str = ""
        self.ref_name: str = ""   # 用了哪张参考图
        self.result: dict = {}
        self.success = False
        self.error: str = ""
        self.saved_path: str = ""  # 保存路径

    def _pick_mode(self) -> str:
        """选模式：mixed 时随机 T2I 或 I2I"""
        if self.mode == "i2i":
            return "i2i"
        elif self.mode == "t2i":
            return "t2i"
        else:
            return "i2i" if REF_IMAGES and random.random() < 0.4 else "t2i"

    def _log(self, msg: str):
        t = datetime.now().strftime("%H:%M:%S")
        print(f"[{t}] 👤 教师#{self.id:02d} | {msg}")

    def run(self):
        """完整流程：提交 → 轮询 → 完成"""
        self.start_time = time.time()
        req_mode = self._pick_mode()

        # ── 构建请求 ──
        body: dict = {"size": self.size, "response_format": "b64_json"}
        if req_mode == "i2i" and REF_IMAGES:
            self.ref_name = random.choice(list(REF_IMAGES.keys()))
            body["image"] = REF_IMAGES[self.ref_name]
            body["prompt"] = random.choice(I2I_PROMPTS)
            self.prompt = body["prompt"]
            self.request_mode = f"🎨I2I[{self.ref_name}]"
        else:
            body["prompt"] = random.choice(T2I_PROMPTS)
            self.prompt = body["prompt"]
            self.request_mode = "📝T2I"

        # ── 提交 ──
        try:
            resp = requests.post(
                f"{self.base_url}/v1/images/generations",
                json=body, timeout=15,
            )
            data = resp.json()
            self.job_id = data["job_id"]
            self.submit_time = time.time()
            pos = data.get("position", "?")
            self._log(f"{self.request_mode} → job_id={self.job_id[:10]}… 排队#{pos}")
        except Exception as e:
            self.error = str(e)
            self.complete_time = time.time()
            self._log(f"❌ 提交失败: {e}")
            return

        # ── 轮询 ──
        while True:
            try:
                resp = requests.get(
                    f"{self.base_url}/v1/jobs/{self.job_id}",
                    timeout=10,
                )
                job = resp.json()
                status = job.get("status")

                if status == "completed":
                    self.complete_time = time.time()
                    self.success = True
                    self.result = job.get("result", {})
                    total = self.complete_time - self.start_time

                    # 保存图片到本地
                    if self.result.get("b64_json"):
                        mode_tag = "i2i" if self.ref_name else "t2i"
                        ref_tag = f"_{self.ref_name.replace('.png','')}" if self.ref_name else ""
                        fname = f"{mode_tag}{ref_tag}_teacher{self.id:02d}_{self.job_id[:8]}.png"
                        fpath = OUTPUT_DIR / fname
                        fpath.write_bytes(base64.b64decode(self.result["b64_json"]))
                        self.saved_path = str(fpath)

                    self._log(f"✅ 完成 总{total:.0f}s 推理{self.result.get('elapsed','?')}s → {Path(self.saved_path).name if self.saved_path else '未保存'}")
                    return

                elif status == "failed":
                    self.error = job.get("error", "unknown")
                    self.complete_time = time.time()
                    self._log(f"❌ 失败: {self.error}")
                    return

                time.sleep(2)

            except Exception as e:
                self._log(f"⚠️ 轮询异常: {e}，重试…")
                time.sleep(2)


# ═════════════════════════════════════════════════════════
# 主流程
# ═════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="多客户端模拟 — N 个独立教师终端压测",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python multi_client_test.py --clients 5              # 5个教师，混合模式
  python multi_client_test.py --clients 20 --mode t2i   # 20个纯文生图
  python multi_client_test.py --clients 30 --delay 1    # 30个，每1秒启动一个
        """,
    )
    parser.add_argument("--url", default="http://localhost:5500")
    parser.add_argument("--clients", type=int, default=5, help="模拟教师数量")
    parser.add_argument("--mode", default="mixed", choices=["t2i", "i2i", "mixed"])
    parser.add_argument("--size", default="512x512", help="图片尺寸（512快/1024慢）")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="启动间隔秒数（默认0.5，模拟几乎同时涌入）")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    print()
    print("=" * 65)
    print("🏫 多客户端模拟压测")
    print("=" * 65)
    print(f"  📍 服务器  : {base_url}")
    print(f"  👥 教师数  : {args.clients}")
    print(f"  🎯 模式    : {args.mode}")
    print(f"  📐 尺寸    : {args.size}")
    print(f"  ⏱  启动间隔: {args.delay}s/人")
    print(f"  📁 参考图  : {len(REF_IMAGES)} 张")
    print("=" * 65)
    print()

    # 健康检查
    try:
        h = requests.get(f"{base_url}/health", timeout=10).json()
        print(f"✅ 服务器在线 | GPU: {h.get('gpu_name','?')} | "
              f"已完成: {h.get('total_completed',0)} 个")
    except Exception:
        print("❌ 服务器连不上！")
        return

    print()
    print("─" * 65)
    print("📡 客户端日志（每个 👤 代表一个独立终端）")
    print("─" * 65)

    # 创建 N 个客户端
    clients = [
        TeacherClient(i, base_url, args.mode, args.size)
        for i in range(1, args.clients + 1)
    ]

    overall_start = time.time()

    # 错峰启动（模拟真实涌入 — 每人间隔 delay 秒）
    with ThreadPoolExecutor(max_workers=args.clients) as executor:
        futures = []
        for i, c in enumerate(clients):
            if i > 0:
                time.sleep(args.delay)
            futures.append(executor.submit(c.run))

        # 等全部完成
        for f in as_completed(futures):
            f.result()

    total_time = time.time() - overall_start

    # ── 汇总 ──
    successes = [c for c in clients if c.success]
    failures = [c for c in clients if c.error or not c.success]

    print()
    print("─" * 65)
    print()
    print("=" * 65)
    print("📊 汇总报告")
    print("=" * 65)

    # 按模式分类
    t2i_list = [c for c in successes if c.request_mode.startswith("📝")]
    i2i_list = [c for c in successes if c.request_mode.startswith("🎨")]

    print(f"  👥 客户端      : {args.clients} 个")
    print(f"  ✅ 成功        : {len(successes)} 个")
    print(f"     📝 文生图   : {len(t2i_list)} 张")
    print(f"     🎨 图生图   : {len(i2i_list)} 张")
    print(f"  ❌ 失败        : {len(failures)} 个")
    print(f"  ⏱  总耗时      : {total_time:.0f}s ({total_time/60:.1f}分钟)")

    if successes:
        elapsed_list = [c.result.get("elapsed", 0) for c in successes]
        wait_list = [c.complete_time - c.start_time for c in successes]
        print(f"  ⚡ 推理耗时    : 最快{min(elapsed_list):.1f}s 最慢{max(elapsed_list):.1f}s "
              f"平均{sum(elapsed_list)/len(elapsed_list):.1f}s")
        print(f"  ⏳ 端到端等待  : 最快{min(wait_list):.0f}s 最慢{max(wait_list):.0f}s "
              f"平均{sum(wait_list)/len(wait_list):.0f}s")
        print(f"  📈 吞吐量      : {len(successes)/(total_time/60):.1f} 张/分钟")

    if failures:
        print(f"\n  ❌ 失败列表:")
        for c in failures:
            print(f"     教师#{c.id:02d} {c.request_mode}: {c.error[:60]}")

    print("=" * 65)
    print()

    # 保存详细日志
    log = {
        "server": base_url,
        "clients": args.clients,
        "mode": args.mode,
        "success": len(successes),
        "failed": len(failures),
        "total_time_s": round(total_time, 1),
        "t2i_count": len(t2i_list),
        "i2i_count": len(i2i_list),
        "details": [
            {
                "teacher_id": c.id,
                "mode": c.request_mode,
                "prompt": c.prompt[:60],
                "ref_image": c.ref_name,
                "success": c.success,
                "job_id": c.job_id,
                "inference_s": c.result.get("elapsed", 0) if c.success else 0,
                "total_wait_s": round(c.complete_time - c.start_time, 1) if c.success else 0,
                "saved_path": c.saved_path,
                "error": c.error,
            }
            for c in sorted(clients, key=lambda c: c.complete_time - c.start_time if c.success else 999)
        ],
    }
    log_file = Path(f"multi_client_result_{int(time.time())}.json")
    log_file.write_text(json.dumps(log, indent=2, ensure_ascii=False))
    print(f"📄 详细日志：{log_file}")
    print(f"📁 图片目录：{OUTPUT_DIR.resolve()}")
    if successes:
        refs_used = set(c.ref_name for c in successes if c.ref_name)
        if refs_used:
            print(f"🎨 使用参考图：{refs_used}")
    print()


if __name__ == "__main__":
    main()
