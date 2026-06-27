# 03 — Skill 实践 Part 1：使用现成 Skill（20min）— 王钟声

**形式**：讲师投屏演示 8min → 教师跟着操作 12min

> **本节使用两个真实的热门社区 Skill**（非自造）：
> - **superpowers**（obra/superpowers，GitHub 27K+ ⭐）：brainstorm → plan → execute 自动化工作流
> - **frontend-design**（Anthropic 官方，周安装 212K+）：50 种视觉设计风格，避免"AI 脸"网页

---

## 环节设计

> 💡 **Pulse Check（讲师过渡时）**："环境都没问题的举下手？Claude Code 能正常对话的？"（10 秒快速确认）

### Step 1：什么是 Skill（2min，口头讲，不另做 PPT）

> "刚才哲栋老师演示绘本生成器时，Agent 自动按'规划→文案→插图→语音→组装'的流程走完了。这个流程不是每次重新想的——它封装在 Skill 里。"
>
> **Skill = 菜谱**。你不会每次做红烧肉都重新想放什么——菜谱写好了，照着做就行。
>
> **单次 Prompt vs Skill 对比**：

| 维度 | 单次 Prompt | Skill |
|------|-----------|-------|
| 性质 | 一次性指令 | 可复用的标准流程 |
| 一致性 | 每次输出可能不同 | 每次都按同样标准 |
| 效率 | 每次重新写 | 一键触发 / 自动触发 |
| 比喻 | 口头交代 | 书面 SOP |
| 来源 | 你自己想 | 社区共享 + 你自己写 |

> "Skill 生态已经非常成熟——GitHub 上有 1400+ 个公开 Skill，今天我们用两个最火的。"

---

### Step 2：认识两个热门社区 Skill（3min，投屏展示）

王钟声打开 `.claude/skills/` 目录（课前已预装），展示两个 Skill：

```
.claude/skills/
├── superpowers/              ← GitHub 27K+ ⭐，最著名的社区 Skill
│   ├── SKILL.md
│   ├── brainstorming/
│   │   └── SKILL.md          ← 子 Skill：头脑风暴，帮你理清需求
│   ├── writing-plans/
│   │   └── SKILL.md          ← 子 Skill：拆解任务，生成执行计划
│   └── executing-plans/
│       └── SKILL.md          ← 子 Skill：按计划逐步执行
│
└── frontend-design/          ← Anthropic 官方，周安装 212K+
    └── SKILL.md              ← 50 种设计风格，让 AI 生成的网页不再"千篇一律"
```

> **superpowers** 是 Jesse Vincent（obra）开发的开源 Skill 套件。核心思路：**接到任务 → 先头脑风暴理清需求 → 再拆成可执行的小步骤 → 最后一步步执行**。完美诠释了下午学的 Agent 概念。
>
> **frontend-design** 是 Anthropic 官方发布的。AI 生成的网页经常"看起来都一个样"——这个 Skill 让它能做出有设计感、不撞脸的界面。

打开 `superpowers/brainstorming/SKILL.md`，快速展示结构（30 秒扫一眼）：

```markdown
---
name: Superpowers: Brainstorming
description: Use when the user asks for a new feature, project, or major change...
---

# Brainstorming

## Checklist
1. Clarify requirements with the user by asking questions... prompt user 1 question at a time up to 3 questions
2. Once requirements are clarified, present 2-3 approaches...
3. Generate a PRD...

## Key Principles
- Never start coding before completing this brainstorming phase
- Distinguish between MVP and nice-to-haves
...
```

> "看到了吗？SKILL.md 就是一个 Markdown 文件——自然语言写的，不是代码。7 个部分和刚才看的一样：Frontmatter + 场景 + 输入 + 输出 + 步骤 + 示例 + 注意事项。这个 Skill 是全球 27,000 多人在用的。"

---

### Step 3：讲师演示 — superpowers 头脑风暴 + 任务规划（3min）

王钟声投屏操作，用一个**教育场景**演示 superpowers：

```
操作 1：确认 Skill 已就绪
ls .claude/skills/superpowers/

操作 2：发起一个教学任务（用自然语言描述，superpowers 自动触发）
输入 prompt：
"我想做一个课堂互动网页：面向小学三年级学生，
学习《静夜思》这首古诗。
网页要有：诗词展示、分句解释、互动问答、
配图、以及一个朗读按钮。
帮我规划一下怎么做。"
```

**关键解说**（superpowers 自动触发后）：

1. **Brainstorming 阶段**（约 1min）：
   - Agent 不会直接写代码——它先问澄清问题
   - "这段演示展示了 Skill 的第 1 层价值：**不让 AI 瞎猜，先问清楚再动手**。"
   - Agent 可能会问："互动问答想要什么题型？选择题还是填空题？""朗读按钮是点一句读一句，还是全诗朗读？"

2. **Plan 阶段**（约 1min）：
   - 教师确认需求后，Agent 自动拆解任务
   - 输出结构化的执行计划：文件列表、每一步做什么、预估复杂度
   - "这是 Skill 的第 2 层价值：**大任务拆成小步骤，每步都可检查**。"

3. **Execute 阶段**（约 1min，展示部分执行）：
   - Agent 按计划逐步执行：创建 HTML → 写 CSS → 加互动逻辑
   - "这是第 3 层价值：**按计划执行，不乱跳步骤**。"

**解说总结**：
- "一个 prompt，Skill 帮你走了三步：理清需求 → 拆解任务 → 逐步执行。"
- "这就是今天上午和下午的区别——上午你一步步指挥 AI，下午你定目标，Agent + Skill 自己走。"
- "superpowers 是全球最火的 Claude Code Skill，27,000 多星。它做的事情，正好是今天下午我们学的 Agent 概念的最佳实践。"

---

### Step 4：教师动手 — 安装并使用两个热门 Skill（10min）

**教师操作**：

```
1. 把 superpowers/ 和 frontend-design/ 两个文件夹
   复制到自己的 .claude/skills/ 目录
   （课前已预置在共享目录 / USB）

2. 验证安装：
   ls .claude/skills/superpowers/
   ls .claude/skills/frontend-design/

3. 重启 Claude Code（或 /reload），让 Skill 加载生效
```

**任务 A：用 superpowers 规划一个教学项目（6min）**

```
输入 prompt（选自己专业的主题）：

"我想做一个教学工具：[描述你的想法]。
面向[你的学生群体]。
帮我规划一下怎么做。"
```

**各专业参考主题**（投影展示）：

| 专业 | 推荐 Prompt |
|------|------------|
| 汉语言 | "我想做一个古诗词互动学习页面，包含原文、注释、白话翻译、作者背景、背诵检查功能" |
| 影视 | "我想做一个电影镜头分析工具，输入影片片段描述，输出分镜头脚本和视觉参考" |
| 音乐 | "我想做一个乐器识别互动页面，展示不同乐器图片、音色试听、乐器家族分类" |
| 表演 | "我想做一个剧本走位可视化工具，输入舞台指示，输出演员站位示意图" |
| 设计 | "我想做一个色彩教学互动页面，展示配色方案、色彩心理学、学生配色练习区" |
| 通用 | "我想做一个课堂知识闯关游戏，包含选择题、计时、积分排行榜、错题回顾" |

**观察重点**：
- Agent 有没有先问澄清问题？（Brainstorming 生效）
- Agent 有没有拆解成小步骤？（Plan 生效）
- 如果不满意某个环节，说"修改：..."让它调整

**任务 B：体验 frontend-design（4min，做完任务 A 的教师先试）**

```
输入 prompt：
"帮我做一个简单的课程介绍页面。
课程名称：[你的课程名]。
要求：设计要有特色，不要千篇一律的样式。"
```

**对比体验**（讲师提示）：
- "如果你之前没用 frontend-design 生成过网页，回想一下上午生成的页面长什么样"
- "用了 frontend-design 之后，配色、字体、布局有没有不一样？"
- "这个 Skill 的价值：**让 AI 的审美从'能用'升级到'好看'**"

> 王钟声巡场，帮遇到问题的教师排错。
> 关键提示：
> - "superpowers 的价值不只是'帮你写代码'——是'帮你先想清楚再动手'。"
> - "frontend-design 自动生效，你不需要手动调用——每次生成网页它都在后台起作用。"
> - "这两个 Skill 都是社区共享的，全球几十万人在用。你今天学会安装 Skill，以后所有社区 Skill 你都能用。"

---

## 验证清单

- [ ] superpowers/ 和 frontend-design/ 两个文件夹已复制到 `.claude/skills/`
- [ ] 重启 / reload 后，superpowers 自动触发了 Brainstorming（Agent 先问问题再动手）
- [ ] Agent 生成了结构化的任务计划（有步骤、有文件列表）
- [ ] frontend-design 生效——生成的网页设计风格不同于默认样式
- [ ] （可选）任务 A 的计划已保存，供后续环节使用

---

## 魔改挑战

**初级**（做完的教师先试）：
- 在 superpowers Brainstorming 阶段，Agent 问你问题时，故意给模糊回答，看 Agent 会不会追问
- 在 Plan 阶段说"修改：把第 2 步和第 3 步交换顺序"，看 Agent 是否理解

**进阶**：
- 让 superpowers 完整执行一个小项目（Brainstorm → Plan → Execute 三步全走完）
- 对比：关掉 frontend-design（暂时移出 skills 文件夹），重新生成同一个网页，看设计有什么区别

---

## 阶段小结（1min）

> "刚才你们用了两个 GitHub 上最火的真实 Skill——superpowers（27K ⭐）和 frontend-design（212K 周安装）。"
>
> "关键收获：
> 1. Skill 生态是**真实存在的**——全球开发者/教育者在共享，不是我们自己造的玩具
> 2. superpowers 让你**先想清楚再动手**——这正是 Agent 和普通聊天的本质区别
> 3. frontend-design 让 AI 输出**从'能用'到'好看'**——这就是专业 Skill 的价值"
>
> "接下来，你们要自己写一个 Skill——把你自己的教学经验封装成菜谱。"
