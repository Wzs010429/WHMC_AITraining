"""
FLUX.2-klein-9B 推理服务 — FastAPI + 任务队列
================================================
OpenAI 兼容 /v1/images/generations 端点
多教师并发 → 异步作业队列（提交即返回 job_id，轮询获取结果）

模型来源：
  🅰️ ModelScope（推荐国内）: modelscope download black-forest-labs/FLUX.2-klein-9B
  🅱️ HuggingFace 镜像: HF_ENDPOINT=https://hf-mirror.com
  🅲️ 本地路径: --model-path /data/models/FLUX.2-klein-9B

启动：
  python server.py --host 0.0.0.0 --port 5500
队列看板：
  http://<ip>:5500/v1/queue
"""

import io
import os
import sys
import time
import uuid
import base64
import logging
import argparse
import asyncio
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Literal
from contextlib import asynccontextmanager

import torch
from PIL import Image
from fastapi import FastAPI, HTTPException, Request, Query, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# ── 日志 ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("flux-server")

# ── 全局 ───────────────────────────────────────────────
pipe = None
model_info = {
    "model_id": "black-forest-labs/FLUX.2-klein-9B",
    "device": "cuda",
    "dtype": "bfloat16",
    "max_resolution": (2048, 2048),
    "default_resolution": (1024, 1024),
    "num_inference_steps": 4,
    "guidance_scale": 1.0,
}
API_KEY = os.environ.get("FLUX_API_KEY", "")
security = HTTPBearer(auto_error=False)
start_time = time.time()


# ═════════════════════════════════════════════════════════
# 任务队列系统
# ═════════════════════════════════════════════════════════

@dataclass
class Job:
    job_id: str
    request: "ImageGenerationRequest"
    status: str = "queued"          # queued | processing | completed | failed | cancelled
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: dict | None = None      # {b64_json, seed, elapsed, size}
    error: str | None = None

    @property
    def elapsed(self) -> float | None:
        if self.completed_at and self.started_at:
            return round(self.completed_at - self.started_at, 1)
        return None


class JobManager:
    """内存任务队列 — FIFO，GPU 逐张推理"""

    def __init__(self, max_concurrent: int = 1):
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.jobs: dict[str, Job] = {}
        self.current_job: Job | None = None
        self._worker_task: asyncio.Task | None = None
        self.max_concurrent = max_concurrent
        self._avg_elapsed: float = 9.0          # 滑动平均（秒）
        self._completed_count: int = 0

    async def start(self):
        self._worker_task = asyncio.create_task(self._worker())
        log.info(f"👷 后台 Worker 已启动（并发数={self.max_concurrent}）")

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        log.info("👷 后台 Worker 已停止")

    # ── 提交 ──────────────────────────────────────────

    async def submit(self, request: "ImageGenerationRequest") -> str:
        job = Job(
            job_id=uuid.uuid4().hex[:12],
            request=request,
        )
        self.jobs[job.job_id] = job
        await self.queue.put(job)
        log.info(
            f"📥 job_id={job.job_id} | prompt='{request.prompt[:50]}...' "
            f"| queue_size={self.queue.qsize()}"
        )
        return job.job_id

    # ── 查询 ──────────────────────────────────────────

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def get_position(self, job: Job) -> int:
        """计算排队位置（0=正在处理, 1+=前面还有几个）"""
        if job.status == "processing":
            return 0
        if job.status in ("completed", "failed", "cancelled"):
            return -1
        # 数队列中排在它前面的
        pos = 0
        # 队列无法直接遍历位置，用创建时间估算
        for j in self.jobs.values():
            if j.status == "queued" and j.created_at < job.created_at:
                pos += 1
        return pos + (1 if self.current_job else 0)

    def get_queue_status(self) -> dict:
        """队列快照"""
        queued_jobs = [j for j in self.jobs.values() if j.status == "queued"]
        queued_jobs.sort(key=lambda j: j.created_at)

        return {
            "queue_length": len(queued_jobs),
            "current_job": {
                "job_id": self.current_job.job_id,
                "prompt": self.current_job.request.prompt[:80],
                "started_at": self.current_job.started_at,
                "elapsed": round(time.time() - self.current_job.started_at, 1)
                if self.current_job and self.current_job.started_at else None,
            } if self.current_job else None,
            "queued": [
                {
                    "job_id": j.job_id,
                    "prompt": j.request.prompt[:60],
                    "position": i + 1,
                    "estimated_wait_seconds": round((i + 1) * self._avg_elapsed),
                }
                for i, j in enumerate(queued_jobs)
            ],
            "avg_generation_seconds": round(self._avg_elapsed, 1),
            "total_completed": self._completed_count,
        }

    def list_jobs(self, status: str = "active") -> list[dict]:
        """列出作业"""
        result = []
        for j in sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True):
            if status == "active" and j.status in ("completed", "failed", "cancelled"):
                continue
            result.append(self._job_to_dict(j))
        return result

    # ── 取消 ──────────────────────────────────────────

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False
        if job.status != "queued":
            return False  # 已经开始或已结束，不可取消
        job.status = "cancelled"
        job.completed_at = time.time()
        log.info(f"🚫 job_id={job_id} 已取消")
        return True

    # ── 清理 ──────────────────────────────────────────

    def cleanup(self, ttl: int = 1800):
        """清理过期的已完成作业（默认 30 分钟）"""
        now = time.time()
        expired = [
            jid for jid, j in self.jobs.items()
            if j.status in ("completed", "failed", "cancelled")
            and j.completed_at
            and (now - j.completed_at) > ttl
        ]
        for jid in expired:
            del self.jobs[jid]
        if expired:
            log.info(f"🧹 清理 {len(expired)} 个过期作业")

    # ── 后台 Worker ───────────────────────────────────

    async def _worker(self):
        while True:
            job = await self.queue.get()

            # 可能在排队期间被取消
            if job.status == "cancelled":
                self.queue.task_done()
                continue

            # 开始处理
            job.status = "processing"
            job.started_at = time.time()
            self.current_job = job
            log.info(f"🎨 job_id={job.job_id} 开始推理 | prompt='{job.request.prompt[:50]}...'")

            try:
                image, seed, elapsed = await _generate_image(job.request)

                buffer = io.BytesIO()
                image.save(buffer, format="PNG", optimize=True)
                img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

                job.result = {
                    "b64_json": img_b64 if job.request.response_format == "b64_json" else None,
                    "seed": seed,
                    "elapsed": elapsed,
                    "size": f"{image.width}x{image.height}",
                }
                job.status = "completed"
                job.completed_at = time.time()

                # 更新滑动平均
                self._completed_count += 1
                alpha = 0.3
                self._avg_elapsed = (
                    alpha * elapsed + (1 - alpha) * self._avg_elapsed
                )

                log.info(
                    f"✅ job_id={job.job_id} 完成 | "
                    f"elapsed={elapsed:.1f}s | avg={self._avg_elapsed:.1f}s"
                )

            except Exception as e:
                job.status = "failed"
                job.error = str(e)
                job.completed_at = time.time()
                log.error(f"❌ job_id={job.job_id} 失败：{e}")

            finally:
                self.current_job = None
                self.queue.task_done()

    # ── 辅助 ──────────────────────────────────────────

    def _job_to_dict(self, j: Job) -> dict:
        d = {
            "job_id": j.job_id,
            "status": j.status,
            "prompt": j.request.prompt[:100],
            "created_at": j.created_at,
            "started_at": j.started_at,
            "completed_at": j.completed_at,
            "elapsed": j.elapsed,
            "position": self.get_position(j),
        }
        if j.result:
            # 返回结果但不包含完整 base64（太大），调用 GET /jobs/{id} 获取完整结果
            d["result_summary"] = {
                "seed": j.result["seed"],
                "elapsed": j.result["elapsed"],
                "size": j.result["size"],
                "has_image": bool(j.result.get("b64_json")),
            }
        if j.error:
            d["error"] = j.error
        return d


# 全局 JobManager 实例（lifespan 中初始化）
job_manager: JobManager | None = None


# ═════════════════════════════════════════════════════════
# 模型下载
# ═════════════════════════════════════════════════════════

def download_from_modelscope(model_id: str, cache_dir: str) -> str:
    try:
        from modelscope import snapshot_download
    except ImportError:
        log.error("❌ 请先安装 modelscope：pip install modelscope")
        raise
    log.info(f"📥 ModelScope 下载：{model_id} → {cache_dir}")
    return snapshot_download(model_id, cache_dir=cache_dir, revision="master")


# ═════════════════════════════════════════════════════════
# 模型加载
# ═════════════════════════════════════════════════════════

def load_pipeline_cls():
    try:
        from diffusers import Flux2KleinPipeline
        return Flux2KleinPipeline
    except ImportError:
        pass
    try:
        from diffusers import FluxPipeline
        log.warning("⚠️ 降级为 FluxPipeline")
        return FluxPipeline
    except ImportError:
        pass
    raise ImportError("无法导入 FLUX Pipeline。pip install -U diffusers")


def load_model(model_path: str, device: str = "cuda", cpu_offload: bool = False):
    global pipe
    log.info(f"加载模型：{model_path}（device={device}）…")
    try:
        Pipeline = load_pipeline_cls()
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        pipe = Pipeline.from_pretrained(model_path, torch_dtype=dtype)
        if cpu_offload:
            pipe.enable_model_cpu_offload()
            log.info("CPU Offload 已启用")
        else:
            pipe = pipe.to(device)
            log.info(f"模型已移至 {device}")
        log.info("✅ 模型加载完成")
        return True
    except Exception as e:
        log.error(f"❌ 模型加载失败：{e}")
        return False


# ═════════════════════════════════════════════════════════
# 鉴权
# ═════════════════════════════════════════════════════════

def verify_api_key(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not API_KEY:
        return
    if credentials is None:
        raise HTTPException(status_code=401, detail="缺少 API Key")
    if credentials.credentials != API_KEY:
        raise HTTPException(status_code=403, detail="API Key 无效")
    return credentials


# ═════════════════════════════════════════════════════════
# Pydantic 模型
# ═════════════════════════════════════════════════════════

class ImageGenerationRequest(BaseModel):
    model: str = Field(default="black-forest-labs/FLUX.2-klein-9B")
    prompt: str = Field(..., min_length=1, max_length=4000)
    n: int = Field(default=1, ge=1, le=4)
    size: str = Field(default="1024x1024")
    response_format: Literal["url", "b64_json"] = Field(default="b64_json")
    user: Optional[str] = None
    negative_prompt: Optional[str] = Field(default=None, max_length=4000)
    seed: Optional[int] = Field(default=None, ge=0)
    num_inference_steps: Optional[int] = Field(default=None, ge=1, le=50)
    guidance_scale: Optional[float] = Field(default=None, ge=0.0, le=20.0)


class ImageData(BaseModel):
    url: Optional[str] = None
    b64_json: Optional[str] = None
    revised_prompt: Optional[str] = None


class ImageGenerationResponse(BaseModel):
    created: int
    data: List[ImageData]


class HealthResponse(BaseModel):
    status: str
    model: str
    device: str
    gpu_name: Optional[str] = None
    vram_total_gb: Optional[float] = None
    vram_free_gb: Optional[float] = None
    uptime_seconds: float
    model_source: str
    queue_length: int = 0
    current_job: Optional[str] = None
    total_completed: int = 0


# ═════════════════════════════════════════════════════════
# 图片生成核心
# ═════════════════════════════════════════════════════════

def parse_size(size_str: str) -> tuple[int, int]:
    try:
        w, h = size_str.lower().split("x")
        width = min(int(w), model_info["max_resolution"][0])
        height = min(int(h), model_info["max_resolution"][1])
        width = max(256, (width // 64) * 64)
        height = max(256, (height // 64) * 64)
        return width, height
    except Exception:
        return model_info["default_resolution"]


def get_generator(device: str, seed: int):
    if device == "cuda" and torch.cuda.is_available():
        return torch.Generator(device="cuda").manual_seed(seed)
    return torch.Generator(device="cpu").manual_seed(seed)


async def _generate_image(request: ImageGenerationRequest) -> tuple[Image.Image, int, float]:
    """在默认线程池中执行推理（不阻塞事件循环），返回 (image, seed, elapsed)"""
    global pipe
    if pipe is None:
        raise RuntimeError("模型未加载")

    width, height = parse_size(request.size)
    steps = request.num_inference_steps or model_info["num_inference_steps"]
    guidance = request.guidance_scale or model_info["guidance_scale"]
    device = model_info["device"]
    seed = request.seed if request.seed is not None else int(torch.randint(0, 2**31, (1,)).item())

    def _run():
        t0 = time.time()
        generator = get_generator(device, seed)
        result = pipe(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt or "",
            height=height,
            width=width,
            guidance_scale=guidance,
            num_inference_steps=steps,
            generator=generator,
        )
        elapsed = round(time.time() - t0, 1)
        return result.images[0], seed, elapsed

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run)


# ═════════════════════════════════════════════════════════
# FastAPI 应用
# ═════════════════════════════════════════════════════════

_resolved_model_source = "huggingface"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _resolved_model_source, job_manager
    log.info("=" * 60)
    log.info("🚀 FLUX.2-klein-9B 推理服务启动中…")
    log.info(f"   Model: {model_info['model_id']}")
    log.info(f"   Device: {model_info['device']}")
    log.info("=" * 60)

    # 初始化 JobManager
    max_concurrent = int(os.environ.get("FLUX_MAX_CONCURRENT", "1"))
    job_manager = JobManager(max_concurrent=max_concurrent)
    await job_manager.start()

    # 定期清理过期作业
    async def cleanup_loop():
        while True:
            await asyncio.sleep(300)  # 每 5 分钟
            job_manager.cleanup()

    cleanup_task = asyncio.create_task(cleanup_loop())

    # 加载模型
    model_path = os.environ.get("FLUX_MODEL_PATH", model_info["model_id"])
    if _resolved_model_source == "modelscope":
        try:
            cache_dir = os.environ.get("MODELSCOPE_CACHE", "./models")
            os.makedirs(cache_dir, exist_ok=True)
            model_path = download_from_modelscope(model_info["model_id"], cache_dir)
        except Exception as e:
            log.error(f"ModelScope 下载失败：{e}，降级 HuggingFace")
            _resolved_model_source = "huggingface"
            model_path = model_info["model_id"]

    success = load_model(
        model_path,
        device=model_info["device"],
        cpu_offload=os.environ.get("FLUX_CPU_OFFLOAD", "").lower() == "true",
    )
    if not success:
        log.error("模型加载失败，服务降级运行")

    yield

    # 关闭
    cleanup_task.cancel()
    await job_manager.stop()
    log.info("服务关闭")


app = FastAPI(
    title="FLUX.2-klein-9B Inference API",
    description="OpenAI 兼容文生图服务 + 任务队列 — WHMC AI 素养工作坊",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── 请求日志 ──────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    elapsed = time.time() - t0
    log.info(f"{request.method} {request.url.path} → {response.status_code} ({elapsed:.2f}s)")
    return response


# ── 全局异常 ──────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"异常：{exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": {"message": str(exc), "type": type(exc).__name__, "code": 500}},
    )


# ═════════════════════════════════════════════════════════
# 端点
# ═════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def root():
    hf_tip = ""
    if _resolved_model_source == "huggingface" and not os.environ.get("HF_ENDPOINT"):
        hf_tip = """
        <p style="color:#e67e22;background:rgba(230,126,34,0.1);padding:10px;border-radius:6px;">
        ⚠️ 国内用户建议：<code>export HF_ENDPOINT=https://hf-mirror.com</code>
        </p>"""
    return f"""
    <html><head><title>FLUX.2-klein-9B 推理服务</title></head>
    <body style="font-family:sans-serif;max-width:800px;margin:40px auto;padding:20px;">
      <h1>🎨 FLUX.2-klein-9B 推理服务</h1>
      <p>OpenAI 兼容 | 任务队列模式 | WHMC AI 素养工作坊</p>
      {hf_tip}
      <table border="1" cellpadding="8" style="border-collapse:collapse;">
        <tr><th>端点</th><th>方法</th><th>说明</th></tr>
        <tr><td><code>/v1/images/generations</code></td><td>POST</td><td>提交作业（异步）</td></tr>
        <tr><td><code>/v1/jobs/{{job_id}}</code></td><td>GET</td><td>查询作业状态</td></tr>
        <tr><td><code>/v1/queue</code></td><td>GET</td><td>队列看板</td></tr>
        <tr><td><code>/v1/models</code></td><td>GET</td><td>模型列表</td></tr>
        <tr><td><code>/health</code></td><td>GET</td><td>健康检查</td></tr>
      </table>
      <p style="margin-top:20px;"><a href="/v1/queue">📊 打开队列看板</a> | <a href="/docs">📖 API 文档</a></p>
    </body></html>"""


@app.get("/health", response_model=HealthResponse)
async def health():
    gpu_name = None
    vram_total = None
    vram_free = None
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        total = torch.cuda.get_device_properties(0).total_memory
        reserved = torch.cuda.memory_reserved(0)
        vram_total = total / (1024**3)
        vram_free = (total - reserved) / (1024**3)

    qs = job_manager.get_queue_status() if job_manager else {}

    return HealthResponse(
        status="healthy" if pipe is not None else "degraded",
        model=model_info["model_id"],
        device=model_info["device"],
        gpu_name=gpu_name,
        vram_total_gb=round(vram_total, 1) if vram_total else None,
        vram_free_gb=round(vram_free, 1) if vram_free else None,
        uptime_seconds=round(time.time() - start_time, 1),
        model_source=_resolved_model_source,
        queue_length=qs.get("queue_length", 0),
        current_job=qs["current_job"]["job_id"] if qs.get("current_job") else None,
        total_completed=qs.get("total_completed", 0),
    )


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{
            "id": model_info["model_id"],
            "object": "model",
            "created": 1700000000,
            "owned_by": "black-forest-labs",
        }],
    }


# ── 作业提交（异步模式，默认）──────────────────────────

@app.post("/v1/images/generations")
async def create_image(
    request: ImageGenerationRequest,
    sync: bool = Query(False, description="设为 true 则同步等待完成"),
    auth: Optional[HTTPAuthorizationCredentials] = Depends(verify_api_key),
):
    """
    文生图端点 — 异步作业模式（默认）

    **异步**（默认）：提交作业 → 立即返回 `{job_id, status:"queued", position}` → 轮询 `GET /v1/jobs/{job_id}`

    **同步**（?sync=true）：等待生成完成 → 返回 `{created, data:[{b64_json,...}]}`
    """
    if pipe is None:
        raise HTTPException(status_code=503, detail="模型未加载")

    if sync:
        # 兼容旧的同步模式
        return await _sync_generate(request)

    # 异步模式：提交到队列
    job_id = await job_manager.submit(request)
    job = job_manager.get(job_id)
    position = job_manager.get_position(job)

    return {
        "job_id": job_id,
        "status": "queued",
        "position": position,
        "queue_length": job_manager.get_queue_status()["queue_length"],
        "estimated_wait_seconds": round(position * job_manager._avg_elapsed),
        "message": "作业已提交。轮询 GET /v1/jobs/{job_id} 获取结果。也可用 ?sync=true 同步等待。",
    }


async def _sync_generate(request: ImageGenerationRequest):
    """同步生成（兼容旧 API），不经过队列，直接推理"""
    if job_manager and job_manager.current_job:
        raise HTTPException(
            status_code=429,
            detail=f"GPU 正忙（当前作业：{job_manager.current_job.job_id}）。"
                   f"请使用异步模式（不带 ?sync=true）提交作业。",
        )

    log.info(f"⚡ 同步生成：prompt='{request.prompt[:60]}...'")
    n = max(1, min(request.n, 4))
    results = []
    for i in range(n):
        image, seed, elapsed = await _generate_image(request)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        results.append(ImageData(
            b64_json=img_b64 if request.response_format == "b64_json" else None,
            revised_prompt=request.prompt,
        ))
    return ImageGenerationResponse(created=int(time.time()), data=results)


# ── 作业查询 ──────────────────────────────────────────

@app.get("/v1/jobs/{job_id}")
async def get_job(job_id: str):
    """查询作业状态。status=completed 时返回完整结果（含 base64 图片）。"""
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"作业不存在：{job_id}")

    response = {
        "job_id": job.job_id,
        "status": job.status,
        "prompt": job.request.prompt[:100],
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "elapsed": job.elapsed,
        "position": job_manager.get_position(job),
    }

    if job.status == "completed" and job.result:
        response["result"] = {
            "b64_json": job.result["b64_json"],
            "seed": job.result["seed"],
            "elapsed": job.result["elapsed"],
            "size": job.result["size"],
        }

    if job.status == "failed":
        response["error"] = job.error

    return response


@app.get("/v1/jobs")
async def list_jobs(
    status: str = Query("active", description="active（进行中）| all（全部）| completed | failed | queued"),
    limit: int = Query(20, ge=1, le=100),
):
    """列出作业"""
    jobs = job_manager.list_jobs(status=status)
    return {"count": len(jobs[:limit]), "jobs": jobs[:limit]}


@app.delete("/v1/jobs/{job_id}")
async def cancel_job(job_id: str):
    """取消排队中的作业"""
    ok = job_manager.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="作业不存在或已开始执行，无法取消")
    return {"job_id": job_id, "status": "cancelled", "message": "作业已取消"}


# ── 队列看板 ──────────────────────────────────────────

@app.get("/v1/queue")
async def queue_dashboard(request: Request):
    """
    队列看板 — Accept: text/html → 可视化页面，Accept: application/json → JSON
    """
    qs = job_manager.get_queue_status()

    # JSON 模式
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return qs

    # HTML 看板
    return HTMLResponse(_queue_html(qs))


def _queue_html(qs: dict) -> str:
    current = qs["current_job"]
    queued = qs["queued"]
    avg = qs["avg_generation_seconds"]
    total = qs["total_completed"]

    # 当前作业行
    current_row = ""
    if current:
        current_row = f"""
        <div class="card processing">
          <div class="status-dot"></div>
          <div>
            <strong>🔧 正在生成…</strong>
            <span class="mono">{current.get('job_id', '')}</span>
            <p class="prompt-text">"{current.get('prompt', '')}"</p>
            <p class="meta">⏱ 已耗时 {current.get('elapsed', 0)}s</p>
          </div>
        </div>"""
    else:
        current_row = """
        <div class="card idle">
          <div>😴 GPU 空闲，等待新作业…</div>
        </div>"""

    # 排队列表
    queue_rows = ""
    if queued:
        for q in queued:
            queue_rows += f"""
            <div class="card queued">
              <span class="pos-badge">#{q['position']}</span>
              <div>
                <span class="mono">{q['job_id']}</span>
                <p class="prompt-text">"{q['prompt']}"</p>
                <p class="meta">⏳ 预计等待 {q['estimated_wait_seconds']}s</p>
              </div>
            </div>"""
    else:
        queue_rows = '<div class="card empty">✅ 队列为空，提交作业立即开始</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="3">
<title>队列看板 — FLUX 推理服务</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: "Segoe UI", "Noto Sans SC", sans-serif;
    background: #0f1923;
    color: #e0e0e0;
    min-height: 100vh;
    padding: 24px;
  }}
  .container {{ max-width: 800px; margin: 0 auto; }}
  h1 {{ font-size: 22px; color: #c9a84c; margin-bottom: 4px; letter-spacing: 2px; }}
  .subtitle {{ font-size: 13px; color: #6b7b8b; margin-bottom: 24px; }}
  .stats {{
    display: flex; gap: 16px; margin-bottom: 20px;
  }}
  .stat {{
    flex: 1; background: #162433; border: 1px solid #243544;
    border-radius: 8px; padding: 16px; text-align: center;
  }}
  .stat .value {{ font-size: 28px; font-weight: bold; color: #c9a84c; }}
  .stat .label {{ font-size: 11px; color: #6b7b8b; margin-top: 4px; }}
  .card {{
    background: #162433; border: 1px solid #243544;
    border-radius: 8px; padding: 16px; margin-bottom: 10px;
    display: flex; align-items: center; gap: 14px;
  }}
  .card.processing {{
    border-color: #c9a84c;
    background: linear-gradient(135deg, #1a2d3d 0%, #162433 100%);
    animation: glow 2s infinite alternate;
  }}
  @keyframes glow {{
    0% {{ box-shadow: 0 0 8px rgba(201,168,76,0.1); }}
    100% {{ box-shadow: 0 0 20px rgba(201,168,76,0.25); }}
  }}
  .card.idle {{ color: #6b7b8b; justify-content: center; }}
  .card.empty {{ color: #4a9b5a; justify-content: center; }}
  .status-dot {{
    width: 14px; height: 14px; border-radius: 50%;
    background: #c9a84c; animation: pulse 1.2s infinite;
    flex-shrink: 0;
  }}
  @keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.3; }}
  }}
  .pos-badge {{
    background: #c9a84c; color: #0f1923; font-weight: bold;
    font-size: 14px; width: 32px; height: 32px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  }}
  .mono {{ font-family: "Consolas", "Menlo", monospace; font-size: 11px; color: #8899aa; }}
  .prompt-text {{ font-size: 14px; color: #c0c8d0; margin-top: 4px; }}
  .meta {{ font-size: 11px; color: #6b7b8b; margin-top: 4px; }}
  .footer {{ margin-top: 24px; font-size: 11px; color: #4a5a6a; text-align: center; }}
  .footer span {{ color: #6b7b8b; }}
</style>
</head>
<body>
<div class="container">
  <h1>📊 FLUX.2-klein-9B 推理队列</h1>
  <p class="subtitle">每 3 秒自动刷新 | 异步作业模式</p>

  <div class="stats">
    <div class="stat">
      <div class="value">{total}</div>
      <div class="label">已完成</div>
    </div>
    <div class="stat">
      <div class="value">{qs['queue_length']}</div>
      <div class="label">排队中</div>
    </div>
    <div class="stat">
      <div class="value">{avg}s</div>
      <div class="label">平均耗时</div>
    </div>
  </div>

  <h3 style="font-size:14px;color:#8899aa;margin-bottom:10px;">当前作业</h3>
  {current_row}

  <h3 style="font-size:14px;color:#8899aa;margin-bottom:10px;">排队列表</h3>
  {queue_rows}

  <div class="footer">
    <span>API:</span> POST /v1/images/generations
    <span>|</span> GET /v1/jobs/&#123;job_id&#125;
    <span>|</span> <a href="/docs" style="color:#c9a84c;">Swagger 文档</a>
  </div>
</div>
</body>
</html>"""


# ── 批量端点（作业模式）────────────────────────────────

@app.post("/v1/images/generations/batch")
async def create_images_batch(
    requests: List[ImageGenerationRequest],
    auth: Optional[HTTPAuthorizationCredentials] = Depends(verify_api_key),
):
    """批量提交作业"""
    job_ids = []
    for req in requests:
        jid = await job_manager.submit(req)
        job_ids.append({
            "job_id": jid,
            "prompt": req.prompt[:60],
            "status": "queued",
        })
    return {
        "message": f"已提交 {len(requests)} 个作业",
        "queue_length": job_manager.get_queue_status()["queue_length"],
        "jobs": job_ids,
    }


# ═════════════════════════════════════════════════════════
# 入口
# ═════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(
        description="FLUX.2-klein-9B 推理服务（任务队列版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python server.py --model-source modelscope
  python server.py --model-path ./models/FLUX.2-klein-9B
  python server.py --host 0.0.0.0 --port 5500
        """,
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5500)
    parser.add_argument("--model", default="black-forest-labs/FLUX.2-klein-9B")
    parser.add_argument("--model-source", default="huggingface",
                        choices=["huggingface", "modelscope", "local"])
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--cpu-offload", action="store_true")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    model_info["model_id"] = args.model
    model_info["device"] = args.device
    _resolved_model_source = args.model_source

    if args.cpu_offload:
        os.environ["FLUX_CPU_OFFLOAD"] = "true"
    if args.model_path:
        os.environ["FLUX_MODEL_PATH"] = args.model_path

    log.info(f"启动：http://{args.host}:{args.port}")
    log.info(f"看板：http://{args.host}:{args.port}/v1/queue")

    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        timeout_keep_alive=120,
    )
