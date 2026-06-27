# superpowers 安装指南

## 来源

- GitHub: https://github.com/obra/superpowers
- 作者: Jesse Vincent (obra)
- Stars: 27,000+
- 许可: MIT 开源

## 安装方式

### 方式 A：Plugin 安装（推荐）
在 Claude Code 中：
```
/plugin install superpowers@claude-plugins-official
```

### 方式 B：手动安装
```bash
git clone https://github.com/obra/superpowers.git
cp -r superpowers/skills/* ~/.claude/skills/
```

### 方式 C：Workshop 预装（本次使用）
课前已下载到共享目录，复制到 `.claude/skills/` 即可。

## 包含的子 Skill

| 子 Skill | 功能 |
|----------|------|
| brainstorming | 头脑风暴：先问清楚需求再动手 |
| writing-plans | 任务拆解：把大目标分解成可执行的小步骤 |
| executing-plans | 逐步执行：按计划一步步完成 |
| systematic-debugging | 系统化调试 |
| requesting-code-review | 代码审查 |
| finishing-a-development-branch | 收尾 + 提交 |

## 验证安装

重启 Claude Code 后，输入任意任务，观察 Agent 是否先问澄清问题再动手。
如果 Agent 直接写代码不先问问题 → superpowers 未生效，检查文件夹位置。
