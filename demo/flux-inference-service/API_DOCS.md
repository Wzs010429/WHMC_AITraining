# FLUX 文生图 API 接口文档

> **服务地址**：`http://10.100.35.254:5500`
> **队列看板**：http://10.100.35.254:5500/v1/queue
> **Swagger 文档**：http://10.100.35.254:5500/docs

---

## 一、服务端部署

### 1.1 首次安装

```bash
cd ~ && git clone https://github.com/Wzs010429/WHMC_AITraining.git
cd WHMC_AITraining/demo/flux-inference-service

python3 -m venv flux-env
source flux-env/bin/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install -U diffusers -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install modelscope -i https://pypi.tuna.tsinghua.edu.cn/simple

# 下载模型（~18GB，首次 10-30 分钟）
modelscope download --model black-forest-labs/FLUX.2-klein-9B --local_dir ./models/FLUX.2-klein-9B
```

### 1.2 启动服务（tmux 后台运行）

```bash
cd ~/WHMC_AITraining/demo/flux-inference-service
source flux-env/bin/activate

# 创建 tmux 会话
tmux new -s flux

# 在 tmux 内启动
python server.py --model-path ./models/FLUX.2-klein-9B --host 0.0.0.0 --port 5500

# 看到 "✅ 模型加载完成" 后 → Ctrl+B 再按 D 断开
```

### 1.3 日常运维

```bash
tmux attach -s flux       # 查看日志
                           # 在 tmux 内 Ctrl+C 可停服务
                           # 停服务后再 python server.py ... 重新启动

tmux ls                   # 列出会话

sudo ufw allow 5500        # 放行端口（首次需要）
```

### 1.4 更新代码

```bash
cd ~/WHMC_AITraining && git pull origin main
# 在 tmux 内 Ctrl+C 停服务，然后 python server.py ... 重新启动
```

---

## 二、接口列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/v1/models` | GET | 模型列表 |
| `/v1/images/generations` | POST | **提交作业**（异步，默认） |
| `/v1/images/generations?sync=true` | POST | 同步生成（GPU 空闲时） |
| `/v1/jobs/{job_id}` | GET | **查询作业结果** |
| `/v1/jobs` | GET | 作业列表 |
| `/v1/jobs/{job_id}` | DELETE | 取消排队中的作业 |
| `/v1/queue` | GET | 队列看板（HTML / JSON） |

所有接口均无需鉴权（内网部署）。

---

## 三、接口详情

### 3.1 健康检查

**请求**

```
GET /health
```

**响应 200**

```json
{
  "status": "healthy",
  "model": "black-forest-labs/FLUX.2-klein-9B",
  "device": "cuda",
  "gpu_name": "NVIDIA L20",
  "vram_total_gb": 48.0,
  "vram_free_gb": 30.5,
  "uptime_seconds": 3600.0,
  "queue_length": 3,
  "current_job": "a1b2c3d4e5f6",
  "total_completed": 42
}
```

---

### 3.2 提交作业（核心接口）

**请求**

```
POST /v1/images/generations
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `prompt` | string | ✅ | — | 图片描述（中文/英文，最长 4000 字） |
| `size` | string | ❌ | `1024x1024` | 图片尺寸：`512x512` / `1024x1024` / `2048x2048` |
| `n` | int | ❌ | `1` | 生成数量（1-4） |
| `seed` | int | ❌ | 随机 | 随机种子（同 seed 同 prompt 出同图） |
| `num_inference_steps` | int | ❌ | `4` | 推理步数（1-50，蒸馏模型 4 步即可） |
| `response_format` | string | ❌ | `b64_json` | 返回格式：`b64_json` |
| `negative_prompt` | string | ❌ | — | 负向提示词 |

**请求示例**

```json
{
  "prompt": "一只橘猫坐在窗台上看月亮，绘本插画风格，温暖色调",
  "size": "1024x1024",
  "n": 1
}
```

**响应 200（异步模式，默认）**

```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "queued",
  "position": 2,
  "queue_length": 3,
  "estimated_wait_seconds": 18,
  "message": "作业已提交。轮询 GET /v1/jobs/a1b2c3d4e5f6 获取结果。"
}
```

| 字段 | 说明 |
|------|------|
| `job_id` | 作业 ID，用于后续轮询 |
| `status` | `queued` = 排队中 |
| `position` | 排队位置（0=正在处理） |
| `estimated_wait_seconds` | 预估等待秒数 |

**响应 200（同步模式 `?sync=true`）**

```json
{
  "created": 1719700000,
  "data": [
    {
      "b64_json": "iVBORw0KGgo...",
      "revised_prompt": "一只橘猫坐在窗台上看月亮..."
    }
  ]
}
```

> 同步模式只在 GPU 空闲时可用。GPU 正忙时返回 429。

---

### 3.3 查询作业

**请求**

```
GET /v1/jobs/{job_id}
```

**响应 200 — 排队中**

```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "queued",
  "prompt": "一只橘猫坐在窗台上看月亮...",
  "position": 2,
  "created_at": 1719700000.0
}
```

**响应 200 — 生成中**

```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "processing",
  "prompt": "一只橘猫坐在窗台上看月亮...",
  "position": 0,
  "started_at": 1719700010.0
}
```

**响应 200 — 已完成**

```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "completed",
  "prompt": "一只橘猫坐在窗台上看月亮...",
  "started_at": 1719700010.0,
  "completed_at": 1719700019.0,
  "elapsed": 9.0,
  "result": {
    "b64_json": "iVBORw0KGgo...",
    "seed": 12345678,
    "elapsed": 9.0,
    "size": "1024x1024"
  }
}
```

| 字段 | 说明 |
|------|------|
| `status` | `queued` → `processing` → `completed` / `failed` |
| `result.b64_json` | **Base64 编码的 PNG 图片** |
| `result.seed` | 生成用的随机种子 |
| `result.elapsed` | 推理耗时（秒） |
| `result.size` | 图片尺寸 |

**响应 200 — 失败**

```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "failed",
  "error": "CUDA out of memory"
}
```

---

### 3.4 队列看板

**JSON 模式**

```
GET /v1/queue
Accept: application/json
```

```json
{
  "queue_length": 3,
  "current_job": {
    "job_id": "a1b2c3d4e5f6",
    "prompt": "一只橘猫坐在窗台上看月亮...",
    "elapsed": 5.2
  },
  "queued": [
    {
      "job_id": "b2c3d4e5f6a1",
      "prompt": "春天的花园...",
      "position": 1,
      "estimated_wait_seconds": 9
    }
  ],
  "avg_generation_seconds": 9.0,
  "total_completed": 42
}
```

**HTML 模式**（浏览器直接打开）

```
GET /v1/queue
```

返回可视化看板，深色主题，每 3 秒自动刷新。

---

### 3.5 作业列表

```
GET /v1/jobs?status=active    # 进行中（默认）
GET /v1/jobs?status=all       # 全部
GET /v1/jobs?limit=10         # 最多返回条数
```

---

### 3.6 取消作业

```
DELETE /v1/jobs/{job_id}
```

**响应 200**

```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "cancelled",
  "message": "作业已取消"
}
```

> 只有 `queued` 状态的作业可以取消。已开始处理的作业无法取消。

---

## 四、客户端调用示例

### 4.1 Python（推荐）

```python
import time
import base64
import requests

BASE = "http://10.100.35.254:5500"

# Step 1: 提交作业
resp = requests.post(f"{BASE}/v1/images/generations", json={
    "prompt": "春天的花园里，孩子们在草地上读书，绘本插画风格",
    "size": "1024x1024"
})
job = resp.json()
print(f"📝 job_id={job['job_id']}  排队位置 #{job['position']}")

# Step 2: 轮询直到完成
while True:
    r = requests.get(f"{BASE}/v1/jobs/{job['job_id']}").json()
    if r["status"] == "completed":
        img_bytes = base64.b64decode(r["result"]["b64_json"])
        with open("output.png", "wb") as f:
            f.write(img_bytes)
        print(f"✅ 完成！{r['result']['elapsed']}s → output.png")
        break
    elif r["status"] == "failed":
        print(f"❌ {r['error']}")
        break
    print(f"⏳ {r['status']}… 位置 #{r.get('position', '?')}")
    time.sleep(3)
```

### 4.2 curl

```bash
# 提交
JOB_ID=$(curl -s -X POST http://10.100.35.254:5500/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{"prompt":"水墨画风格月亮","size":"512x512"}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['job_id'])")

# 轮询
while true; do
  STATUS=$(curl -s http://10.100.35.254:5500/v1/jobs/$JOB_ID \
    | python3 -c "import json,sys;print(json.load(sys.stdin)['status'])")
  echo "状态: $STATUS"
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 2
done

# 保存图片
curl -s http://10.100.35.254:5500/v1/jobs/$JOB_ID | python3 -c "
import json,base64,sys
d=json.load(sys.stdin)
open('output.png','wb').write(base64.b64decode(d['result']['b64_json']))
print('✅ 已保存')
"
```

### 4.3 JavaScript（浏览器）

```javascript
const BASE = "http://10.100.35.254:5500";

async function generateImage(prompt) {
  // 提交
  const res = await fetch(`${BASE}/v1/images/generations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, size: "1024x1024" }),
  });
  const { job_id } = await res.json();
  console.log("job_id:", job_id);

  // 轮询
  while (true) {
    const r = await fetch(`${BASE}/v1/jobs/${job_id}`);
    const job = await r.json();

    if (job.status === "completed") {
      const img = document.createElement("img");
      img.src = `data:image/png;base64,${job.result.b64_json}`;
      document.body.appendChild(img);
      console.log("✅ 完成！");
      return;
    }
    if (job.status === "failed") {
      console.error("❌", job.error);
      return;
    }
    console.log("⏳", job.status, "位置", job.position);
    await new Promise(r => setTimeout(r, 3000));
  }
}

generateImage("一只橘猫看月亮");
```

### 4.4 OpenAI SDK（兼容模式）

```python
from openai import OpenAI

client = OpenAI(base_url="http://10.100.35.254:5500/v1", api_key="x")

response = client.images.generate(
    model="black-forest-labs/FLUX.2-klein-9B",
    prompt="一只橘猫坐在窗台上看月亮",
    size="1024x1024",
    n=1,
)
# 注意：OpenAI SDK 下发的是同步请求，GPU 正忙时会返回 429
```

---

## 五、状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 404 | 作业不存在 |
| 429 | GPU 正忙（同步模式），请改用异步模式 |
| 500 | 服务端错误 |
| 503 | 模型未加载 |

---

## 六、推荐工作流

```
1. 打开看板        http://10.100.35.254:5500/v1/queue  确认服务在线
2. 提交作业        POST /v1/images/generations          拿到 job_id
3. 轮询结果        GET  /v1/jobs/{job_id}              每 3 秒查一次
4. 结果出来        status=completed → 解码 base64 → 保存图片
5. 继续下一个      回到步骤 2
```
