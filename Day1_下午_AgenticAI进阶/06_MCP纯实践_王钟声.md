# 06 — MCP 纯实践（30min）— 王钟声

**形式**：不讲 PPT，直接配、直接跑

---

## 环节设计

### Step 1：交代背景（1min）

> "其实你们前面跑绘本生成器的时候，Agent 调了图片 API 和 TTS——那都是通过 MCP 连接的。图片 MCP 和 TTS MCP 课前已经帮你们配好了。现在我们要打开盖子，看里面是怎么配的，并且用 MCP 跑通带图片+语音的完整流程。"

---

### Step 2：理解 MCP — 一张简图（3min）

王钟声画一张极简图：

```
Claude Code（你的 AI 助手）
    │
    │ MCP 协议（统一的"插头标准"）
    │
    ├── 图片 MCP Server  →  L20 服务器 FLUX.2-klein-9B → 插图
    ├── TTS MCP Server   →  本地 Higgs TTS v3 → 语音旁白
    ├── （搜索 Server）   →  搜索引擎，查最新资料
    └── （任何支持 MCP 的工具）
```

> "MCP（Model Context Protocol）= AI 世界的 USB Type-C。以前每连一个新工具都要单独写对接代码。MCP 一个标准全搞定。"
>
> **MCP 与 Skill 的关系**：
> - **Skill** 定义了"做什么、怎么做"（流程和规范）
> - **MCP** 提供了"能力扩展"（让 AI 能做更多事）
> - 两者互补：Skill 里可以调用 MCP 提供的能力

---

### Step 3：认识图片 MCP Server 配置（5min）

王钟声投屏，教师打开已有的配置：

**操作 1**：打开 `.claude/mcp.json`（课前已配好，现在看内容）

```json
{
  "mcpServers": {
    "flux-image": {
      "command": "python",
      "args": [
        "-m", "flux_mcp_server",
        "--url", "http://10.x.x.x:5500/v1/images/generations"
      ],
      "env": {
        "IMAGE_OUTPUT_DIR": "./picturebook_images"
      }
    }
  }
}
```

**解说**：
- "这就是你们一直在用的图片 MCP 配置。`flux-image` 是给 Agent 看的名字。"
- "`--url` 指向学校的 L20 服务器——FLUX.2-klein-9B 在上面跑着。你的电脑不需要装图片模型。"
- "Aquiles-Image 是 OpenAI 兼容接口，标准格式调用。"
- "未来你想换图片模型？改这个 URL 就行——其他地方不用动。"

**操作 3**：验证一下图片 MCP 是否连通：

```
输入："帮我生成一张测试图片：一只卡通小猫在草地上看书。"
```

Agent 调用图片 MCP → 生成图片 → 保存到 `./picturebook_images/` 目录。观察右侧日志中出现 `[API] flux-image`。

---

### Step 4：认识 TTS MCP Server 配置（5min）

教师打开已有配置：

**操作 1**：在 `.claude/mcp.json` 中找到 `higgs-tts` 配置块——它就在 `flux-image` 旁边：

```json
{
  "mcpServers": {
    "flux-image": {
      "command": "python",
      "args": [
        "-m", "flux_mcp_server",
        "--url", "http://10.x.x.x:5500/v1/images/generations"
      ],
      "env": {
        "IMAGE_OUTPUT_DIR": "./picturebook_images"
      }
    },
    "higgs-tts": {
      "command": "python",
      "args": [
        "-m", "higgs_tts_mcp_server",
        "--host", "localhost",
        "--port", "8080"
      ],
      "env": {
        "TTS_OUTPUT_DIR": "./picturebook_audio",
        "DEFAULT_VOICE": "zh-CN"
      }
    }
  }
}
```

**解说**：
- "TTS 跑在你自己的电脑上——每台教师机有一个独立的 Higgs TTS v3。"
- "`--port 8080` 是 llama.cpp 的本地服务端口。课前已帮你启动好了。"
- "图片走服务器（共享），语音走本地（独享）——各取所长。"
- "未来想换 TTS 模型？改配置就行，Agent 不用重新学。"

**操作 2**：验证 TTS 是否连通：

```
输入："把这段文字转成语音：'春风轻轻吹过花园，花儿们都醒了。'"
```

Agent 调用 TTS MCP → 生成 mp3 → 保存到 `./picturebook_audio/` 目录。观察右侧日志中出现 `[API] higgs-tts`。

---

### Step 5：跑完整流程 — 带语音+插图的绘本（12min）

现在图片和 TTS 都通了，用前面 Skill Part1 生成的大纲和文案，跑完整流程：

**输入 prompt**：

```
"帮我做绘本：主题____，面向____年级，6页。

要求：
1. 先生成大纲等我确认
2. 确认后逐页：写文案 → 调图片 API 生成插图 → 调 TTS 生成语音旁白
3. 每页文案自动选 Higgs TTS 情感标签
4. 全部完成后组装翻页 HTML
5. 最终网页生成前停下等我确认"
```

**完整流程（教师观察每一步）**：

```
Step 1: Agent 规划大纲 → 教师确认（Hook #1）
Step 2: Agent 生成第 1 页文案 → 调 flux-image → 插图保存
Step 3: Agent 调 higgs-tts → 旁白保存（含情感标签）
Step 4: 第 2-6 页重复 Step 2-3
Step 5: Agent 组装 HTML（翻页效果+图文+播放按钮）
Step 6: 教师预览确认（Hook #2）
Step 7: 浏览器打开 → 翻页 → 点播放按钮 → 听到 AI 语音旁白
```

**教师观察重点**：
- 右侧工具日志中交替出现 `[API] flux-image` 和 `[API] higgs-tts`
- 图片保存在 `./picturebook_images/`
- 音频保存在 `./picturebook_audio/`
- final HTML 包含了翻页效果和音频播放器

---

### Step 6：扩展思路（4min）

> "现在你们接入的是图片 API + TTS。但 MCP 能接的不止这些。"

快速展示其他 MCP Server 的例子：

| MCP Server | 能力 | 绘本场景 |
|------------|------|----------|
| 翻译 Server | 实时翻译 | 绘本自动生成双语版本 |
| 搜索 Server | 上网查资料 | 自动查古诗背景、作者生平 |
| 数据库 Server | 查学生名单 | 自动把绘本分发给对应班级 |
| 语音克隆 Server | 克隆教师声音 | 用教师自己的声音读绘本 |

> "关键不是今天接入多少工具——关键是理解这个模式：有人写好 MCP Server → 你配置几行 → AI 就能用。即插即用。"

---

## 验证清单

- [ ] `mcp.json` 中配置了 `flux-image` 和 `higgs-tts` 两个 Server
- [ ] 重启 Claude Code 后，MCP Server 连接成功
- [ ] Agent 成功调用了图片 MCP（观察右侧日志）
- [ ] Agent 成功调用了 TTS MCP（观察右侧日志）
- [ ] `./picturebook_images/` 目录下有生成的插图
- [ ] `./picturebook_audio/` 目录下有生成的 mp3
- [ ] 浏览器打开 HTML，能看到翻页效果 + 听到语音旁白

---

## 魔改挑战

**初级**：
- 修改 TTS 的默认音色（改 `DEFAULT_VOICE` 参数）
- 把图片保存目录改到桌面

**进阶**：
- 在 prompt 中指定情感标签："第 4 页用思念的情感读"
- 换一个主题重新跑整套流程（主题不同，但 Skill+MCP 不变）

---

## 排错要点

| 症状 | 排查 |
|------|------|
| `[API] flux-image` 报错 | 检查 L20 服务器 IP 是否可达：`curl http://10.x.x.x:5500/health` |
| `[API] higgs-tts` 报错 | 检查本地 TTS 服务：`curl http://localhost:8080/health` |
| MCP 配置不生效 | 确认已重启 Claude Code；确认 JSON 格式正确（无多余逗号） |
| 图片/音频未保存 | 检查 `IMAGE_OUTPUT_DIR` / `TTS_OUTPUT_DIR` 目录是否存在 |
| TTS 生成太慢 | 降低量化等级（BF16 → INT8）；确认 GPU 未被其他程序占用 |
