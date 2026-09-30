<!-- File purpose: Subject system — fixed subjects, dynamic subject methodology, and the requirements→subjects mapping. -->

# Check Subjects（检查科目体系）

本文件定义多轮自检每轮的检查科目：6 个固定科目 + 动态生成科目。

---

## 1. Fixed Subjects（固定科目 · 每轮必查）

每轮必须完整执行以下 6 个固定科目。**范围全量**：每轮都针对整个项目。

### 1.1 correctness — 代码正确性（含引用核对）

- 语法正确（可编译/可解析）
- 逻辑正确：分支、循环、返回值、异常路径、类型
- **引用核对**（与单轮快速检查一致，但范围为全项目）：
  - 被调用的函数：存在性、导入路径、签名、返回类型
  - 数据依赖：字段、表/文件/API 是否存在、格式与 schema
  - 配置项：key 存在、类型、路径、默认值
- 处理：引用问题先报告、确认后修复

### 1.2 comparison — 代码比较性（版本 / 逻辑对比）

- **版本对比**：当前代码 vs 上一轮检查时的版本（`git diff` 或状态差异），确认修复没有引入回归
- **历史对比**：与 git 历史版本对比，确认行为没有被意外改变
- **逻辑等价性**：重构前后的逻辑等价验证（相同输入 → 相同输出）
- 输出：差异摘要 + 等价性结论

### 1.3 standards — 代码规范符合

- 语言规范（如 PEP 8 基础、语言 lint 无新增错误）
- 框架约定（如 Django/Flask/React 的惯例用法）
- 项目自身约定（README/贡献指南/既有代码风格中声明的规范）
- 命令：`ruff check` / `eslint` / `gofmt -l` 等项目已有工具（存在则运行）

### 1.4 emoji — 清除一切 emoji

- 运行 `python3 scripts/emoji_scan.py <project>` 扫描全部文本文件
- 检出 → 报告（默认）；确认后运行 `--fix` 清除
- 范围：被检查项目代码/注释/文档 + 本 skill 的输出报告（报告本身也不得含 emoji）
- 通过标准：扫描结果 0 检出

### 1.5 style — 代码风格检查

与 `standards` 的边界（避免重复执行）：
- **standards** = 语言/框架/项目**约定与规则**（是否符合规范）
- **style** = **格式化与一致性**：缩进、行宽、命名风格、空行、引号风格、import 顺序、文件尾部换行
- 命令：`ruff format --check` / `prettier --check` / `gofmt -l` 等（存在则运行）；无工具时人工核对一致性
- 通过标准：格式化检查无 diff，命名/结构一致

### 1.6 smoke — 冒烟测试

- 运行 `python3 scripts/smoke_test.py <project>`（探测全部入口 + 只读兜底）
- 通过标准：退出码 0；失败 → 本轮计入问题（streak 重置）

---

## 2. Dynamic Subjects（动态科目 · 每轮 ≥5 个，轮间不同）

### 2.1 生成方法：「检查维度 × 聚焦对象」二元组合

**维度**（从以下 20+ 维度中选择未用过的）：

```
perf 性能 / security 安全 / robustness 健壮性 / testability 可测试性
maintainability 可维护性 / dependency-health 依赖健康 / config-consistency 配置一致性
compatibility 兼容性 / boundary 边界条件 / concurrency 并发
error-handling 错误处理 / logging 日志 / resource-usage 资源使用
data-integrity 数据完整性 / api-contract API 契约 / backward-compat 向后兼容
accessibility 无障碍 / localization 本地化 / naming 命名 / documentation 文档一致性
dead-code 死代码 / duplication 重复代码 / error-transparency 错误透明度 / determinism 确定性
```

**聚焦对象**（从项目**当前状态**中提取，每轮观察项目状态后挑选）：

```
最近修改的模块 / 新增依赖 / 变更的配置 / 高复杂度函数 / 最新提交涉及文件
测试覆盖缺口 / README 承诺的功能 / CI 配置 / 错误日志热点 / 公开 API 面
数据文件与 schema / 命令行入口 / 集成点（外部调用） / 序列化边界 / 启动与退出路径
```

**组合示例**：`perf × 高复杂度函数`、`security × 新增依赖`、`config-consistency × 变更的配置`、
`error-handling × 最近修改的模块`、`compatibility × 公开 API 面`……

### 2.2 轮次差异与防重（必须遵守）

1. 每轮开始：先观察项目当前状态 → 生成 ≥5 个组合（科目名用 `维度-对象` 形式，如 `perf-hotpath`）
2. 已用科目登记在 `round_guard.py` 的状态 `used_dynamic_subjects` 中；**与之前任何轮次重复的组合必须更换**（start-round 会对重复报错）
3. 每轮的动态科目组合应避免与固定科目同名（固定科目聚焦六类基础检查，动态科目聚焦维度/对象，天然不重叠）
4. 说明依据：输出动态科目时附一行「选择依据」（从项目状态观察到的线索）

### 2.3 候选池（≥20 可直接选用，也可自行组合）

```
perf-hotpath            security-secrets           robustness-empty-input
testability-test-gap    maintainability-complexity dependency-health-outdated
config-consistency-env  compatibility-py-version   boundary-array-index
concurrency-shared-state error-handling-exceptions  logging-verbosity
resource-usage-leaks    data-integrity-schema      api-contract-signature
backward-compat-migration accessibility-keyboard  localization-hardcoded
naming-consistency      documentation-staleness    dead-code-unused
duplication-extraction  error-transparency-user    determinism-nondeterministic
security-injection      perf-io-bottleneck         config-secrets-in-repo
dependency-pinning      boundary-unicode-input     concurrency-race-window
```

> 候选池仅作示例。动态科目**必须根据项目当前状态**选择，轮间不得重复。

---

## 3. Requirements → Subjects Mapping（需求到科目映射）

| 需求（用户原话） | 对应科目 / 机制 |
|---|---|
| 代码正确性 | correctness（固定） |
| 代码的比较性（版本/逻辑对比） | comparison（固定） |
| 是否符合代码规范 | standards（固定） |
| 清除一切 emoji | emoji（固定，emoji_scan.py） |
| 代码风格检查 | style（固定） |
| 执行冒烟测试 | smoke（固定，smoke_test.py） |
| 动态生成至少 5 个科目、轮间不同 | Dynamic Subjects（§2，round_guard 防重） |
| 每轮「问题排查—问题解决—验证」 | Loop Protocol 三阶段（pipeline.md §3.1） |
| 连续三轮无问题才结束 | round_guard streak 规则 |
| 正确且不影响结果、符合规范、易维护 | 全程目标（rules.md + 各科目通过标准） |
