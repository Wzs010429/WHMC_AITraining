# FLUX.2-klein-9B 推理服务 — Linux 部署指南

面向 WHMC 工作坊的 OpenAI 兼容文生图 API，教师用 Vibe Coding 直接调用。

## 模型信息

| 属性 | 说明 |
|------|------|
| 模型 | `black-forest-labs/FLUX.2-klein-9B`（Black Forest Labs） |
| 参数量 | 9B（Rectified Flow Transformer）+ Qwen3 8B 文本编码器 |
| 推理步数 | **仅 4 步**（Step-Distilled，~9秒/张） |
| 默认分辨率 | 1024×1024（最高 2048×2048） |
| 精度 | BF16（~18GB 显存） |
| 模型下载 | ModelScope / HuggingFace 镜像 |
| API 协议 | OpenAI 兼容 `/v1/images/generations` |
| 许可 | 非商业用途 |

### 硬件要求

| 配置 | 最低 | 推荐 |
|------|------|------|
| GPU | RTX 3090（24GB） | **L20 48GB** ✅ |
| 显存 | 18GB（BF16 + CPU Offload） | 48GB（BF16 全加载） |
| RAM | 32GB | 64GB |
| 存储 | 100GB | 500GB NVMe |
| 系统 | Ubuntu 20.04+ | Ubuntu 22.04 LTS |
| CUDA | 12.0+ | 12.4+ |
| 驱动 | 535+ | 550+ |

---

## 🚀 快速开始（5 步部署）

### 第 1 步：克隆仓库

```bash
git clone <this-repo-url>
cd demo/flux-inference-service
```

### 第 2 步：创建虚拟环境

```bash
python3 -m venv flux-env
source flux-env/bin/activate
```

### 第 3 步：安装依赖

```bash
# 基础依赖
pip install -r requirements.txt

# 如果 diffusers 版本太旧，从 GitHub 安装最新版
pip install git+https://github.com/huggingface/diffusers.git
```

### 第 4 步：下载模型（三选一）

#### 🅰️ ModelScope（推荐国内）

```bash
# 安装 ModelScope CLI
pip install modelscope

# 下载模型到本地（~18GB，首次需要 10-30 分钟）
modelscope download --model black-forest-labs/FLUX.2-klein-9B --local_dir ./models/FLUX.2-klein-9B
```

#### 🅱️ HuggingFace 镜像（备选）

```bash
# 设置国内镜像
export HF_ENDPOINT=https://hf-mirror.com

# huggingface-cli 下载
pip install huggingface_hub
huggingface-cli download black-forest-labs/FLUX.2-klein-9B --local-dir ./models/FLUX.2-klein-9B
```

#### 🅲️ HuggingFace 官方（海外服务器）

```bash
# 直接让 diffusers 自动下载
# 无需手动操作，启动服务时会自动从 HuggingFace 拉取
```

### 第 5 步：启动服务

```bash
# 使用 ModelScope 下载的本地模型
python server.py \
  --model-path ./models/FLUX.2-klein-9B \
  --host 0.0.0.0 \
  --port 5500

# 或者让服务自动从 ModelScope 下载
python server.py \
  --model-source modelscope \
  --host 0.0.0.0 \
  --port 5500

# 或者使用 HuggingFace 镜像
export HF_ENDPOINT=https://hf-mirror.com
python server.py --host 0.0.0.0 --port 5500
```

看到以下日志表示启动成功：

```
✅ 模型加载完成
INFO:     Uvicorn running on http://0.0.0.0:5500
```

---

## 🧪 验证服务

### 方法一：浏览器

打开 `http://<服务器IP>:5500/docs` → Swagger 交互文档 → 点击 `POST /v1/images/generations` → "Try it out" → 填入 prompt → 执行。

### 方法二：测试脚本

```bash
# 测试本地服务
python test_client.py

# 测试远程服务器
python test_client.py --url http://10.x.x.x:5500

# 跳过图片生成（仅测试健康检查）
python test_client.py --skip-generate
```

### 方法三：curl

```bash
# 健康检查
curl http://localhost:5500/health

# 生成图片（返回 Base64）
curl -X POST http://localhost:5500/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "model": "black-forest-labs/FLUX.2-klein-9B",
    "prompt": "一轮圆月挂在夜空中，诗人站在窗前仰望，中国水墨画风格",
    "size": "1024x1024",
    "response_format": "b64_json"
  }' | python3 -c "
import json, base64, sys
data = json.load(sys.stdin)
img = base64.b64decode(data['data'][0]['b64_json'])
with open('output.png', 'wb') as f:
    f.write(img)
print(f'✅ 已保存 output.png ({len(img)/1024:.0f}KB)')
"
```

---

## 🐍 教师端调用（OpenAI SDK）

```python
from openai import OpenAI

# 和调 ChatGPT 完全一样的写法
client = OpenAI(
    base_url="http://10.x.x.x:5500/v1",  # 服务器 IP
    api_key="not-needed"                   # 内网无需鉴权
)

response = client.images.generate(
    model="black-forest-labs/FLUX.2-klein-9B",
    prompt="春天的花园里，孩子们在草地上读书，绘本插画风格，温暖色调",
    n=1,
    size="1024x1024"
)

print(f"生成完成，Base64 长度：{len(response.data[0].b64_json)}")
```

---

## ⚙️ 配置参数

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | `0.0.0.0` | 监听地址 |
| `--port` | `5500` | 监听端口 |
| `--model` | `black-forest-labs/FLUX.2-klein-9B` | 模型 ID |
| `--model-source` | `huggingface` | `modelscope` / `huggingface` / `local` |
| `--model-path` | — | 本地模型路径 |
| `--device` | `cuda` | 设备（`cuda` / `cpu`） |
| `--cpu-offload` | 关闭 | 启用 CPU Offload 节省显存 |
| `--reload` | 关闭 | 开发模式热重载 |

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HF_ENDPOINT` | — | HuggingFace 镜像（国内设 `https://hf-mirror.com`） |
| `MODELSCOPE_CACHE` | `./models` | ModelScope 缓存目录 |
| `FLUX_CPU_OFFLOAD` | `false` | CPU Offload |
| `FLUX_MAX_CONCURRENT` | `1` | 最大并发推理数 |
| `FLUX_API_KEY` | — | API 鉴权 Key（不设则跳过鉴权） |
| `FLUX_MODEL_PATH` | — | 本地模型路径（覆盖 `--model-path`） |

---

## 🔧 systemd 自启动（生产环境）

```bash
sudo tee /etc/systemd/system/flux-image.service << 'EOF'
[Unit]
Description=FLUX.2-klein-9B Inference Service
After=network.target

[Service]
Type=simple
User=flux
WorkingDirectory=/opt/flux-inference
Environment="HF_ENDPOINT=https://hf-mirror.com"
Environment="FLUX_MAX_CONCURRENT=1"
ExecStart=/opt/flux-inference/flux-env/bin/python server.py \
  --model-path /data/models/FLUX.2-klein-9B \
  --host 0.0.0.0 \
  --port 5500
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now flux-image.service
sudo systemctl status flux-image.service
```

---

## 🐳 Docker 部署

```bash
# 构建镜像
docker build -t flux-klein9b-server .

# 启动（需先下载模型到 ./data/models/）
docker compose up -d

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

---

## ❓ 常见问题

### Q: 启动报 `CUDA Out of Memory`？

```bash
# 开启 CPU Offload
python server.py --model-path ./models/FLUX.2-klein-9B --cpu-offload

# 或限制显存
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128
```

### Q: ModelScope 下载速度慢？

```bash
# 换 HuggingFace 镜像
export HF_ENDPOINT=https://hf-mirror.com
modelscope download --model black-forest-labs/FLUX.2-klein-9B --local_dir ./models/FLUX.2-klein-9B

# 或直接用 huggingface-cli
huggingface-cli download black-forest-labs/FLUX.2-klein-9B --local-dir ./models/FLUX.2-klein-9B
```

### Q: HuggingFace 连接不上？

```bash
# 方案 1：用镜像
export HF_ENDPOINT=https://hf-mirror.com

# 方案 2：用 ModelScope
pip install modelscope
modelscope download --model black-forest-labs/FLUX.2-klein-9B --local_dir ./models/FLUX.2-klein-9B

# 方案 3：手动下载后传到服务器
# 在自己电脑上下载 → scp 到服务器 → 用 --model-path 指定路径
```

### Q: 如何限制访问？

```bash
# 防火墙白名单（只允许教师 IP 段）
sudo ufw allow from 10.0.0.0/8 to any port 5500

# 或设置 API Key
export FLUX_API_KEY=your-secret-key
python server.py ...
# 教师调用时需带：Authorization: Bearer your-secret-key
```

### Q: 生成超时怎么办？

图片生成需要 5-15 秒，客户端设置 `timeout=120`。

---

## 📖 API 端点一览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 欢迎页 |
| `/health` | GET | 健康检查 + GPU 显存状态 |
| `/v1/models` | GET | 模型列表（OpenAI 格式） |
| `/v1/images/generations` | POST | 文生图（OpenAI 兼容） |
| `/v1/images/generations/batch` | POST | 批量生成 |
| `/docs` | GET | Swagger 交互文档 |

---

## 📁 文件结构

```
flux-inference-service/
├── server.py          # FastAPI 推理服务（主程序）
├── test_client.py     # 连通性测试脚本
├── requirements.txt   # Python 依赖
├── Dockerfile         # Docker 镜像
├── docker-compose.yml # Docker Compose
├── .env.example       # 环境变量模板
└── README.md          # 本文件
```
