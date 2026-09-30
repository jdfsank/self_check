---
name: self_check
description: 代码开发后自检 / Post-development code self-check. 触发词：代码检查、自检、检查代码、check code、self-check、review code → 单轮快速检查（默认：核对改动代码的正确性与引用）；深度、深入检查、最终检查、全面检查、deep check、final check、detailed → 多轮自检（全项目多轮循环：正确性/比较性/规范/清除emoji/风格/冒烟测试，至少连续三轮无问题才结束）。Works across Claude, Codex, and CodeBuddy — three entries, one shared pipeline.
agent_created: true
---

<!-- File purpose: Canonical entry point for the self-check skill. All three
     platform entries (Claude / Codex / CodeBuddy) are symlinks to this file. -->

# Self-Check（代码开发后自检）

## Operating Contract

`SKILL.md` 是唯一 canonical 入口；`references/pipeline.md` 定义完整流水线；
`references/check_subjects.md` 定义检查科目；`scripts/` 提供可复现的机械检查。
三个平台（Claude / Codex / CodeBuddy）的独立入口全部软链指向本目录——
**同一份内容，同一套流程**，修改本目录即三端同步。

触发本技能后，按 §1 判定模式，然后执行对应流水线。

---

## 1. Mode Detection（模式判定）

| 语气 / 关键词 | 模式 |
|---|---|
| 深度 / 深入检查 / 最终检查 / 全面检查 / deep / final / detailed / thorough | **多轮自检**（高优先级） |
| 代码检查 / 自检 / 检查代码 / check / self-check / review my code | **单轮快速检查**（默认） |

同时命中时取高优先级；无关键词但要求「检查」时默认单轮。完整触发词表见 `references/pipeline.md` §1。

---

## 2. Quick Check（单轮快速检查 · 默认）

核对**用户此前修改的代码**本身的正确性 + 相关引用正确性：

1. **定位改动**：`python3 scripts/scan_changes.py <project>`（git diff 优先，时间戳兜底）
2. **正确性核对**：语法、逻辑、返回值、异常路径、类型
3. **引用核对**：被调用的函数（存在/签名/导入）、数据依赖（字段/表/文件/API）、
   配置项（key/类型/路径）→ **引用问题先报告、确认后修复**
4. **修复并输出 Markdown 报告**

详细步骤见 `references/pipeline.md` §2，报告模板见 §5。

---

## 3. Multi-Round Self-Check Loop（多轮自检）

对**整个项目**逐轮完整检查；轮次不设上限，**至少连续三轮未检查出任何问题**才结束。

```
Round N
 ├─ 规划科目：6 固定 + ≥5 动态（轮间不同，round_guard 防重）
 ├─ 问题排查 (Diagnose)  → 问题清单 + 与上轮比对（停滞检测）
 ├─ 问题解决 (Fix)       → 修复（保持结果不变；引用问题先确认）
 ├─ 验证 (Verify)        → 复验 + 冒烟测试 smoke_test.py
 └─ 记录：发现任何问题 → streak=0；零问题 → streak+1
     streak >= 3 → DONE；否则 Round N+1（停滞两轮 → 询问用户）
```

### 固定科目（每轮必查 · 6 项）

`correctness`（正确性，含引用核对）· `comparison`（版本/逻辑对比）· `standards`（规范符合）
· `emoji`（清除一切 emoji，emoji_scan.py）· `style`（风格检查）· `smoke`（冒烟测试）

### 动态科目（每轮 ≥5 个）

根据项目**当前状态**生成「检查维度 × 聚焦对象」组合（如 `perf-hotpath`、`security-secrets`）；
**不同轮次必须各不相同**（`round_guard.py start-round` 强制防重）。方法论与候选池见
`references/check_subjects.md` §2。

### 轮次记账

```bash
python3 scripts/round_guard.py start-round --state .selfcheck/state.json \
  --dynamic '["perf-hotpath", "security-secrets", "config-consistency-env", ...]'
python3 scripts/round_guard.py record --state .selfcheck/state.json \
  --issues <N> --fixed <M> --smoke pass --issue-ids '[...]'   # 退出码 3 = DONE
```

---

## 4. 行为规则（Rules）

- 报告一律 **Markdown**（除非用户明确要求 HTML）
- 修复**保持结果不变**：不改行为、不改输出、不改接口；只改与问题直接相关的代码，不顺手重构
- 引用类问题**先报告、确认后修复**
- 冒烟测试**只读**运行（不装依赖、不写源文件；见 `scripts/smoke_test.py` 保证）
- 不删除用户文件；`git` 写操作需用户授权
- 报告与输出不得包含 emoji（与被检查项目同标准）
- 每轮必须输出：科目清单（固定 + 动态及选择依据）、问题明细、修复明细、冒烟结果、streak 计数

## References

- `references/pipeline.md` — 完整流水线：触发词全表、单轮流程、多轮状态机、三阶段、报告模板
- `references/check_subjects.md` — 6 固定科目定义与检查清单、动态科目方法论与候选池、需求映射
- `references/compatibility.md` — 三平台兼容策略、安装/卸载/同步说明

## Scripts

- `scripts/scan_changes.py` — 定位改动（git diff 优先 → 时间戳退化）
- `scripts/smoke_test.py` — 冒烟测试（探测全部入口 + 只读兜底；退出码 0/1/2）
- `scripts/emoji_scan.py` — emoji 检测（默认报告，`--fix` 显式清除）
- `scripts/round_guard.py` — 轮次状态机（科目登记/防重、streak、停滞检测；退出码 3 = DONE）
