"""
FLUX.2-klein-9B 推理服务 — FastAPI 版本
==========================================
OpenAI 兼容 /v1/images/generations 端点
适配 L20 × 2 服务器，单卡 BF16 全精度推理

模型来源：
  🅰️ ModelScope（推荐国内）: modelscope download black-forest-labs/FLUX.2-klein-9B
  🅱️ HuggingFace 镜像: HF_ENDPOINT=https://hf-mirror.com
  🅲️ 本地路径: --model-path /data/models/FLUX.2-klein-9B

启动：
  python server.py --host 0.0.0.0 --port 5500
  python server.py --model-source modelscope --host 0.0.0.0 --port 5500
文档：http://<ip>:5500/docs
"""

import io
import os
import sys
import time
import json
import uuid
import base64
import logging
import argparse
import asyncio
from pathlib import Path
from typing import Optional, List, Literal
from contextlib import asynccontextmanager
from datetime import datetime

import torch
from PIL import Image
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# ── 日志配置 ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("flux-server")

# ── 模型全局变量 ─────────────────────────────────────────
pipe = None
model_info = {
    "model_id": "black-forest-labs/FLUX.2-klein-9B",
    "device": "cuda",
    "dtype": "bfloat16",
    "max_resolution": (2048, 2048),
    "default_resolution": (1024, 1024),
    "num_inference_steps": 4,
    "guidance_scale": 1.0,  # 蒸馏模型固定 1.0
}

# ── 并发控制 ─────────────────────────────────────────────
# L20 48GB 显存只能串行推理，设为 1；双卡可设为 2
GPU_SEMAPHORE = asyncio.Semaphore(int(os.environ.get("FLUX_MAX_CONCURRENT", "1")))

# ── API Key 鉴权（可选）───────────────────────────────────
API_KEY = os.environ.get("FLUX_API_KEY", "")
security = HTTPBearer(auto_error=False)


# ═══════════════════════════════════════════════════════════
# 模型下载工具
# ═══════════════════════════════════════════════════════════

def download_from_modelscope(model_id: str, cache_dir: str) -> str:
    """从 ModelScope 下载模型，返回本地路径"""
    try:
        from modelscope import snapshot_download
    except ImportError:
        log.error("❌ 请先安装 modelscope：pip install modelscope")
        raise

    log.info(f"📥 从 ModelScope 下载模型：{model_id} → {cache_dir}")
    local_path = snapshot_download(
        model_id,
        cache_dir=cache_dir,
        revision="master",
    )
    log.info(f"✅ 模型已下载到：{local_path}")
    return local_path


def resolve_model_path(
    model_id: str,
    model_source: str = "huggingface",
    local_path: Optional[str] = None,
) -> str:
    """
    根据来源解析模型路径：
    - modelscope: 从 ModelScope 下载到 ./models/ 目录
    - huggingface: 返回 HF model_id（可通过 HF_ENDPOINT 镜像加速）
    - local: 直接返回本地路径
    """
    if model_source == "local":
        if not local_path or not Path(local_path).exists():
            raise FileNotFoundError(f"本地模型路径不存在：{local_path}")
        log.info(f"📁 使用本地模型：{local_path}")
        return local_path

    elif model_source == "modelscope":
        cache_dir = os.environ.get("MODELSCOPE_CACHE", "./models")
        os.makedirs(cache_dir, exist_ok=True)
        return download_from_modelscope(model_id, cache_dir)

    else:  # huggingface
        # 检查是否设置了镜像
        hf_endpoint = os.environ.get("HF_ENDPOINT", "")
        if hf_endpoint:
            log.info(f"🌐 HuggingFace 镜像：{hf_endpoint}")
        else:
            log.info("🌐 使用 HuggingFace 官方源（国内可设置 HF_ENDPOINT=https://hf-mirror.com）")
        return model_id


# ═══════════════════════════════════════════════════════════
# 模型加载
# ═══════════════════════════════════════════════════════════

def load_pipeline_cls():
    """加载 Flux2KleinPipeline，兼容不同 diffusers 版本"""
    try:
        from diffusers import Flux2KleinPipeline
        return Flux2KleinPipeline
    except ImportError:
        pass
    try:
        from diffusers import FluxPipeline
        log.warning("⚠️ Flux2KleinPipeline 不可用，降级为 FluxPipeline")
        return FluxPipeline
    except ImportError:
        pass
    raise ImportError(
        "无法导入 FLUX Pipeline。请升级 diffusers：\n"
        "  pip install -U diffusers\n"
        "  # 或从 GitHub 安装最新版：\n"
        "  pip install git+https://github.com/huggingface/diffusers.git"
    )


def load_model(model_path: str, device: str = "cuda", cpu_offload: bool = False):
    """加载 FLUX.2-klein-9B 模型"""
    global pipe
    log.info(f"正在加载模型：{model_path}（device={device}, cpu_offload={cpu_offload}）…")

    try:
        Pipeline = load_pipeline_cls()
        dtype = torch.bfloat16 if device == "cuda" else torch.float32

        pipe = Pipeline.from_pretrained(
            model_path,
            torch_dtype=dtype,
        )

        if cpu_offload:
            pipe.enable_model_cpu_offload()
            log.info("已启用 CPU Offload（显存优化）")
        else:
            pipe = pipe.to(device)
            log.info(f"模型已移至 {device}")

        log.info("✅ 模型加载完成")
        return True

    except Exception as e:
        log.error(f"❌ 模型加载失败：{e}")
        return False


# ═══════════════════════════════════════════════════════════
# 鉴定中间件
# ═══════════════════════════════════════════════════════════

def verify_api_key(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """可选的 API Key 鉴权"""
    if not API_KEY:
        return  # 未设置 API Key，跳过鉴定
    if credentials is None:
        raise HTTPException(status_code=401, detail="缺少 API Key（Authorization: Bearer <key>）")
    if credentials.credentials != API_KEY:
        raise HTTPException(status_code=403, detail="API Key 无效")
    return credentials


# ═══════════════════════════════════════════════════════════
# Pydantic 模型（OpenAI 兼容）
# ═══════════════════════════════════════════════════════════

class ImageGenerationRequest(BaseModel):
    """OpenAI Images API 请求格式"""
    model: str = Field(default="black-forest-labs/FLUX.2-klein-9B")
    prompt: str = Field(..., min_length=1, max_length=4000)
    n: int = Field(default=1, ge=1, le=4)
    size: str = Field(default="1024x1024")
    response_format: Literal["url", "b64_json"] = Field(default="b64_json")
    user: Optional[str] = None
    # 扩展参数
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


class ErrorResponse(BaseModel):
    error: dict


# ═══════════════════════════════════════════════════════════
# 生成逻辑
# ═══════════════════════════════════════════════════════════

def parse_size(size_str: str) -> tuple[int, int]:
    """解析 '1024x1024' 为 (1024, 1024)"""
    try:
        w, h = size_str.lower().split("x")
        width, height = int(w), int(h)
        max_w, max_h = model_info["max_resolution"]
        width = min(width, max_w)
        height = min(height, max_h)
        # 对齐到 64
        width = (width // 64) * 64
        height = (height // 64) * 64
        return max(256, width), max(256, height)
    except Exception:
        return model_info["default_resolution"]


def get_generator(device: str, seed: int):
    """创建 torch.Generator，兼容 CPU/CUDA"""
    if device == "cuda" and torch.cuda.is_available():
        return torch.Generator(device="cuda").manual_seed(seed)
    else:
        return torch.Generator(device="cpu").manual_seed(seed)


async def generate_image(request: ImageGenerationRequest) -> tuple[Image.Image, int]:
    """异步生成单张图片（带并发控制）"""
    global pipe

    if pipe is None:
        raise RuntimeError("模型未加载")

    width, height = parse_size(request.size)
    steps = request.num_inference_steps or model_info["num_inference_steps"]
    guidance = request.guidance_scale or model_info["guidance_scale"]
    device = model_info["device"]

    if request.seed is not None:
        seed = request.seed
    else:
        seed = int(torch.randint(0, 2**31, (1,)).item())

    log.info(
        f"🎨 生成：prompt='{request.prompt[:80]}...' "
        f"size={width}x{height} steps={steps} seed={seed}"
    )

    def _run():
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
        return result.images[0], seed

    # 并发控制：防止多个请求同时推理导致 OOM
    async with GPU_SEMAPHORE:
        loop = asyncio.get_event_loop()
        image, used_seed = await loop.run_in_executor(None, _run)

    return image, used_seed


# ═══════════════════════════════════════════════════════════
# FastAPI 应用
# ═══════════════════════════════════════════════════════════

start_time = time.time()
_resolved_model_source = "huggingface"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载模型"""
    global _resolved_model_source
    log.info("=" * 60)
    log.info("🚀 FLUX.2-klein-9B 推理服务启动中…")
    log.info(f"   Model: {model_info['model_id']}")
    log.info(f"   Device: {model_info['device']}")
    log.info(f"   Precision: {model_info['dtype']}")
    log.info(f"   Source: {_resolved_model_source}")
    log.info("=" * 60)

    model_path = os.environ.get("FLUX_MODEL_PATH", model_info["model_id"])

    # 如果设置了 ModelScope 源，先下载
    if _resolved_model_source == "modelscope":
        try:
            model_path = resolve_model_path(
                model_info["model_id"],
                model_source="modelscope",
            )
        except Exception as e:
            log.error(f"ModelScope 下载失败：{e}，降级到 HuggingFace")
            model_path = resolve_model_path(model_info["model_id"], model_source="huggingface")
            _resolved_model_source = "huggingface"
    elif _resolved_model_source == "huggingface":
        model_path = resolve_model_path(model_info["model_id"], model_source="huggingface")

    success = load_model(
        model_path,
        device=model_info["device"],
        cpu_offload=os.environ.get("FLUX_CPU_OFFLOAD", "").lower() == "true",
    )
    if not success:
        log.error("模型加载失败，服务将以降级模式运行")

    yield
    log.info("服务关闭")


app = FastAPI(
    title="FLUX.2-klein-9B Inference API",
    description="OpenAI 兼容文生图服务 — WHMC AI 素养工作坊",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── 中间件：请求日志 ──────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    log.info(
        f"{request.method} {request.url.path} → "
        f"{response.status_code} ({elapsed:.2f}s)"
    )
    return response


# ── 异常处理 ──────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"未处理异常：{exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": str(exc),
                "type": type(exc).__name__,
                "code": 500,
            }
        },
    )


# ═══════════════════════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def root():
    """欢迎页"""
    hf_tip = ""
    if _resolved_model_source == "huggingface" and not os.environ.get("HF_ENDPOINT"):
        hf_tip = """
        <p style="color:#e67e22;background:rgba(230,126,34,0.1);padding:10px;border-radius:6px;">
        ⚠️ 国内用户建议设置镜像：<code>export HF_ENDPOINT=https://hf-mirror.com</code><br>
        或使用 ModelScope 下载：<code>python server.py --model-source modelscope</code>
        </p>"""

    return f"""
    <html>
    <head><title>FLUX.2-klein-9B 推理服务</title></head>
    <body style="font-family:sans-serif;max-width:800px;margin:40px auto;padding:20px;">
      <h1>🎨 FLUX.2-klein-9B 推理服务</h1>
      <p>OpenAI 兼容 | WHMC AI 素养工作坊</p>
      {hf_tip}
      <table border="1" cellpadding="8" style="border-collapse:collapse;">
        <tr><th>端点</th><th>说明</th></tr>
        <tr><td><code>POST /v1/images/generations</code></td><td>文生图（OpenAI 兼容）</td></tr>
        <tr><td><code>GET /v1/models</code></td><td>模型列表</td></tr>
        <tr><td><code>GET /health</code></td><td>健康检查 + GPU 状态</td></tr>
        <tr><td><code>GET /docs</code></td><td>Swagger 交互文档</td></tr>
      </table>
      <p style="margin-top:20px;color:#888;">Model: {model_info['model_id']}<br>Source: {_resolved_model_source}</p>
    </body>
    </html>
    """


@app.get("/health", response_model=HealthResponse)
async def health():
    """健康检查 + GPU 状态"""
    gpu_name = None
    vram_total = None
    vram_free = None

    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        total = torch.cuda.get_device_properties(0).total_mem
        reserved = torch.cuda.memory_reserved(0)
        vram_total = total / (1024**3)
        vram_free = (total - reserved) / (1024**3)

    return HealthResponse(
        status="healthy" if pipe is not None else "degraded",
        model=model_info["model_id"],
        device=model_info["device"],
        gpu_name=gpu_name,
        vram_total_gb=round(vram_total, 1) if vram_total else None,
        vram_free_gb=round(vram_free, 1) if vram_free else None,
        uptime_seconds=round(time.time() - start_time, 1),
        model_source=_resolved_model_source,
    )


@app.get("/v1/models")
async def list_models():
    """模型列表（OpenAI 兼容格式）"""
    return {
        "object": "list",
        "data": [
            {
                "id": model_info["model_id"],
                "object": "model",
                "created": 1700000000,
                "owned_by": "black-forest-labs",
            }
        ],
    }


@app.post("/v1/images/generations", response_model=ImageGenerationResponse)
async def create_image(
    request: ImageGenerationRequest,
    auth: Optional[HTTPAuthorizationCredentials] = Depends(verify_api_key),
):
    """
    文生图端点（OpenAI 兼容）
    ---
    用法和 OpenAI Images API 完全一致：
    ```python
    from openai import OpenAI
    client = OpenAI(base_url="http://<ip>:5500/v1", api_key="x")
    client.images.generate(model="...", prompt="...")
    ```
    """
    if pipe is None:
        raise HTTPException(
            status_code=503,
            detail="模型未加载，请检查服务日志。提示：首次启动需下载 ~18GB 模型文件。",
        )

    n = max(1, min(request.n, 4))

    try:
        results = []
        for i in range(n):
            image, seed = await generate_image(request)

            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

            data = ImageData(
                b64_json=img_b64 if request.response_format == "b64_json" else None,
                url=None,
                revised_prompt=request.prompt,
            )
            results.append(data)

        return ImageGenerationResponse(
            created=int(time.time()),
            data=results,
        )

    except RuntimeError as e:
        log.error(f"生成失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/images/generations/batch")
async def create_images_batch(
    requests: List[ImageGenerationRequest],
    auth: Optional[HTTPAuthorizationCredentials] = Depends(verify_api_key),
):
    """
    批量生成（顺序执行，避免 OOM）
    ---
    一次请求生成多组图片。
    """
    if pipe is None:
        raise HTTPException(status_code=503, detail="模型未加载")

    results = []
    for req in requests:
        try:
            image, seed = await generate_image(req)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            results.append({
                "prompt": req.prompt,
                "seed": seed,
                "b64_json": base64.b64encode(buffer.getvalue()).decode("utf-8"),
            })
        except Exception as e:
            results.append({"prompt": req.prompt, "error": str(e)})

    return {"created": int(time.time()), "results": results}


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(
        description="FLUX.2-klein-9B 推理服务",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 从 HuggingFace 加载（国内设置 HF_ENDPOINT 镜像）
  export HF_ENDPOINT=https://hf-mirror.com
  python server.py --host 0.0.0.0 --port 5500

  # 从 ModelScope 下载并加载（推荐国内）
  python server.py --model-source modelscope --host 0.0.0.0 --port 5500

  # 从本地路径加载
  python server.py --model-path /data/models/FLUX.2-klein-9B --host 0.0.0.0 --port 5500
        """,
    )
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=5500, help="监听端口")
    parser.add_argument("--model", default="black-forest-labs/FLUX.2-klein-9B", help="模型 ID")
    parser.add_argument("--model-source", default="huggingface",
                        choices=["huggingface", "modelscope", "local"],
                        help="模型来源（默认 huggingface，国内推荐 modelscope）")
    parser.add_argument("--model-path", default=None, help="本地模型路径（--model-source local 时使用）")
    parser.add_argument("--device", default="cuda", help="设备（cuda / cpu）")
    parser.add_argument("--cpu-offload", action="store_true", help="启用 CPU Offload 节省显存")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    # 更新全局配置
    model_info["model_id"] = args.model
    model_info["device"] = args.device
    _resolved_model_source = args.model_source

    if args.cpu_offload:
        os.environ["FLUX_CPU_OFFLOAD"] = "true"

    if args.model_path:
        os.environ["FLUX_MODEL_PATH"] = args.model_path

    log.info(f"启动服务：http://{args.host}:{args.port}")
    log.info(f"API 文档：http://{args.host}:{args.port}/docs")
    log.info(f"模型来源：{args.model_source}")

    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        timeout_keep_alive=120,
    )
