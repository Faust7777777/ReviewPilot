# ReviewPilot 作为 Harness:定位、对照与路线图

> 本文回答"ReviewPilot 算不算 harness、该怎么定位、往哪进化"。
> 基于一次独立模型(codex / gpt-5.5)实读全仓代码的评审,诚实标注现状,不夸大。

## 1. 诚实定位

ReviewPilot 当前是一个 **领域专用的 PR 评审 harness(domain-specific PR Review Harness)**,
而**不是**通用 agent harness(如 Aider / OpenCode / Goose / OpenHands)。

它把 PR 评审拆成**可替换、可度量、可对照**的阶段(获取 → 上下文 → 模型分析 → 证据护栏 → 渲染 → 回归评测);
**且已具备 harness 的核心求解面:受限只读 ReAct 评审循环**——评审时模型按需 `read_file`/`search`
仓库取证(只读、限步数、全程 trace),基于"diff + 读到的证据"出 finding(PR #40)。
它仍**不是**让 agent 自由改仓库的通用 coding agent——刻意约束在"只读取证 + 诚实评审"。

> 对外一句话:**ReviewPilot 是一个领域专用 PR 评审 harness——把 PR review 拆成可观测的阶段,
> 约束模型只基于证据输出少量高置信结论,并用小样本 eval 比较不同模型、上下文与护栏策略。
> 它不是通用 coding agent,也不承诺自动改代码;目标是让 reviewer 更快重建 PR 上下文、减少噪声。**

## 2. Harness 要素对照(独立评审打分)

| 要素 | ReviewPilot | 说明 |
|---|---|---|
| Agent loop | ✅ 有(PR #40) | 受限只读 ReAct 评审循环:推理→调工具取证→观察→再判断→停 |
| Tool / function calling | ✅ 有(PR #40) | litellm function-calling;只读工具 `read_file` / `search`(`llm.chat_tools`) |
| 上下文 / 会话管理 | ✅ 有 | 评审时按需读仓库(workspace,本地目录/浅 clone);`chat` 多轮历史 |
| Provider / model 抽象 | ✅ 有 | litellm + 按前缀选原生 key + 分阶段模型(PR #13) |
| 权限 / 沙箱 | 🟡 部分 | 工具全只读 + 路径穿越防护 + step cap;未做进程级沙箱 |
| 配置体系 | 🟡 部分 | 分阶段模型;缺 profile / 预算 / 超时 |
| 可观测 / trace | 🟡 部分 | Loop 取证 trace 已露出在 briefing(PR #41);未做持久化 run_id |
| Eval / 回归 | ✅ 有(亮点) | 小样本 FP/FN + 护栏开关对照;与生产同链路(PR #33) |

## 3. "名副其实"最小集 —— 完成情况

1. ✅ 仓库级**只读上下文工具**:`read_file` / `search`(`workspace.py`,PR #40)。
2. ✅ 受限 **review loop**:模型按需取证,≤N 步,只读,全程 trace(`review_loop.py`,PR #40)。
3. ✅ **evidence validator**:finding 的 file 必须落在 diff 改动文件 ∪ 读过的文件,否则当幻觉丢弃(`guardrail`,本轮)。
4. 🟡 **run trace**:Loop trace 已展示;持久化 run_id/token 待做。
5. ✅ 生产与 eval **共用同一 pipeline**(PR #33)。

## 4. 进化路线图

| 优先级 | 方向 | 状态 |
|---|---|---|
| ① | provider/model 配置化(去绑定、分阶段) | ✅ PR #13 |
| ② | **受限只读 ReAct review loop + 工具集** | ✅ PR #40(取证 trace 露出 #41,证据校验本轮) |
| ③ | **run trace 持久化**(run_id + prompt/模型/token/findings/护栏丢弃原因,JSONL→SQLite) | 🟡 trace 已露出,持久化待做 |
| ④ | 扩 eval:加"必须读仓库才能发现"的上下文依赖样本,证明 ReAct 的价值 | ⬜ |
| ⑤ | 跨 PR 记忆:团队规则/历史误报/已驳回结论,作为可检索证据注入 | ⬜ |

## 5. 已知短板(诚实记录)

- 已修:关联 issue 填充(PR #30/#34)、diffnorm rename/删除/binary 取名(#32)、护栏证据校验(本轮)。
- 仍在:run trace 未持久化;`chat` 追问目前仍只带 diff+历史,未接 Review Loop 的按需取证;eval 样本偏小、尚缺"必须读仓库才能发现"的样本。

## 6. 论证:为什么"领域 harness"这个定位立得住

通用 agent harness 的价值在"让模型自由操作仓库去解任意任务";它的代价是难度量、易失控。
ReviewPilot 反其道:**在 PR 评审这一个任务上,把流程固定成可观测、可对照的阶段,并用护栏约束输出**。
它的 harness 性不在"自由",而在"**可替换组件 + 可度量回归 + 可对照策略**"——
这恰好契合题面的"模型选择、上下文获取方式、误报漏报控制"都需要被**对比与量化**。
因此称其为"领域专用 PR 评审 harness"既有底气(已有可注入 LLM、typed finding、护栏、eval 对照),
又不夸大(明确不是通用 agent、当前为 proto-harness)。
