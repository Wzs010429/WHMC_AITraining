# Demo：AI 绘本生成器 — 推理服务

这是第一天下午 **Agentic AI 进阶** 教程的配套推理服务，为演示中的 AI 绘本生成器提供文生图 API。

## 快速导航

| 目录 | 内容 |
|------|------|
| `flux-inference-service/` | FLUX.2-klein-9B 推理服务（OpenAI 兼容 API） |

## 架构

```
教师浏览器                    L20 服务器
┌──────────┐    HTTP API    ┌─────────────────┐
│ picturebook│ ←───────→    │ FLUX 推理服务    │
│ .html      │  /v1/images  │ :5500            │
└──────────┘                │ FLUX.2-klein-9B  │
                            │ BF16 · 4步推理   │
                            └─────────────────┘
```

## 推理服务部署

详见 [`flux-inference-service/README.md`](flux-inference-service/README.md)

```bash
# 在 L20 服务器上
git clone <this-repo>
cd demo/flux-inference-service

# 安装依赖
pip install -r requirements.txt

# 从 ModelScope 下载模型并启动（国内推荐）
python server.py --model-source modelscope --host 0.0.0.0 --port 5500
```

## 教程环节对应

| 时间 | 环节 | 如何使用此 Demo |
|------|------|---------------|
| 14:55 | Skill Part1 | "绘本生成器是一个 Skill 的输出，FLUX API 是它调用的 MCP 工具" |
| 15:15 | Skill Part2 | 教师通过 Skill 调用 DeepSeek → FLUX → TTS 完成完整链路 |
| 16:20 | MCP 实践 | 展示 `mcp.json` → flux-image MCP Server 对应关系 |
| 16:50 | 总结 | 逐层指认五层架构：模型→工具→Skill→Harness→人 |
