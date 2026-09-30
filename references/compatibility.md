<!-- File purpose: Explain how this skill stays consistent across Claude, Codex, and CodeBuddy — three independent entries, one shared pipeline. -->

# Compatibility（三平台兼容策略）

本技能在 **Claude / Codex / CodeBuddy** 三个平台各有一个独立入口，全部指向同一份
canonical 内容（`SKILL.md` + `references/` + `scripts/`），从机制上保证流程一致。

## Architecture（架构）

```
        /Users/typ/Desktop/utils/skills/self_check/   ← canonical core（唯一事实来源）
        SKILL.md · rules.md · references/ · scripts/
                    │
     ┌──────────────┼──────────────┐
     ▼              ▼              ▼
~/.claude/skills  ~/.agents/skills  ~/.workbuddy/skills
  self_check ──┐   self_check ──┐   self_check ──┐
               └───────► 三处均为指向 canonical core 的软链（symlink）
```

三个入口是同一目录的软链，因此任何平台读到的 `SKILL.md`、流水线、脚本完全一致。

## Platform Entries（三平台入口）

| Platform | Entry directory | Trigger mechanism |
|---|---|---|
| Claude (Claude Code) | `~/.claude/skills/self_check/` | `description` 关键词匹配自动加载 + `/` 手动调用 |
| Codex CLI | `~/.agents/skills/self_check/` | `description` 隐式匹配 + `/skills` 显式 |
| CodeBuddy / WorkBuddy | `~/.workbuddy/skills/self_check/` | `description` 关键词自动触发 + `@skill:name` |

## Frontmatter Contract（frontmatter 约定 · 单一文件兼容三方）

```yaml
---
name: self_check              # 必须匹配目录名（Codex 要求）
description: <触发词前置的中英双语描述>   # Claude 1536 字符截断，关键词放最前
agent_created: true           # WorkBuddy skill 管理识别
---
```

- **name 匹配目录名**：三处软链目录名均为 `self_check`，与 frontmatter `name` 一致
- **description 触发词前置**：Claude 合并后截断 1536 字符，触发词必须出现在描述最前部
- 三平台对该 frontmatter 的必需字段集是并集兼容的（三方均接受 `name` + `description`，
  `agent_created` 仅 WorkBuddy 识别、其余平台忽略）

## Recognition Evidence（识别依据 · 官方文档实证）

| Platform | 用户级路径 | frontmatter 要求 | 软链支持 |
|---|---|---|---|
| Claude Code | `~/.claude/skills/`（官方 "Personal" 级） | `description` 推荐（触发判据）；其余可选 | 官方明确支持：*"can be a symlink to a directory elsewhere on disk. Claude Code follows the symlink"* |
| Codex CLI | `~/.agents/skills/`（官方 "USER" scope） | `SKILL.md` 必须含 `name` + `description` | 官方明确支持：*"Codex supports symlinked skill folders and follows the symlink target"* |
| WorkBuddy | `~/.workbuddy/skills/` | `name` + `description` 必填；建议 `agent_created: true` | 加载器（Node fs）枚举时过滤点开头目录，`fs.access`/`stat`/`readFile` 均跟随软链 |

- 触发词前置原则（Codex 官方同款建议）：*"Front-load the key use case and trigger words
  so a host can still match the skill if descriptions are shortened"* — 本技能已遵循
- frontmatter 解析验证：三个入口的 `SKILL.md` 均通过 YAML 解析（name=self_check、
  description 307 字符 < 1536 上限、agent_created=true）
- 注意：平台对**新装/变更技能**通常需重启或刷新会话才进入技能列表（Codex 文档：
  *"Codex detects skill changes automatically. If an update doesn't appear, restart Codex."*）

## Rules for Portability（可移植性规则）

- 脚本全部纯 Python 标准库（`pathlib` / `subprocess` / `json`），无第三方依赖
- `#!/usr/bin/env python3` shebang，三平台可执行
- 文件路径统一用 `/` 分隔符与 `pathlib.Path`
- 冒烟测试与 emoji 扫描的排除目录在两平台通用（`.git`、`node_modules`、`dist` 等）
- 不使用任何平台专属 API（无 Claude/Codex/WorkBuddy 专属工具调用——触发后由各平台
  的 agent 自身执行流水线，脚本只提供可复现的机械检查）

## Symlink vs Copy（软链与复制兜底）

**推荐软链**（同源维护，一处修改三处生效）：

```bash
mkdir -p ~/.claude/skills ~/.agents/skills ~/.workbuddy/skills
ln -s /Users/typ/Desktop/utils/skills/self_check ~/.claude/skills/self_check
ln -s /Users/typ/Desktop/utils/skills/self_check ~/.agents/skills/self_check
ln -s /Users/typ/Desktop/utils/skills/self_check ~/.workbuddy/skills/self_check
```

**兜底**：若某平台（如 Codex 或 WorkBuddy 的加载器）不识别软链，则对该平台改为复制：

```bash
cp -R /Users/typ/Desktop/utils/skills/self_check ~/.agents/skills/self_check
```

> 复制模式后该平台入口与 canonical core **不再同源**——每次修改 core 后需手动同步，
> 或在 README 中记录同步命令。

## Uninstall（卸载）

```bash
rm ~/.claude/skills/self_check ~/.agents/skills/self_check ~/.workbuddy/skills/self_check
# 保留 canonical core（/Users/typ/Desktop/utils/skills/self_check），需要时重装
```
