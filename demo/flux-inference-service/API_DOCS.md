# FLUX 文生图 API 接口文档

> **服务地址**：`http://10.100.35.254:5500`
> **队列看板**：http://10.100.35.254:5500/v1/queue
> **Swagger 文档**：http://10.100.35.254:5500/docs

---

## ⚠️ 重要须知（请先阅读）

### 服务器不存储图片

| 项目 | 说明 |
|------|------|
| 📦 **图片存储** | **服务器端不存盘**。图片仅在内存中保留 **30 分钟**，超时自动清理 |
| 🔄 **服务重启** | 所有未取走的图片**立即丢失** |
| 💾 **客户端责任** | **你必须自行保存**。拿到 `b64_json` 后解码写入本地文件 |
| 📂 **参考图** | 仅用于图生图推理，服务器不保存你上传的参考图 |

### 队列特性

| 项目 | 说明 |
|------|------|
| 🔢 **队列上限** | **无硬限制**，动态扩张。100 个作业同时排队也没问题 |
| 🚶 **排队策略** | FIFO 先进先出，后来的排后面 |
| ⏱️ **预估等待** | `estimated_wait_seconds` = 前面作业数 × 平均耗时（~9秒/张） |
| ❌ **取消机制** | 排队中可取消（`DELETE /v1/jobs/{job_id}`），已开始的无法取消 |
| 📊 **实时看板** | http://10.100.35.254:5500/v1/queue 查看当前队列 |

### 典型流程

```
提交作业 → 拿到 job_id → 轮询 → status=completed → 解码 base64 → 自己写盘保存
   ↓                                                      ↑
  立即返回                                            图片不存服务器
```

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

tmux new -s flux
python server.py --model-path ./models/FLUX.2-klein-9B --host 0.0.0.0 --port 5500
# 看到 "✅ 模型加载完成" → Ctrl+B 再按 D 断开
```

### 1.3 日常运维

```bash
tmux attach -s flux       # 查看日志，Ctrl+C 停服务后重新 python server.py ... 启动
sudo ufw allow 5500        # 放行端口（首次需要）

# 更新代码
cd ~/WHMC_AITraining && git pull origin main
# tmux 里 Ctrl+C → 重启服务
```

---

## 二、接口列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 + GPU 状态 |
| `/v1/models` | GET | 模型列表 |
| `/v1/images/generations` | POST | **核心接口**：文生图 / 图生图 / 多参考图 |
| `/v1/jobs/{job_id}` | GET | 查询作业结果 |
| `/v1/jobs` | GET | 作业列表 |
| `/v1/jobs/{job_id}` | DELETE | 取消排队中的作业 |
| `/v1/queue` | GET | 可视化队列看板（HTML / JSON） |

---

## 三、核心接口：`POST /v1/images/generations`

一个接口，**三种模式**，根据参数自动切换：

| 模式 | 传参 | 用途 |
|------|------|------|
| 📝 **文生图** | 只传 `prompt` | 文字 → 图片 |
| 🎨 **图生图编辑** | `prompt` + `image` | 文字指令修改单张图片 |
| 🧩 **多参考图合成** | `prompt` + `images[]` | 4 张图合成一张 |

---

### 3.1 📝 文生图（Text-to-Image）

**请求**

```
POST /v1/images/generations
Content-Type: application/json
```

```json
{
  "prompt": "一只橘猫坐在窗台上看月亮，绘本插画风格，温暖色调",
  "size": "1024x1024",
  "seed": 42
}
```

**参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `prompt` | string | ✅ | — | 图片描述，中英文均可，最长 4000 字 |
| `size` | string | ❌ | `1024x1024` | `512x512` / `1024x1024` / `2048x2048` |
| `seed` | int | ❌ | 随机 | 同 seed 同 prompt 出同图 |
| `n` | int | ❌ | `1` | 生成数量（1-4） |
| `num_inference_steps` | int | ❌ | `4` | 推理步数（蒸馏模型 4 步足够） |
| `guidance_scale` | float | ❌ | `1.0` | 蒸馏模型固定 1.0 |

**响应（异步模式，默认）**

```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "queued",
  "position": 0,
  "queue_length": 1,
  "estimated_wait_seconds": 0
}
```

---

### 3.2 🎨 图生图编辑（Image-to-Image Editing）

传入一张参考图 + 编辑指令，模型根据指令修改图片。

**请求**

```json
{
  "prompt": "把猫变成一只金色的狗，保持相同的姿势和背景",
  "image": "iVBORw0KGgo...",
  "size": "1024x1024"
}
```

`image` 支持三种格式：
- **纯 Base64**：`"iVBORw0KGgoAAAANSUhEUg..."`
- **Data URL**：`"data:image/png;base64,iVBORw0KGgo..."`
- **HTTP URL**：`"https://example.com/cat.png"`

**prompt 写法（图生图模式）**

> 用自然语言直接描述编辑需求，像对人说话一样。FLUX.2 对叙事性 prompt 响应最好。
>
> ✅ 好："把背景换成夜晚的星空，猫咪保持不动"
> ✅ 好："把这只猫变成一只老虎，保持相同的姿势"
> ❌ 差："cat → dog"（太简略）

**完整示例**

```json
{
  "prompt": "Add a wizard hat on the cat, change the background to a magical library with floating books",
  "image": "https://example.com/cat.jpg",
  "size": "1024x1024",
  "seed": 42
}
```

---

### 3.3 🧩 多参考图合成（Multi-Reference）

最多 4 张参考图，按自然语言指令合成。

**请求**

```json
{
  "prompt": "The person from image 1 sitting at the cafe table from image 2, with the lighting style of image 3",
  "images": [
    "iVBORw0KGgo...（人物照片）",
    "https://example.com/cafe.jpg",
    "data:image/png;base64,iVBORw0KGgo...（风格参考）"
  ],
  "size": "1024x1024"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `images` | string[] | ✅ | 参考图数组，最多 4 张，每张支持 base64 / data URL / HTTP URL |

**prompt 写法（多参考图模式）**

通过序号引用图片：`image 1`、`image 2` 对应数组索引。

```
✅ "把图1中的人放到图2的咖啡馆场景里，保持图3的暖色调光影"
✅ "Replace the background of image 1 with the landscape from image 2"
✅ "Combine the face from image 1 with the hairstyle from image 2"
```

---

## 四、查询作业

```
GET /v1/jobs/{job_id}
```

**响应（已完成）**

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
    "size": "1024x1024",
    "mode": "T2I"
  }
}
```

| 字段 | 说明 |
|------|------|
| `result.b64_json` | Base64 编码的 PNG 图片 |
| `result.mode` | 生成模式：`T2I` / `I2I` / `Multi-Ref` |
| `result.seed` | 随机种子 |
| `result.elapsed` | 推理耗时（秒） |

---

## 五、其他接口

### 健康检查

```
GET /health
```

```json
{
  "status": "healthy",
  "gpu_name": "NVIDIA L20",
  "vram_total_gb": 48.0,
  "vram_free_gb": 30.5,
  "queue_length": 3,
  "total_completed": 42
}
```

### 队列看板

```
GET /v1/queue               → HTML 可视化（浏览器打开）
GET /v1/queue  Accept: application/json → JSON
```

### 作业列表

```
GET /v1/jobs?status=active   # 进行中
GET /v1/jobs?status=all      # 全部
```

### 取消作业

```
DELETE /v1/jobs/{job_id}
```

> 只有 `queued` 状态可取消。

---

## 六、客户端调用

### 6.1 Python — 文生图

```python
import time, base64, requests

BASE = "http://10.100.35.254:5500"

# 提交
resp = requests.post(f"{BASE}/v1/images/generations", json={
    "prompt": "春天的花园里，孩子们在草地上读书，绘本插画风格",
    "size": "1024x1024"
})
job = resp.json()

# 轮询
while True:
    r = requests.get(f"{BASE}/v1/jobs/{job['job_id']}").json()
    if r["status"] == "completed":
        img = base64.b64decode(r["result"]["b64_json"])
        with open("output.png", "wb") as f: f.write(img)
        print(f"✅ {r['result']['elapsed']}s  mode={r['result']['mode']}")
        break
    elif r["status"] == "failed":
        print(f"❌ {r['error']}"); break
    time.sleep(3)
```

### 6.2 Python — 图生图编辑

```python
import base64, requests

BASE = "http://10.100.35.254:5500"

# 把本地图片编码为 base64
with open("cat.jpg", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

# 提交编辑任务
resp = requests.post(f"{BASE}/v1/images/generations", json={
    "prompt": "Add a wizard hat on the cat, magical background",
    "image": img_b64,
    "size": "1024x1024"
})
print(resp.json())
# → {"job_id": "...", "status": "queued", "position": 0}
```

### 6.3 Python — 多参考图合成

```python
resp = requests.post(f"{BASE}/v1/images/generations", json={
    "prompt": "Person from image 1 sitting at the cafe from image 2",
    "images": [
        base64.b64encode(open("person.jpg","rb").read()).decode(),
        "https://example.com/cafe.jpg",
    ],
    "size": "1024x1024"
})
```

### 6.4 curl — 文生图

```bash
# 提交
JOB_ID=$(curl -s -X POST http://10.100.35.254:5500/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{"prompt":"水墨画风格月亮","size":"512x512"}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['job_id'])")

# 轮询 + 保存
while true; do
  STATUS=$(curl -s http://10.100.35.254:5500/v1/jobs/$JOB_ID \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['status'])")
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 2
done
curl -s http://10.100.35.254:5500/v1/jobs/$JOB_ID | python3 -c "
import json,base64,sys
d=json.load(sys.stdin)['result']
open('output.png','wb').write(base64.b64decode(d['b64_json']))
print(f'✅ {d[\"size\"]} {d[\"elapsed\"]}s mode={d[\"mode\"]}')
"
```

### 6.5 JavaScript（浏览器）

```javascript
const BASE = "http://10.100.35.254:5500";

async function generate(prompt, imageBase64 = null) {
  const body = { prompt, size: "1024x1024" };
  if (imageBase64) body.image = imageBase64;  // 图生图模式

  const { job_id } = await fetch(`${BASE}/v1/images/generations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(r => r.json());

  while (true) {
    const job = await fetch(`${BASE}/v1/jobs/${job_id}`).then(r => r.json());
    if (job.status === "completed") {
      const img = document.createElement("img");
      img.src = `data:image/png;base64,${job.result.b64_json}`;
      document.body.appendChild(img);
      return;
    }
    if (job.status === "failed") { console.error(job.error); return; }
    await new Promise(r => setTimeout(r, 3000));
  }
}

// 文生图
generate("一只橘猫看月亮");

// 图生图（需要先读取文件获取 base64）
// generate("给猫戴上巫师帽", "iVBORw0KGgo...");
```

---

## 七、状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 参数错误（prompt 为空、images 超过 4 张等） |
| 404 | 作业不存在 |
| 429 | GPU 正忙（同步模式） |
| 500 | 服务端错误 |
| 503 | 模型未加载 |

---

## 八、推荐工作流

```
1. 浏览器看板    http://10.100.35.254:5500/v1/queue    确认在线
2. 提交作业      POST /v1/images/generations           拿到 job_id
3. 每 3 秒轮询   GET  /v1/jobs/{job_id}
4. status=completed → 解码 base64 → 保存/展示
```

## 九、技术参考

- 模型：`black-forest-labs/FLUX.2-klein-9B`（9B 流模型 + Qwen3 8B 文本编码器）
- 推理步数：4 步蒸馏（Step-Distilled）
- 默认分辨率：1024×1024，最高 2048×2048
- 精度：BF16（~18GB 显存）
- Pipeline：`Flux2KleinPipeline`（HuggingFace Diffusers）
- ModelScope 模型页：`https://modelscope.cn/collections/black-forest-labs/FLUX-2-Klein`

---

## 十、附赠测试脚本

| 脚本 | 用途 | 用法 |
|------|------|------|
| `lan_test.py` | 快速连通测试 | `python lan_test.py --url http://10.100.35.254:5500` |
| `multi_client_test.py` | N个独立教师模拟 | `python multi_client_test.py --clients 15` |
| `dynamic_queue_test.py` | 动态队列压测 | `python dynamic_queue_test.py --teachers 30 --duration 180` |
| `stress_test.py` | 高强度并发 | `python stress_test.py --jobs 50` |

所有脚本均保存生成的图片到本地（`output/` 或 `output_dynamic/`），服务器端不会存图。
