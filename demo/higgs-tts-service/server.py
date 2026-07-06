"""
Higgs Audio v3 TTS 推理服务 — 纯 transformers 版
=================================================
基于 multimodalart/higgs-audio-v3-tts-4b-transformers，
不依赖 SGLang-Omni，直接用 AutoModelForCausalLM 推理。

部署：
  1. pip install "transformers>=5.5" torch torchaudio
  2. 模型文件放到 ./models/higgs-audio-v3-tts-4b/
  3. Bridge 文件已预置在 models/higgs-audio-v3-tts-4b/ 中
     （modeling_higgs_multimodal_qwen3.py + configuration_higgs_multimodal_qwen3.py）
  4. python server.py --host 0.0.0.0 --port 8100
"""

import io, os, sys, time, uuid, json, base64, logging, argparse, asyncio
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List
from contextlib import asynccontextmanager

import torch
import torchaudio
from fastapi import FastAPI, HTTPException, Request, Query, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-5s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("higgs-server")

API_KEY = os.environ.get("TTS_API_KEY", "")
security = HTTPBearer(auto_error=False)
start_time = time.time()

pipe = None   # model
tok = None    # tokenizer
model_config = None


# ═════════════════════════════════════════════════════════
# Job Queue
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
                 "position": i + 1,
                 "estimated_wait_s": round((i + 1) * self._avg_elapsed)}
                for i, j in enumerate(queued)
            ],
            "avg_elapsed": round(self._avg_elapsed, 1),
            "total_completed": self._completed_count,
        }

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.status != "queued": return False
        job.status = "cancelled"; job.completed_at = time.time()
        return True

    def cleanup(self, ttl: int = 1800):
        now = time.time()
        expired = [jid for jid, j in self.jobs.items()
                    if j.status in ("completed", "failed", "cancelled")
                    and j.completed_at and (now - j.completed_at) > ttl]
        for jid in expired: del self.jobs[jid]

    async def _worker(self):
        while True:
            job = await self.queue.get()
            if job.status == "cancelled": self.queue.task_done(); continue
            job.status = "processing"; job.started_at = time.time()
            self.current_job = job

            try:
                audio_b64, duration, elapsed = await _tts_inference(job.request)
                job.result = {"audio_b64_json": audio_b64, "duration_s": duration,
                              "elapsed_s": elapsed, "format": "wav"}
                job.status = "completed"; job.completed_at = time.time()
                self._completed_count += 1
                self._avg_elapsed = 0.3 * elapsed + 0.7 * self._avg_elapsed
                log.info(f"✅ job={job.job_id} | {elapsed:.1f}s | audio={duration:.1f}s")
            except Exception as e:
                job.status = "failed"; job.error = str(e); job.completed_at = time.time()
                log.error(f"❌ job={job.job_id} | {e}")
            finally:
                self.current_job = None; self.queue.task_done()


job_manager: JobManager | None = None


# ═════════════════════════════════════════════════════════
# 模型加载
# ═════════════════════════════════════════════════════════

def load_model(model_path: str):
    """加载 Higgs v3 模型（纯 transformers，无 SGLang 依赖）"""
    global pipe, tok, model_config
    import importlib.util

    log.info(f"加载模型：{model_path}")

    # 手动加载自定义 config/modeling 类（解决 trust_remote_code 的注册顺序问题）
    model_dir = Path(model_path)
    config_file = model_dir / "configuration_higgs_multimodal_qwen3.py"
    modeling_file = model_dir / "modeling_higgs_multimodal_qwen3.py"

    if not config_file.exists():
        raise FileNotFoundError(f"缺少 config 文件：{config_file}")

    # 导入自定义 configuration 模块
    spec = importlib.util.spec_from_file_location("higgs_config", config_file)
    config_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_mod)
    HiggsConfig = config_mod.HiggsMultimodalQwen3Config

    # 导入自定义 modeling 模块
    spec2 = importlib.util.spec_from_file_location("higgs_modeling", modeling_file)
    model_mod = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(model_mod)
    HiggsModel = model_mod.HiggsMultimodalQwen3ForConditionalGeneration

    # 用自定义类直接加载
    from transformers import AutoTokenizer
    model_config = HiggsConfig.from_pretrained(model_path)
    tok = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    pipe = HiggsModel.from_pretrained(
        model_path,
        config=model_config,
        torch_dtype=torch.bfloat16,
    ).to("cuda").eval()

    log.info(f"✅ 模型加载完成 | sample_rate={model_config.sample_rate}")


# ═════════════════════════════════════════════════════════
# TTS 推理
# ═════════════════════════════════════════════════════════

async def _tts_inference(request: "TTSRequest") -> tuple[str, float, float]:
    global pipe, tok
    if pipe is None: raise RuntimeError("模型未加载")

    t0 = time.time()

    def _run():
        kwargs: dict = {}

        # 语音克隆
        if request.reference_audio_b64:
            ref_bytes = base64.b64decode(request.reference_audio_b64)
            ref_audio, ref_sr = torchaudio.load(io.BytesIO(ref_bytes))
            # 转为单声道 24kHz（Higgs 输入格式）
            if ref_audio.shape[0] > 1:
                ref_audio = ref_audio.mean(dim=0, keepdim=True)
            if ref_sr != model_config.sample_rate:
                resampler = torchaudio.transforms.Resample(ref_sr, model_config.sample_rate)
                ref_audio = resampler(ref_audio)
            kwargs["reference_audio"] = ref_audio.squeeze(0)
            kwargs["reference_sample_rate"] = model_config.sample_rate
            if request.reference_text:
                kwargs["reference_text"] = request.reference_text

        # 速度
        if request.speed is not None:
            kwargs["speed"] = request.speed

        wav = pipe.generate_speech(request.input, tok, **kwargs)
        wav = wav.float().cpu()

        # 保存为 WAV bytes
        buf = io.BytesIO()
        torchaudio.save(buf, wav.unsqueeze(0), model_config.sample_rate, format="wav")
        buf.seek(0)
        audio_bytes = buf.read()

        duration = len(wav) / model_config.sample_rate
        elapsed = time.time() - t0
        return base64.b64encode(audio_bytes).decode("utf-8"), round(duration, 1), round(elapsed, 1)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run)


# ═════════════════════════════════════════════════════════
# Pydantic 模型
# ═════════════════════════════════════════════════════════

class TTSRequest(BaseModel):
    model: str = Field(default="higgs-audio-v3-tts")
    input: str = Field(..., min_length=1, max_length=5000,
                       description="要合成的文本。支持内联控制标签：<|emotion:joy|>, <|sfx:laughter|>")
    voice: str = Field(default="nova")
    speed: Optional[float] = Field(default=None, ge=0.25, le=4.0)
    response_format: str = Field(default="wav")
    reference_audio_b64: Optional[str] = Field(default=None, description="参考音频 Base64（语音克隆）")
    reference_text: Optional[str] = Field(default=None, description="参考音频文本内容")


class HealthResponse(BaseModel):
    status: str
    model: str
    backend: str
    uptime_s: float
    queue_length: int = 0
    total_completed: int = 0


# ═════════════════════════════════════════════════════════
# FastAPI
# ═════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    global job_manager
    log.info("=" * 60)
    log.info("🎙️  Higgs Audio v3 TTS 服务（纯 transformers 版）")
    log.info("=" * 60)

    model_path = os.environ.get("HIGGS_MODEL_PATH", "./models/higgs-audio-v3-tts-4b")
    if Path(model_path).exists():
        load_model(model_path)
    else:
        log.warning(f"⚠️ 模型路径不存在：{model_path}")

    job_manager = JobManager()
    await job_manager.start()

    async def cleanup_loop():
        while True:
            await asyncio.sleep(300)
            job_manager.cleanup()
    cleanup_task = asyncio.create_task(cleanup_loop())

    yield
    cleanup_task.cancel()
    await job_manager.stop()
    log.info("服务关闭")


app = FastAPI(title="Higgs Audio v3 TTS API", version="2.0.0", lifespan=lifespan, docs_url="/docs")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    resp = await call_next(request)
    log.info(f"{request.method} {request.url.path} → {resp.status_code} ({time.time()-t0:.2f}s)")
    return resp


def verify_api_key(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not API_KEY: return
    if creds is None: raise HTTPException(401, "缺少 API Key")
    if creds.credentials != API_KEY: raise HTTPException(403, "API Key 无效")


@app.get("/", response_class=HTMLResponse)
async def root():
    return f"""<html><head><title>Higgs Audio v3 TTS</title></head>
<body style="font-family:sans-serif;max-width:700px;margin:40px auto;">
<h1>🎙️ Higgs Audio v3 TTS 服务</h1>
<p>纯 transformers 推理 | WHMC 工作坊</p>
<table border="1" cellpadding="8"><tr><th>端点</th><th>方法</th><th>说明</th></tr>
<tr><td><code>/v1/audio/speech</code></td><td>POST</td><td>提交 TTS 作业</td></tr>
<tr><td><code>/v1/jobs/{{id}}</code></td><td>GET</td><td>查询作业</td></tr>
<tr><td><code>/v1/queue</code></td><td>GET</td><td>队列看板</td></tr>
<tr><td><code>/health</code></td><td>GET</td><td>健康检查</td></tr></table>
<p><a href="/v1/queue">📊 看板</a> | <a href="/docs">📖 Swagger</a></p></body></html>"""


@app.get("/health", response_model=HealthResponse)
async def health():
    qs = job_manager.get_queue_status() if job_manager else {}
    return HealthResponse(
        status="healthy" if pipe is not None else "degraded",
        model="bosonai/higgs-audio-v3-tts-4b",
        backend="transformers",
        uptime_s=round(time.time() - start_time, 1),
        queue_length=qs.get("queue_length", 0),
        total_completed=qs.get("total_completed", 0),
    )


@app.post("/v1/audio/speech")
async def create_speech(request: TTSRequest, sync: bool = Query(False),
                        auth=Depends(verify_api_key)):
    if sync:
        audio_b64, duration, elapsed = await _tts_inference(request)
        return {"audio_b64_json": audio_b64, "duration_s": duration, "elapsed_s": elapsed}

    job_id = await job_manager.submit(request)
    job = job_manager.get(job_id)
    return {
        "job_id": job_id, "status": "queued",
        "position": job_manager.get_position(job),
        "queue_length": job_manager.get_queue_status()["queue_length"],
        "estimated_wait_s": round(job_manager.get_position(job) * job_manager._avg_elapsed),
    }


@app.get("/v1/jobs/{job_id}")
async def get_job(job_id: str):
    job = job_manager.get(job_id)
    if not job: raise HTTPException(404, f"作业不存在：{job_id}")
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
    if job.status == "failed": resp["error"] = job.error
    return resp


@app.get("/v1/jobs")
async def list_jobs(status: str = Query("active"), limit: int = Query(20, le=100)):
    all_jobs = sorted(job_manager.jobs.values(), key=lambda j: j.created_at, reverse=True)
    filtered = [j for j in all_jobs if status == "all" or j.status not in ("completed", "failed", "cancelled")]
    return {"count": len(filtered[:limit]), "jobs": [_job_summary(j) for j in filtered[:limit]]}


@app.delete("/v1/jobs/{job_id}")
async def cancel_job(job_id: str):
    if not job_manager.cancel(job_id): raise HTTPException(400, "作业不存在或已开始")
    return {"job_id": job_id, "status": "cancelled"}


def _job_summary(j: Job) -> dict:
    d = {"job_id": j.job_id, "status": j.status, "input": j.request.input[:80],
         "elapsed": j.elapsed, "position": job_manager.get_position(j)}
    if j.result: d["duration_s"] = j.result["duration_s"]
    if j.error: d["error"] = j.error
    return d


@app.get("/v1/queue")
async def queue_dashboard(request: Request):
    qs = job_manager.get_queue_status()
    if "application/json" in request.headers.get("accept", ""): return qs
    cur = qs["current_job"]; queued = qs["queued"]
    cur_row = f"""<div class="card processing"><div class="dot"></div><div>
      <strong>🔊 合成中…</strong> <span class="mono">{cur.get('job_id','')}</span>
      <p>"{cur.get('input','')}"</p><p class="meta">⏱ {cur.get('elapsed',0)}s</p></div></div>""" if cur else '<div class="card idle">😴 空闲</div>'
    q_rows = "".join(f"""<div class="card queued"><span class="pos">#{q['position']}</span><div>
      <span class="mono">{q['job_id']}</span><p>"{q['input']}"</p>
      <p class="meta">⏳ ~{q['estimated_wait_s']}s</p></div></div>""" for q in queued) if queued else '<div class="card empty">✅ 队列为空</div>'
    return HTMLResponse(f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta http-equiv="refresh" content="3">
<title>TTS 队列</title><style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:"Segoe UI","Noto Sans SC",sans-serif;background:#0f1923;color:#e0e0e0;min-height:100vh;padding:24px}}.container{{max-width:750px;margin:0 auto}}
h1{{font-size:22px;color:#5dade2;margin-bottom:4px}}.sub{{font-size:13px;color:#6b7b8b;margin-bottom:20px}}.stats{{display:flex;gap:16px;margin-bottom:20px}}.stat{{flex:1;background:#162433;border:1px solid #243544;border-radius:8px;padding:16px;text-align:center}}
.stat .v{{font-size:28px;color:#5dade2}}.stat .l{{font-size:11px;color:#6b7b8b;margin-top:4px}}
.card{{background:#162433;border:1px solid #243544;border-radius:8px;padding:16px;margin-bottom:10px;display:flex;align-items:center;gap:14px}}
.card.processing{{border-color:#5dade2;animation:glow 2s infinite alternate}}@keyframes glow{{0%{{box-shadow:0 0 8px rgba(93,173,226,0.1)}}100%{{box-shadow:0 0 20px rgba(93,173,226,0.25)}}}}
.card.idle{{color:#6b7b8b;justify-content:center}}.card.empty{{color:#4a9b5a;justify-content:center}}
.dot{{width:14px;height:14px;border-radius:50%;background:#5dade2;flex-shrink:0;animation:pulse 1.2s infinite}}@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.pos{{background:#5dade2;color:#0f1923;font-weight:bold;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.mono{{font-family:Consolas,monospace;font-size:11px;color:#8899aa}}.meta{{font-size:11px;color:#6b7b8b;margin-top:4px}}</style></head><body><div class="container">
<h1>🎙️ Higgs Audio v3 TTS 队列</h1><p class="sub">3s 刷新 | 纯 transformers 推理</p>
<div class="stats"><div class="stat"><div class="v">{qs['total_completed']}</div><div class="l">已完成</div></div>
<div class="stat"><div class="v">{qs['queue_length']}</div><div class="l">排队中</div></div>
<div class="stat"><div class="v">{qs['avg_elapsed']}s</div><div class="l">平均耗时</div></div></div>
<h3 style="font-size:14px;color:#8899aa;margin-bottom:10px;">当前作业</h3>{cur_row}
<h3 style="font-size:14px;color:#8899aa;margin-bottom:10px;">排队</h3>{q_rows}</div></body></html>""")


# ═════════════════════════════════════════════════════════
# 入口
# ═════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser(description="Higgs Audio v3 TTS 服务（纯 transformers）")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--model-path", default="./models/higgs-audio-v3-tts-4b")
    args = parser.parse_args()

    os.environ["HIGGS_MODEL_PATH"] = args.model_path
    log.info(f"启动：http://{args.host}:{args.port}")

    uvicorn.run("server:app", host=args.host, port=args.port, timeout_keep_alive=120)
