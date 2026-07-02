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
| API 协议 | OpenAI 兼容 + 异步任务队列 |
| 许可 | 非商业用途 |

### 任务队列模式（v2）

多教师并发时，服务使用**异步作业队列**：

```
教师提交 → job_id（立即返回）→ 排队 → GPU推理 → 完成 → 教师轮询获取结果
```

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/images/generations` | POST | 提交作业（默认异步） |
| `/v1/images/generations?sync=true` | POST | 同步等待（GPU空闲时可用） |
| `/v1/jobs/{job_id}` | GET | 查询作业状态/结果 |
| `/v1/jobs` | GET | 列出所有作业 |
| `/v1/jobs/{job_id}` | DELETE | 取消排队中的作业 |
| `/v1/queue` | GET | 队列看板（HTML + JSON） |

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

### 方法一：浏览器看板

打开 `http://<服务器IP>:5500/v1/queue` → 可视化队列看板（每 3 秒自动刷新）

### 方法二：测试脚本

```bash
python test_client.py                              # 异步模式（默认）
python test_client.py --url http://10.x.x.x:5500   # 指定服务器
python test_client.py --sync                       # 同步模式
python test_client.py --batch                      # 批量提交测试
```

### 方法三：curl — 异步作业流程

```bash
# 1. 提交作业
JOB=$(curl -s -X POST http://localhost:5500/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{"prompt":"一轮圆月，水墨画风格","size":"512x512"}')
JOB_ID=$(echo $JOB | python3 -c "import json,sys;print(json.load(sys.stdin)['job_id'])")
echo "作业ID: $JOB_ID"

# 2. 轮询结果
while true; do
  STATUS=$(curl -s http://localhost:5500/v1/jobs/$JOB_ID | python3 -c "import json,sys;print(json.load(sys.stdin)['status'])")
  echo "状态: $STATUS"
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then break; fi
  sleep 2
done

# 3. 提取图片
curl -s http://localhost:5500/v1/jobs/$JOB_ID | python3 -c "
import json,base64,sys
data=json.load(sys.stdin)['result']
img=base64.b64decode(data['b64_json'])
open('output.png','wb').write(img)
print(f'✅ {data[\"size\"]} {data[\"elapsed\"]}s')
"

# 4. 查看队列
curl -s -H "Accept: application/json" http://localhost:5500/v1/queue | python3 -m json.tool
```

---

## 👥 多教师并发使用

多个老师同时提交时，服务自动排队：

```
教师A ──→ job_aaa（立即返回）──┐
教师B ──→ job_bbb（立即返回）──┤──→ [队列] ──→ GPU 逐个推理
教师C ──→ job_ccc（立即返回）──┘
```

**关键特性：**
- 提交即返回 `job_id`，不阻塞
- FIFO 先进先出
- 实时查询排队位置 + 预估等待时间
- 可视化看板 `http://<ip>:5500/v1/queue`
- 可取消尚未开始的作业

### Python 异步调用示例

```python
import time, requests

BASE = "http://10.x.x.x:5500"

# 提交作业
resp = requests.post(f"{BASE}/v1/images/generations", json={
    "prompt": "春天的花园，绘本风格",
    "size": "1024x1024"
})
job_id = resp.json()["job_id"]
print(f"📝 {job_id} — 排队位置 {resp.json()['position']}")

# 轮询直到完成
while True:
    r = requests.get(f"{BASE}/v1/jobs/{job_id}").json()
    if r["status"] == "completed":
        # 保存图片
        import base64
        img = base64.b64decode(r["result"]["b64_json"])
        with open("output.png", "wb") as f: f.write(img)
        print(f"✅ 完成！{r['result']['elapsed']}s")
        break
    elif r["status"] == "failed":
        print(f"❌ {r['error']}")
        break
    print(f"⏳ {r['status']}… 位置 #{r.get('position', '?')}")
    time.sleep(3)
```


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
| `/health` | GET | 健康检查 + GPU 显存 + 队列状态 |
| `/v1/models` | GET | 模型列表（OpenAI 格式） |
| `/v1/images/generations` | POST | **提交作业**（异步，默认） |
| `/v1/images/generations?sync=true` | POST | 同步生成（GPU 空闲时） |
| `/v1/images/generations/batch` | POST | 批量提交作业 |
| `/v1/jobs/{job_id}` | GET | **查询作业**（完成后返回图片） |
| `/v1/jobs` | GET | 列出作业（?status=active\|all） |
| `/v1/jobs/{job_id}` | DELETE | 取消排队中的作业 |
| `/v1/queue` | GET | **队列看板**（HTML / JSON） |
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
