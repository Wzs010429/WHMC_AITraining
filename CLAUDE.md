# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## 仓库定位

本仓库是**WHMC 人工智能素养提升工作坊**的协作仓库，用于存储培训内容规划、教学材料和相关代码。

## 工作坊背景

- **名称**：人工智能素养提升工作坊（三天）
- **对象**：非计算机专业教师（汉语言、影视、音乐、表演等）
- **目标**：让教师理解 AI 科研基本工作流，能用自身专业知识参与 AI 科研团队

## 目录结构

```
Day1_下午_AgenticAI进阶/
├── 00_总览/              ← 课程总览、时间表、技术方案、风险预案
├── 01_Agent理论/          ← 🔥演示先行 + 14页PPT + 逐点对应（林哲栋，30min）
│   ├── prompts/           ← Claude Code 对话 prompt（开场演示、互动问答）
│   └── materials/         ← Agent五要素速查卡、架构总图
├── 02_Harness理论/        ← 5层精简PPT + 工具日志演示（林哲栋，25min）
│   ├── prompts/           ← Harness演示prompt、指令速查表
│   └── materials/         ← 五层扩展体系图
├── 03_Skill实践_Part1/    ← 真实社区Skill：superpowers + frontend-design（王钟声，20min）
│   ├── prompts/           ← 演示prompt、各专业参考prompt
│   └── materials/         ← SKILL.md结构参考、superpowers安装指南
├── 04_Skill实践_Part2/    ← 创建自定义Skill（王钟声，18min）
│   ├── prompts/           ← 讲师演示prompt、6个参考方向
│   ├── templates/         ← SKILL_空白模板.md
│   └── materials/         ← Skill创建检查清单
├── 05_Hook实践/           ← Hook配置 + 审核点实践（林哲栋，27min）
│   ├── code/              ← settings.json 配置示例
│   ├── prompts/           ← Hook配置/审核点/Skill中加Hook prompt
│   └── materials/         ← Hook三种类型速查
├── 06_MCP实践/            ← MCP配置 + 完整流程跑通（王钟声，30min）
│   ├── code/              ← mcp.json 配置示例
│   ├── prompts/           ← 完整流程prompt、连通性测试prompt
│   └── materials/         ← MCP排错速查
└── 07_总结/               ← 互动回顾 + 成果展示（王钟声，10min）
    └── materials/         ← 五层架构总图、教师自检清单、三天衔接图
```

## 每个章节文件夹包含

| 子目录 | 内容 |
|--------|------|
| `README.md` | 该章节完整教案（原 .md 文件） |
| `prompts/` | Claude Code 对话 prompt 文字（即"代码"——和 Claude 聊天的内容） |
| `code/` | 配置文件：settings.json、mcp.json 等 |
| `templates/` | 模板文件：SKILL.md 空白模板等 |
| `materials/` | 素材：速查卡、架构图、检查清单等 |

## 内容设计原则

- 每个技术概念必须有生活化比喻（Agent=代驾、Skill=菜谱、MCP=USB Type-C、Hook=安检口）
- 理论（PPT）和实践（上机）穿插，单一形式不超过 30 分钟
- 一个统一 Demo（AI 绘本生成器）贯穿全场，不分专业做多个案例
- Hook 设计必须强调"AI 干活，人把关"
- Skill Part 1 使用**真实社区热门 Skill**（superpowers 27K⭐ + frontend-design 212K周安装），不用自造 Skill

## 讲师分工

| 讲师 | 负责环节 | 角色 |
|------|---------|------|
| 林哲栋 | Agent 理论、Harness 理论、Hook 实践 | 理论 + 审核主线 |
| 王钟声 | Skill Part 1+2、MCP 实践、总结 | 能力 + 扩展主线 |
