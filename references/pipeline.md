<!-- File purpose: Canonical pipeline definition shared by all three platforms (Claude / Codex / CodeBuddy). -->

# Pipeline — Self-Check Flow

这是 self_check 技能的核心流水线定义。`SKILL.md` 是入口，本文件是完整流程。
三者独立入口（三平台软链）全部指向同一份本文件，保证流程一致。

---

## 1. Mode Detection（模式判定）

触发时按以下优先级判定模式（高优先级优先；同时命中时取高优先级）：

| Priority | Trigger keywords (中/英) | Mode |
|---|---|---|
| HIGH | 深度 / 深入检查 / 最终检查 / 全面检查 / deep / final / detailed / thorough | 多轮自检 (multi-round) |
| DEFAULT | 代码检查 / 自检 / 检查代码 / check / self-check / review my code | 单轮快速检查 (quick) |

- 无任何关键词但用户明确要求「检查」：默认单轮快速检查
- 用户说「最终检查 / final check」且此前已做过自检：多轮自检（这是交付前的收尾验证）

---

## 2. Quick Check — Single Round（单轮快速检查）

**目标**：核对用户**此前修改的代码**本身的正确性，以及这些代码的**相关引用**是否正确。

### Step 1 — Locate changes（定位改动）

```bash
python3 scripts/scan_changes.py <project> [--hours 24]
```

- 优先 `git diff`（staged + unstaged + untracked）
- 无 git 或 git 无变更 → 按最近修改时间窗口退化
- 依赖/构建目录（node_modules、dist、.git 等）自动排除

### Step 2 — Correctness of the changed code（改动代码本身正确性）

逐文件核对：
- 语法正确、可编译/可解析
- 逻辑正确：分支、循环、返回值、异常路径
- 类型与接口一致性（函数签名、参数、返回类型）
- 边界条件与空值处理

### Step 3 — Reference correctness（相关引用正确性）

对改动代码**引用到的**每项逐一核对：

| Reference kind | 核对内容 | 处理 |
|---|---|---|
| 被调用的函数 | 存在性、导入路径、签名匹配、返回类型 | 报告 + 确认后修复 |
| 数据依赖 | 字段名、表/文件/API 是否存在、格式与 schema | 报告 + 确认后修复 |
| 配置项 | key 是否存在、类型、路径、默认值 | 报告 + 确认后修复 |

> **引用问题默认只报告、不直接修改**（防误删动态导入、误判未完成代码）。确认后才修。

### Step 4 — Fix & Report

- 正确性问题（Step 2）可直接修复；引用问题（Step 3）先确认
- 修复保持结果不变（见 `rules.md`）
- 输出 Markdown 报告（模板见 §5）

---

## 3. Multi-Round Self-Check Loop（多轮自检）

**目标**：交付正确、符合全部代码规范、且在不影响结果的前提下易于维护的代码。
**范围**：每轮对**整个项目**进行完整检查（范围全量）；动态科目提供聚焦增量（科目聚焦）。

### 3.1 Loop Protocol（循环协议）

```
Round N 开始
 │
 ├─ 规划科目（每轮必须）
 │    6 个固定科目（见 check_subjects.md §1）
 │    + ≥5 个动态科目（维度 × 对象组合，见 check_subjects.md §2）
 │    → round_guard.py start-round 登记（自动防重，轮间必须不同）
 │
 ├─ 阶段 1 · 问题排查 (Diagnose)
 │    按全部科目逐项检查整个项目 → 形成问题清单
 │    与上一轮问题清单比对（round_guard.py stagnation）→ 检测停滞
 │
 ├─ 阶段 2 · 问题解决 (Fix)
 │    修复（保持结果不变；引用问题先确认；不顺手重构）
 │    每个问题记录稳定 issue id（file:line:kind:简述）
 │
 ├─ 阶段 3 · 验证 (Verify)
 │    复验修复项 + 冒烟测试（scripts/smoke_test.py）→ pass / fail / skip
 │
 ├─ 记录（round_guard.py record）
 │    本轮发现问题数 N
 │    streak = (N == 0) ? streak+1 : 0     ← 发现任何问题即重置，即使当轮已修复
 │
 └─ streak >= 3 → 结束（输出最终报告）
    否则 → Round N+1（轮次不设上限）
    非自然出口：同问题连续两轮存在（stagnation_streak>=2）→ 询问用户继续/中止
```

### 3.2 Fixed Subjects per Round（每轮固定科目）

每轮**必须**包含以下 6 个固定科目（定义与检查清单见 `check_subjects.md` §1）：

1. `correctness` — 代码正确性（含引用核对：函数/数据/配置）
2. `comparison` — 代码比较性（版本/逻辑对比）
3. `standards` — 代码规范符合
4. `emoji` — 清除一切 emoji（`scripts/emoji_scan.py`）
5. `style` — 代码风格检查
6. `smoke` — 冒烟测试（`scripts/smoke_test.py`）

### 3.3 Dynamic Subjects（动态科目）

- 每轮**至少 5 个**，根据项目**当前状态**生成（维度 × 对象，方法论见 `check_subjects.md` §2）
- **不同轮次必须各不相同**——`round_guard.py` 的 used-subjects 登记表强制约束
- 与固定科目不重叠：动态科目聚焦「维度/对象」，固定科目聚焦六类基础检查

### 3.4 Termination（终止条件）

- **必须至少连续三轮（streak >= 3）均未检查出任何代码问题**才允许结束
- 「检查出问题」指任何科目发现的任何问题（含冒烟失败、emoji 残留、风格违规）
- 当轮发现问题 → streak 重置为 0（即使当轮已修复）
- 轮次不设上限；唯一非自然出口是停滞（同一问题连续两轮存在）→ 询问用户

### 3.5 Round Bookkeeping（轮次记账）

每轮开始与结束必须调用 `scripts/round_guard.py`：

```bash
# 初始化状态（可选，文件持久化）
python3 scripts/round_guard.py init --project <path> --state .selfcheck/state.json

# 每轮开始：登记科目（动态科目 ≥5 且轮间不同；重复会报错）
python3 scripts/round_guard.py start-round \
  --state .selfcheck/state.json \
  --dynamic '["perf-hotpath", "security-secrets", ...]'

# 每轮结束：记录结果（自动计算 streak；streak>=3 时退出码 3 = DONE）
python3 scripts/round_guard.py record \
  --state .selfcheck/state.json \
  --issues <N> --fixed <M> --smoke pass|fail|skip \
  --issue-ids '["src/x.py:12:bug:off-by-one", ...]'

# 停滞检测（纯重叠比对，agent 可直接使用）
python3 scripts/round_guard.py stagnation --prev-issues '[...]' --cur-issues '[...]'
```

> `.selfcheck/` 为推荐的状态目录（脚本自动排除，不会被误检）。无权限写入时可用 `--state-json` 在内存中传递状态。

---

## 4. Smoke Test（冒烟测试）

调用 `scripts/smoke_test.py <project>`：
- 运行**所有匹配**的测试入口（非首个即止）：
  pytest / unittest / npm test / go test / cargo test / make test
- 无测试框架时兜底只读语法检查：`ast.parse` 全量 `.py`、`node --check` 全量 `.js`、`gofmt -l`
- 防挂起：`CI=1` + 每项 300s 超时；pytest 禁用 cacheprovider（不写 `.pytest_cache`）
- 退出码：`0` 通过 / `1` 失败 / `2` 跳过（无可检文件）
- **只读保证**：不安装依赖、不写源文件

---

## 5. Report Format（报告模板 · Markdown）

### 单轮快速检查报告

```markdown
## 自检报告（快速 · 单轮）
- 检查范围：<变更文件清单>
- 模式：单轮快速检查

### 正确性
| 文件 | 问题 | 严重度 | 状态 |
|---|---|---|---|
| ... | ... | high/mid/low | 已修复/待确认 |

### 引用核对
| 引用 | 类型 | 核对结果 | 状态 |
|---|---|---|---|
| foo() in src/a.py | 函数 | 签名不匹配 | 待确认 |

### 残留风险
- <未解决问题清单>
```

### 多轮自检报告（每轮 + 最终）

```markdown
## 自检报告 · Round N / <streak>
- 模式：多轮自检
- 科目清单：固定 6 项 + 动态 <清单>

### 问题排查（Diagnose）
| id | 科目 | 位置 | 问题 | 严重度 |
|---|---|---|---|---|

### 问题解决（Fix）
| id | 修复内容 | 是否影响结果 |
|---|---|---|

### 验证（Verify）
- 冒烟测试：pass / fail / skip <摘要>
- streak：<N>（连续干净轮次）

### 最终结论（DONE 时）
- 连续三轮零问题：✓
- 交付：<总结>
```

---

## 6. Output Language

- 报告一律 **Markdown**（用户偏好，除非明确要求 HTML）
- 正文中英混合：标题/流程/科目名用英文，关键解释与报告内容可用中文
