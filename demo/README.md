# Demo：AI 绘本生成器 — 推理服务

这是第一天下午 **Agentic AI 进阶** 教程的配套推理服务。

## 快速导航

| 目录 | 内容 | 端口 |
|------|------|------|
| `flux-inference-service/` | FLUX.2-klein-9B 文生图 API | `:5500` |
| `higgs-tts-service/` | Higgs Audio v3 TTS API | `:8100` |

## 架构

```
教师电脑                      L20 服务器
┌──────────────┐   HTTP     ┌─────────────────────┐
│ Skill/Agent   │←─────────→│ :5500 FLUX 文生图    │
│ 绘本生成器    │            │ :8100 Higgs TTS      │
│              │            └─────────────────────┘
│ picturebook  │
│ .html        │
└──────────────┘
```

## 启动所有服务

> 环境配置详见 [ENV_SETUP.md](ENV_SETUP.md) — FLUX 和 TTS 各用独立环境
> 模型权重已预置在服务器上，无需额外下载

```bash
# 一键安装两个环境
./install.sh

# 终端1：FLUX 文生图（:5500）
cd flux-inference-service && source ../flux-env/bin/activate
tmux new -s flux
python server.py --model-path ./models/FLUX.2-klein-9B --host 0.0.0.0 --port 5500

# 终端2：Higgs TTS（:8100）
cd higgs-tts-service && source ../tts-env/bin/activate
tmux new -s tts
python server.py --model-path ./models/higgs-audio-v3-tts-4b --host 0.0.0.0 --port 8100
```

## 完整调用链路（教师 Vibe Coding）

```
1. DeepSeek API   → 生成绘本文案（Agent 自动规划）
2. FLUX API :5500 → 生成每页插图（文生图/图生图）
3. Higgs API :8100 → 生成每页语音旁白（可克隆教师声音）
4. 组装 HTML     → 翻页绘本网页
```

## 教程环节对应

| 时间 | 环节 | 如何使用此 Demo |
|------|------|---------------|
| 14:55 | Skill Part1 | "绘本生成器是一个 Skill 的输出" |
| 15:15 | Skill Part2 | 教师调用 DeepSeek → FLUX → TTS 完整链路 |
| 16:20 | MCP 实践 | `mcp.json` → flux-image + higgs-tts |
| 16:50 | 总结 | 五层架构：模型→工具→Skill→Harness→人 |
