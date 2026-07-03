"""
Higgs Audio v3 TTS 推理服务 — FastAPI + Job Queue
==================================================
基于 SGLang-Omni 后端，封装 OpenAI 兼容 /v1/audio/speech 端点。
前端 FastAPI 提供：作业队列、状态轮询、队列看板。

架构：
  教师 → FastAPI :8100 → Job Queue → SGLang-Omni :18100 → GPU

部署：
  1. 安装 SGLang-Omni：pip install sglang-omni
  2. 下载模型到 ./models/higgs-audio-v3-tts-4b
  3. python server.py --host 0.0.0.0 --port 8100
"""

import io
import os
import sys
import time
import uuid
import json
import base64
import logging
import argparse
import asyncio
import subprocess
import signal
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Literal
from contextlib import asynccontextmanager

import requests as sync_requests  # 用于内部调用 SGLang
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
log = logging.getLogger("higgs-server")

# ── 全局 ───────────────────────────────────────────────
API_KEY = os.environ.get("TTS_API_KEY", "")
security = HTTPBearer(auto_error=False)
start_time = time.time()

# SGLang 后端地址（内部）
SGLANG_PORT = int(os.environ.get("SGLANG_PORT", "18100"))
SGLANG_URL = f"http://127.0.0.1:{SGLANG_PORT}"

sglang_process: subprocess.Popen | None = None


# ═════════════════════════════════════════════════════════
# Job Queue（同 FLUX 服务架构）
# ═════════════════════════════════════════════════════════

@dataclass
class Job:
    job_id: str
    request: "TTSRequest"
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: dict | None = None
    error: str | None = None

    @property
    def elapsed(self) -> float | None:
        if self.completed_at and self.started_at:
            return round(self.completed_at - self.started_at, 1)
        return None


class JobManager:
    def __init__(self):
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.jobs: dict[str, Job] = {}
        self.current_job: Job | None = None
        self._worker_task: asyncio.Task | None = None
        self._avg_elapsed: float = 2.0
        self._completed_count: int = 0

    async def start(self):
        self._worker_task = asyncio.create_task(self._worker())
        log.info("👷 Worker 已启动")

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()

    async def submit(self, request: "TTSRequest") -> str:
        job = Job(job_id=uuid.uuid4().hex[:12], request=request)
        self.jobs[job.job_id] = job
        await self.queue.put(job)
        log.info(f"📥 job={job.job_id} | input='{request.input[:50]}...' | q={self.queue.qsize()}")
        return job.job_id

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def get_position(self, job: Job) -> int:
        if job.status == "processing": return 0
        if job.status in ("completed", "failed", "cancelled"): return -1
        pos = sum(1 for j in self.jobs.values()
                  if j.status == "queued" and j.created_at < job.created_at)
        return pos + (1 if self.current_job else 0)

    def get_queue_status(self) -> dict:
        queued = sorted(
            [j for j in self.jobs.values() if j.status == "queued"],
            key=lambda j: j.created_at,
        )
        return {
            "queue_length": len(queued),
            "current_job": {
                "job_id": self.current_job.job_id,
                "input": self.current_job.request.input[:80],
                "elapsed": round(time.time() - self.current_job.started_at, 1)
                if self.current_job and self.current_job.started_at else None,
            } if self.current_job else None,
            "queued": [
                {"job_id": j.job_id, "input": j.request.input[:60],
                 "position": i + 1, "estimated_wait_s": round((i + 1) * self._avg_elapsed)}
                for i, j in enumerate(queued)
            ],
            "avg_elapsed": round(self._avg_elapsed, 1),
            "total_completed": self._completed_count,
        }

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.status != "queued": return False
        job.status = "cancelled"
        job.completed_at = time.time()
        return True

    def cleanup(self, ttl: int = 1800):
        now = time.time()
        expired = [jid for jid, j in self.jobs.items()
                    if j.status in ("completed", "failed", "cancelled")
                    and j.completed_at and (now - j.completed_at) > ttl]
        for jid in expired:
            del self.jobs[jid]

    async def _worker(self):
        while True:
            job = await self.queue.get()
            if job.status == "cancelled":
                self.queue.task_done()
                continue

            job.status = "processing"
            job.started_at = time.time()
            self.current_job = job
            log.info(f"🔊 job={job.job_id} 推理中…")

            try:
                audio_b64, duration, elapsed = await _tts_inference(job.request)

                job.result = {
                    "audio_b64_json": audio_b64,
                    "duration_s": duration,
                    "elapsed_s": elapsed,
                    "format": "wav",
                }
                job.status = "completed"
                job.completed_at = time.time()

                self._completed_count += 1
                self._avg_elapsed = 0.3 * elapsed + 0.7 * self._avg_elapsed
                log.info(f"✅ job={job.job_id} | {elapsed:.1f}s | audio={duration:.1f}s")

            except Exception as e:
                job.status = "failed"
                job.error = str(e)
                job.completed_at = time.time()
                log.error(f"❌ job={job.job_id} | {e}")

            finally:
                self.current_job = None
                self.queue.task_done()


job_manager: JobManager | None = None


# ═════════════════════════════════════════════════════════
# TTS 推理（调用 SGLang 后端）
# ═════════════════════════════════════════════════════════

async def _tts_inference(request: "TTSRequest") -> tuple[str, float, float]:
    """调用 SGLang /v1/audio/speech，返回 (base64_wav, duration_s, elapsed_s)"""
    t0 = time.time()

    payload: dict = {
        "model": "higgs-audio-v3-tts",
        "input": request.input,
        "voice": request.voice,
        "response_format": "wav",
    }
    if request.speed is not None:
        payload["speed"] = request.speed

    # 语音克隆：传参考音频
    files = {}
    if request.reference_audio_b64:
        # base64 → 临时文件
        ref_bytes = base64.b64decode(request.reference_audio_b64)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(ref_bytes)
        tmp.close()
        files["reference_audio"] = (os.path.basename(tmp.name), open(tmp.name, "rb"), "audio/wav")
        if request.reference_text:
            payload["reference_text"] = request.reference_text

    try:
        loop = asyncio.get_event_loop()

        def _call():
            if files:
                return sync_requests.post(
                    f"{SGLANG_URL}/v1/audio/speech",
                    data=payload, files=files, timeout=120,
                )
            return sync_requests.post(
                f"{SGLANG_URL}/v1/audio/speech",
                json=payload, timeout=120,
            )

        resp = await loop.run_in_executor(None, _call)
        resp.raise_for_status()

        # 获取音频时长
        audio_bytes = resp.content
        duration = _get_wav_duration(audio_bytes)

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        elapsed = round(time.time() - t0, 1)

        return audio_b64, duration, elapsed

    finally:
        # 清理临时文件
        for _, (_, fh, _) in files.items():
            fh.close()
        if files:
            for _, (name, _, _) in files.items():
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass


def _get_wav_duration(wav_bytes: bytes) -> float:
    """从 WAV 字节计算音频时长（秒）"""
    try:
        import struct
        # WAV header: bytes 24-27 = sample_rate, 28-31 = byte_rate
        sample_rate = struct.unpack('<I', wav_bytes[24:28])[0]
        data_size = struct.unpack('<I', wav_bytes[40:44])[0]
        return round(data_size / (sample_rate * 2), 1)  # 16-bit = 2 bytes/sample
    except Exception:
        return 0.0


# ═════════════════════════════════════════════════════════
# Pydantic 模型
# ═════════════════════════════════════════════════════════

class TTSRequest(BaseModel):
    """TTS 请求体（OpenAI 兼容 + Higgs 扩展）"""
    model: str = Field(default="higgs-audio-v3-tts")
    input: str = Field(..., min_length=1, max_length=5000,
                       description="要合成的文本。支持内联控制标签：<|emotion:joy|>, <|sfx:laughter|>, <|prosody:speed_slow|>")
    voice: str = Field(default="nova", description="预置音色：alloy, ash, coral, echo, fable, nova, onyx, sage, shimmer")
    speed: Optional[float] = Field(default=None, ge=0.25, le=4.0, description="语速倍率")
    response_format: str = Field(default="wav")
    # ── 语音克隆（可选）─────────────────────────
    reference_audio_b64: Optional[str] = Field(default=None,
                                                description="参考音频 Base64（WAV 格式），提供后自动克隆音色")
    reference_text: Optional[str] = Field(default=None,
                                           description="参考音频的文本内容（提高克隆质量）")


class TTSResponse(BaseModel):
    """同步 TTS 响应（?sync=true）"""
    audio_b64_json: str
    duration_s: float
    elapsed_s: float


class HealthResponse(BaseModel):
    status: str
    model: str
    backend: str
    sglang_ok: bool
    uptime_s: float
    queue_length: int = 0
    total_completed: int = 0


# ═════════════════════════════════════════════════════════
# SGLang 生命周期管理
# ═════════════════════════════════════════════════════════

def start_sglang(model_path: str, port: int):
    """启动 SGLang-Omni 子进程"""
    global sglang_process
    cmd = [
        "sgl-omni", "serve",
        "--model-path", model_path,
        "--port", str(port),
        "--host", "127.0.0.1",
    ]
    log.info(f"🚀 启动 SGLang-Omni：{' '.join(cmd)}")
    sglang_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # 等待 SGLang 就绪
    for line in sglang_process.stdout:
        log.info(f"[SGLang] {line.rstrip()}")
        if "Uvicorn running" in line or "Application startup complete" in line:
            break

    # 额外等待确保模型加载完成
    time.sleep(3)
    log.info("✅ SGLang-Omni 就绪")


def stop_sglang():
    global sglang_process
    if sglang_process:
        sglang_process.send_signal(signal.SIGTERM)
        try:
            sglang_process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            sglang_process.kill()
        log.info("🛑 SGLang-Omni 已停止")


# ═════════════════════════════════════════════════════════
# FastAPI 应用
# ═════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    global job_manager

    log.info("=" * 60)
    log.info("🎙️  Higgs Audio v3 TTS 服务启动中…")
    log.info(f"   后端: SGLang-Omni @ {SGLANG_URL}")
    log.info("=" * 60)

    # 启动 SGLang（如果模型路径存在）
    model_path = os.environ.get("HIGGS_MODEL_PATH", "./models/higgs-audio-v3-tts-4b")
    if Path(model_path).exists():
        start_sglang(model_path, SGLANG_PORT)
    else:
        log.warning(f"⚠️ 模型路径不存在：{model_path}")
        log.warning("   请先下载模型：huggingface-cli download bosonai/higgs-audio-v3-tts-4b --local-dir ./models/higgs-audio-v3-tts-4b")
        log.warning("   服务将启动，但 TTS 推理不可用")

    job_manager = JobManager()
    await job_manager.start()

    # 定期清理
    async def cleanup_loop():
        while True:
            await asyncio.sleep(300)
            job_manager.cleanup()

    cleanup_task = asyncio.create_task(cleanup_loop())

    yield

    cleanup_task.cancel()
    await job_manager.stop()
    stop_sglang()
    log.info("服务关闭")


app = FastAPI(
    title="Higgs Audio v3 TTS API",
    description="OpenAI 兼容 TTS 服务 + 任务队列 — WHMC AI 素养工作坊",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    resp = await call_next(request)
    log.info(f"{request.method} {request.url.path} → {resp.status_code} ({time.time() - t0:.2f}s)")
    return resp


def verify_api_key(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not API_KEY: return
    if creds is None: raise HTTPException(401, "缺少 API Key")
    if creds.credentials != API_KEY: raise HTTPException(403, "API Key 无效")


# ═════════════════════════════════════════════════════════
# 端点
# ═════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def root():
    return f"""
    <html><head><title>Higgs Audio v3 TTS</title></head>
    <body style="font-family:sans-serif;max-width:700px;margin:40px auto;padding:20px;">
      <h1>🎙️ Higgs Audio v3 TTS 服务</h1>
      <p>OpenAI 兼容 | 作业队列 | WHMC AI 素养工作坊</p>
      <table border="1" cellpadding="8" style="border-collapse:collapse;">
        <tr><th>端点</th><th>方法</th><th>说明</th></tr>
        <tr><td><code>/v1/audio/speech</code></td><td>POST</td><td>提交 TTS 作业（异步）</td></tr>
        <tr><td><code>/v1/jobs/{{job_id}}</code></td><td>GET</td><td>查询作业 + 获取音频</td></tr>
        <tr><td><code>/v1/queue</code></td><td>GET</td><td>队列看板</td></tr>
        <tr><td><code>/health</code></td><td>GET</td><td>健康检查</td></tr>
      </table>
      <p><a href="/v1/queue">📊 队列看板</a> | <a href="/docs">📖 API 文档</a></p>
    </body></html>"""


@app.get("/health", response_model=HealthResponse)
async def health():
    sglang_ok = False
    try:
        resp = sync_requests.get(f"{SGLANG_URL}/health", timeout=5)
        sglang_ok = resp.status_code == 200
    except Exception:
        pass

    qs = job_manager.get_queue_status() if job_manager else {}
    return HealthResponse(
        status="healthy" if sglang_ok else "degraded",
        model="bosonai/higgs-audio-v3-tts-4b",
        backend="SGLang-Omni",
        sglang_ok=sglang_ok,
        uptime_s=round(time.time() - start_time, 1),
        queue_length=qs.get("queue_length", 0),
        total_completed=qs.get("total_completed", 0),
    )


# ── TTS 提交（异步）───────────────────────────────────

@app.post("/v1/audio/speech")
async def create_speech(
    request: TTSRequest,
    sync: bool = Query(False, description="同步等待完成"),
    auth=Depends(verify_api_key),
):
    """
    TTS 端点 — 异步作业模式（默认）

    内联控制标签：
      <|emotion:joy|> <|emotion:sadness|> <|emotion:fear|>
      <|emotion:enthusiasm|> <|emotion:amusement|>
      <|sfx:laughter|> <|sfx:sigh|>
      <|prosody:speed_slow|> <|prosody:speed_fast|>
      <|prosody:pitch_high|> <|prosody:pitch_low|>
      <|prosody:long_pause|> <|prosody:short_pause|>
    """
    if sync:
        audio_b64, duration, elapsed = await _tts_inference(request)
        return TTSResponse(audio_b64_json=audio_b64, duration_s=duration, elapsed_s=elapsed)

    job_id = await job_manager.submit(request)
    job = job_manager.get(job_id)
    return {
        "job_id": job_id,
        "status": "queued",
        "position": job_manager.get_position(job),
        "queue_length": job_manager.get_queue_status()["queue_length"],
        "estimated_wait_s": round(job_manager.get_position(job) * job_manager._avg_elapsed),
    }


# ── 作业查询 ──────────────────────────────────────────

@app.get("/v1/jobs/{job_id}")
async def get_job(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(404, f"作业不存在：{job_id}")

    resp = {
        "job_id": job.job_id, "status": job.status,
        "input": job.request.input[:120],
        "created_at": job.created_at, "started_at": job.started_at,
        "completed_at": job.completed_at, "elapsed": job.elapsed,
        "position": job_manager.get_position(job),
    }

    if job.status == "completed" and job.result:
        resp["result"] = {
            "audio_b64_json": job.result["audio_b64_json"],
            "duration_s": job.result["duration_s"],
            "elapsed_s": job.result["elapsed_s"],
            "format": job.result["format"],
        }
    if job.status == "failed":
        resp["error"] = job.error

    return resp


@app.get("/v1/jobs")
async def list_jobs(status: str = Query("active"), limit: int = Query(20, le=100)):
    all_jobs = sorted(job_manager.jobs.values(), key=lambda j: j.created_at, reverse=True)
    filtered = [j for j in all_jobs if status == "all" or j.status not in ("completed", "failed", "cancelled")]
    return {"count": len(filtered[:limit]), "jobs": [_job_summary(j) for j in filtered[:limit]]}


@app.delete("/v1/jobs/{job_id}")
async def cancel_job(job_id: str):
    if not job_manager.cancel(job_id):
        raise HTTPException(400, "作业不存在或已开始")
    return {"job_id": job_id, "status": "cancelled"}


def _job_summary(j: Job) -> dict:
    d = {"job_id": j.job_id, "status": j.status, "input": j.request.input[:80],
         "elapsed": j.elapsed, "position": job_manager.get_position(j)}
    if j.result:
        d["duration_s"] = j.result["duration_s"]
    if j.error:
        d["error"] = j.error
    return d


# ── 队列看板 ──────────────────────────────────────────

@app.get("/v1/queue")
async def queue_dashboard(request: Request):
    qs = job_manager.get_queue_status()
    if "application/json" in request.headers.get("accept", ""):
        return qs
    return HTMLResponse(_queue_html(qs))


def _queue_html(qs: dict) -> str:
    cur = qs["current_job"]
    queued = qs["queued"]
    cur_row = ""
    if cur:
        cur_row = f"""<div class="card processing"><div class="dot"></div><div>
          <strong>🔊 正在合成…</strong> <span class="mono">{cur.get('job_id','')}</span>
          <p class="text">"{cur.get('input','')}"</p>
          <p class="meta">⏱ {cur.get('elapsed',0)}s</p></div></div>"""
    else:
        cur_row = '<div class="card idle">😴 空闲</div>'

    queue_rows = ""
    if queued:
        for q in queued:
            queue_rows += f"""<div class="card queued"><span class="pos">#{q['position']}</span><div>
              <span class="mono">{q['job_id']}</span>
              <p class="text">"{q['input']}"</p>
              <p class="meta">⏳ ~{q['estimated_wait_s']}s</p></div></div>"""
    else:
        queue_rows = '<div class="card empty">✅ 队列为空</div>'

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta http-equiv="refresh" content="3">
<title>TTS 队列看板</title><style>
*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:"Segoe UI","Noto Sans SC",sans-serif;background:#0f1923;color:#e0e0e0;min-height:100vh;padding:24px}}.container{{max-width:750px;margin:0 auto}}
h1{{font-size:22px;color:#5dade2;margin-bottom:4px}}.sub{{font-size:13px;color:#6b7b8b;margin-bottom:20px}}
.stats{{display:flex;gap:16px;margin-bottom:20px}}.stat{{flex:1;background:#162433;border:1px solid #243544;border-radius:8px;padding:16px;text-align:center}}
.stat .v{{font-size:28px;font-weight:bold;color:#5dade2}}.stat .l{{font-size:11px;color:#6b7b8b;margin-top:4px}}
.card{{background:#162433;border:1px solid #243544;border-radius:8px;padding:16px;margin-bottom:10px;display:flex;align-items:center;gap:14px}}
.card.processing{{border-color:#5dade2;background:linear-gradient(135deg,#1a2d3d 0%,#162433 100%);animation:glow 2s infinite alternate}}
@keyframes glow{{0%{{box-shadow:0 0 8px rgba(93,173,226,0.1)}}100%{{box-shadow:0 0 20px rgba(93,173,226,0.25)}}}}
.card.idle{{color:#6b7b8b;justify-content:center}}.card.empty{{color:#4a9b5a;justify-content:center}}
.dot{{width:14px;height:14px;border-radius:50%;background:#5dade2;animation:pulse 1.2s infinite;flex-shrink:0}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.pos{{background:#5dade2;color:#0f1923;font-weight:bold;font-size:14px;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.mono{{font-family:Consolas,Menlo,monospace;font-size:11px;color:#8899aa}}.text{{font-size:14px;color:#c0c8d0;margin-top:4px}}
.meta{{font-size:11px;color:#6b7b8b;margin-top:4px}}.footer{{margin-top:24px;font-size:11px;color:#4a5a6a;text-align:center}}
</style></head><body><div class="container">
<h1>🎙️ Higgs Audio v3 TTS 队列</h1><p class="sub">3s 刷新 | 异步作业模式</p>
<div class="stats"><div class="stat"><div class="v">{qs['total_completed']}</div><div class="l">已完成</div></div>
<div class="stat"><div class="v">{qs['queue_length']}</div><div class="l">排队中</div></div>
<div class="stat"><div class="v">{qs['avg_elapsed']}s</div><div class="l">平均耗时</div></div></div>
<h3 style="font-size:14px;color:#8899aa;margin-bottom:10px;">当前作业</h3>{cur_row}
<h3 style="font-size:14px;color:#8899aa;margin-bottom:10px;">排队列表</h3>{queue_rows}
<div class="footer">POST /v1/audio/speech | GET /v1/jobs/&#123;job_id&#125; | <a href="/docs" style="color:#5dade2">Swagger</a></div>
</div></body></html>"""


# ═════════════════════════════════════════════════════════
# 入口
# ═════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Higgs Audio v3 TTS 服务")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--sglang-port", type=int, default=18100, help="SGLang 内部端口")
    parser.add_argument("--model-path", default="./models/higgs-audio-v3-tts-4b")
    parser.add_argument("--no-sglang", action="store_true", help="不自动启动 SGLang")
    args = parser.parse_args()

    os.environ["HIGGS_MODEL_PATH"] = args.model_path
    os.environ["SGLANG_PORT"] = str(args.sglang_port)
    SGLANG_PORT = args.sglang_port
    SGLANG_URL = f"http://127.0.0.1:{SGLANG_PORT}"

    if args.no_sglang:
        log.info("⚠️ --no-sglang：请确保 SGLang 已在 :{SGLANG_PORT} 运行")

    log.info(f"启动：http://{args.host}:{args.port}")
    log.info(f"SGLang：{SGLANG_URL}")

    uvicorn.run("server:app", host=args.host, port=args.port,
                reload=False, timeout_keep_alive=120)
