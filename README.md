# self_check — 代码开发后自检 Skill

三平台（Claude / Codex / CodeBuddy）通用的「代码开发后自检」技能。
**三个独立入口，同一份流水线**——三平台入口均为指向本目录的软链，任何修改三端同步。

## 功能

| 模式 | 触发词 | 行为 |
|---|---|---|
| 单轮快速检查（默认） | 代码检查 / 自检 / check code / self-check | 核对用户此前修改代码的正确性 + 引用（函数/数据/配置） |
| 多轮自检 | 深度 / 深入检查 / 最终检查 / deep / final | 全项目多轮循环：正确性/比较性/规范/清emoji/风格/冒烟测试 + 每轮 ≥5 个动态科目，连续三轮零问题才结束 |

## 目录结构

```
self_check/
├── SKILL.md              # canonical 入口（三平台软链指向）
├── rules.md              # 行为规则
├── README.md             # 本文件
├── references/
│   ├── pipeline.md       # 完整流水线（模式判定/单轮/多轮状态机/报告模板）
│   ├── check_subjects.md # 6 固定科目 + 动态科目方法论（维度×对象 + 候选池）
│   └── compatibility.md  # 三平台兼容策略
└── scripts/              # 纯 stdlib，三平台可执行
    ├── scan_changes.py   # 定位改动（git diff → 时间戳退化）
    ├── smoke_test.py     # 冒烟测试（探测全部入口 + 只读兜底）
    ├── emoji_scan.py     # emoji 检测（默认报告，--fix 显式清除）
    └── round_guard.py    # 轮次状态机（防重/streak/停滞检测）
```

## 安装（软链三平台）

```bash
mkdir -p ~/.claude/skills ~/.agents/skills ~/.workbuddy/skills
ln -s "$PWD" ~/.claude/skills/self_check
ln -s "$PWD" ~/.agents/skills/self_check
ln -s "$PWD" ~/.workbuddy/skills/self_check
```

验证：

```bash
ls -l ~/.claude/skills/self_check ~/.agents/skills/self_check ~/.workbuddy/skills/self_check
```

## 卸载

```bash
rm ~/.claude/skills/self_check ~/.agents/skills/self_check ~/.workbuddy/skills/self_check
```

canonical core（本目录）保留，需要时按上面命令重装。

## 注意

- **软链兜底**：若某平台不识别软链，对该平台改为 `cp -R "$PWD" <入口>`；
  复制后不再同源，每次修改后需手动同步（见 `references/compatibility.md`）
- **脚本依赖**：全部仅用 Python 标准库，无第三方依赖
- **状态目录**：多轮自检推荐用项目下 `.selfcheck/state.json` 保存轮次状态
  （脚本已将其加入排除目录，不会被误检）
- **单实例**：`round_guard` 状态文件为串行设计，同一项目请勿并发运行多轮自检
  （并发写会互相覆盖）；不同项目的状态文件相互独立，可并行
