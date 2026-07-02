# ============================================================
# FLUX.2-klein-9B 推理服务 Docker 镜像
# ============================================================
# 构建：docker build -t flux-klein9b-server .
# 运行：docker run --gpus all -p 5500:5500 flux-klein9b-server
#
# 注意：
# 1. 模型权重通过 volume 挂载（不在镜像内）
# 2. 需要 nvidia-container-toolkit
# 3. 国内构建时可设置 HuggingFace 镜像：
#    docker build --build-arg HF_ENDPOINT=https://hf-mirror.com .

FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

LABEL maintainer="WHMC AI Workshop"
LABEL description="FLUX.2-klein-9B 推理服务"

# 系统依赖（Ubuntu 22.04 自带 Python 3.10）
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3 1
RUN update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# 工作目录
WORKDIR /app

# Python 依赖
COPY requirements.txt .
ARG HF_ENDPOINT=""
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir git+https://github.com/huggingface/diffusers.git

# 复制服务代码
COPY server.py .

# HuggingFace 缓存目录 + 模型存储（挂载外部 volume）
VOLUME ["/data/huggingface", "/data/models", "/data/flux-images"]

ENV HF_HOME=/data/huggingface
ENV MODELSCOPE_CACHE=/data/models
ENV FLUX_CPU_OFFLOAD=false
ENV FLUX_MAX_CONCURRENT=1

EXPOSE 5500

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -f http://localhost:5500/health || exit 1

# 默认从 ModelScope 下载模型启动（国内友好）
# 如果已有本地模型，设置 FLUX_MODEL_PATH 环境变量
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "5500"]
