# ReviewPilot 作为 Harness:定位、对照与路线图

> 本文回答"ReviewPilot 算不算 harness、该怎么定位、往哪进化"。
> 基于一次独立模型(codex / gpt-5.5)实读全仓代码的评审,诚实标注现状,不夸大。

## 1. 诚实定位

ReviewPilot 当前是一个 **领域专用的 PR 评审 harness(domain-specific PR Review Harness)**,
而**不是**通用 agent harness(如 Aider / OpenCode / Goose / OpenHands)。

更精确的现状限定词:**linear PR review harness / proto-harness**——它把 PR 评审拆成
**可替换、可度量、可对照**的阶段(获取 → 上下文 → 模型分析 → 证据护栏 → 渲染 → 回归评测),
但还不具备通用 harness 的"agent 自由操作仓库"那一面。

> 对外一句话:**ReviewPilot 是一个领域专用 PR 评审 harness——把 PR review 拆成可观测的阶段,
> 约束模型只基于证据输出少量高置信结论,并用小样本 eval 比较不同模型、上下文与护栏策略。
> 它不是通用 coding agent,也不承诺自动改代码;目标是让 reviewer 更快重建 PR 上下文、减少噪声。**

## 2. Harness 要素对照(独立评审打分)

| 要素 | ReviewPilot | 说明 / 与 Aider·OpenCode·Goose·PR-Agent 的差距 |
|---|---|---|
| Agent loop | ❌ 无 | 固定线性流水线,非循环决策 |
| Tool / function calling | ❌ 无 | 仅程序侧 `gh`,模型不能调用工具 |
| 上下文 / 会话管理 | 🟡 部分 | `chat` 有 diff+消息历史,无仓库级检索/摘要 |
| Provider / model 抽象 | ✅ 有(已补) | litellm + 按前缀选原生 key + 分阶段模型(PR #13) |
| 权限 / 沙箱 | ❌ 无 | 无只读工具权限模型 / step cap |
| 配置体系 | 🟡 部分 | 已有分阶段模型;缺 profile / 预算 / 超时 / 重试 |
| 可观测 / trace | ❌ 无 | eval 记 latency,无 run trace |
| Eval / 回归 | ✅ 有(亮点) | 小样本 FP/FN + 护栏开关对照;样本仍小 |

## 3. "名副其实"还差什么(最小集)

1. 仓库级**只读上下文工具**:`read_file` / `search` / `list_changed_files` / `get_hunk` / RepoMap。
2. 受限 **review loop**:模型可请求上下文,最多 N 步,工具全只读,全程 trace。
3. **evidence validator**:校验 finding 的 file/line/evidence 确实来自 diff 或读到的上下文(当前护栏只查"非空")。
4. **run trace**:`run_id` + 每阶段 prompt/模型/latency/token/raw/findings/护栏丢弃原因。
5. 生产与 eval **共用同一 pipeline**,保存 raw trace 供回归。

## 4. 进化路线图(按性价比;独立评审排序)

| 优先级 | 方向 | 状态 |
|---|---|---|
| ① | **provider/model 配置化**:去 DeepSeek 绑定、分阶段模型、fallback | ✅ 已做(PR #13,fallback 待补) |
| ② | **确定性检索 → 受限只读 tool loop**:先按 PR 改动自动读同文件/调用方/测试 + RepoMap;再上"模型按需取上下文"的只读工具循环(禁 shell/写盘,≤5–8 步) | ⬜ 下一步 |
| ③ | **run trace**(JSONL→SQLite):没有 trace 就难证明"harness 可度量" | ⬜ |
| ④ | **扩 eval**:期望升级到 kind/file/evidence/关键词;生产与 eval 同入口;加真实 PR / repo fixture / 上下文依赖样本 | ⬜ |
| ⑤ | **跨 PR 记忆**:团队规则、历史误报、常改模块、已接受/驳回结论;必须作为可检索证据注入,不做不可审计的长期 prompt 记忆 | ⬜ |

## 5. 已知短板(诚实记录,供后续修)

- `prfetch` 定义了 `issue` 字段但未填充关联 issue;`diffnorm` 轻量,漏 rename/删除/binary;护栏只查证据非空、不验证证据真在 diff 中。
- `chat` 是"带历史的 diff 问答",非真正的 repo session(无摘要/无 token 预算/无工具)。

## 6. 论证:为什么"领域 harness"这个定位立得住

通用 agent harness 的价值在"让模型自由操作仓库去解任意任务";它的代价是难度量、易失控。
ReviewPilot 反其道:**在 PR 评审这一个任务上,把流程固定成可观测、可对照的阶段,并用护栏约束输出**。
它的 harness 性不在"自由",而在"**可替换组件 + 可度量回归 + 可对照策略**"——
这恰好契合题面的"模型选择、上下文获取方式、误报漏报控制"都需要被**对比与量化**。
因此称其为"领域专用 PR 评审 harness"既有底气(已有可注入 LLM、typed finding、护栏、eval 对照),
又不夸大(明确不是通用 agent、当前为 proto-harness)。
