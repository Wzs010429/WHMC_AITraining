# MCP 排错速查表

| 症状 | 排查方法 |
|------|---------|
| [API] flux-image 报错 | 检查 L20 服务器 IP 是否可达：`curl http://10.x.x.x:5500/health` |
| [API] higgs-tts 报错 | 检查本地 TTS 服务：`curl http://localhost:8080/health` |
| MCP 配置不生效 | 确认已重启 Claude Code；确认 JSON 格式正确（无多余逗号） |
| 图片/音频未保存 | 检查 IMAGE_OUTPUT_DIR / TTS_OUTPUT_DIR 目录是否存在 |
| TTS 生成太慢 | 降低量化等级（BF16 → INT8）；确认 GPU 未被其他程序占用 |

## MCP 核心概念

> MCP（Model Context Protocol）= AI 世界的 USB Type-C
> 以前每连一个新工具都要单独写对接代码。MCP 一个标准全搞定。

## MCP 与 Skill 的关系

| 概念 | 作用 | 比喻 |
|------|------|------|
| Skill | 定义"做什么、怎么做"（流程和规范） | 菜谱 |
| MCP | 提供"能力扩展"（让 AI 能做更多事） | USB Type-C 接口 |
| 关系 | 互补：Skill 里可以调用 MCP 提供的能力 | 菜谱里用到的厨具 |

## 扩展思路

MCP 能接的不止图片和 TTS：

| MCP Server | 能力 | 教师场景 |
|------------|------|---------|
| 翻译 Server | 实时翻译 | 绘本自动生成双语版本 |
| 搜索 Server | 上网查资料 | 自动查古诗背景、作者生平 |
| 数据库 Server | 查学生名单 | 自动把绘本分发给对应班级 |
| 语音克隆 Server | 克隆教师声音 | 用教师自己的声音读绘本 |
