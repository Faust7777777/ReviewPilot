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
| 可观测 / trace | 🟡 部分 | Loop 取证 trace + **护栏丢弃原因**已在 briefing 诚实展示(#41/#46);TUI 会话已落盘(`sessions_store`);但结构化 run trace(run_id/token/各阶段模型)仍未落盘 |
| Eval / 回归 | 🟡 已覆盖核心(实测待跑) | 小样本 FP/FN + 护栏 A/B 对照;**已能走 ReAct review_loop**(DictWorkspace)并加了"必须读 caller 才能发现"的跨文件样本(#47);loop vs chunked 的实测对照待带 key 跑 |
| Agent 指令 / system prompt | ✅ 有(本轮外置) | 评审员系统提示 = `review_loop._SYSTEM/_FINISH` + `analyzer`/`chat` 模板,本轮从代码字符串外置为 `reviewpilot/prompts/reviewer.md`(可版本化/审计) |
| CI / Back-Pressure | ✅ 本轮 | `.github/workflows/ci.yml`:push/PR 自动跑 pytest,把回归门接进合并回路 |

> 注:根目录 `AGENTS.md`(本轮新增)是"让本仓库对**开发 ReviewPilot 的 agent** 友好"的卫生层,**不是**上表"Agent 指令 / system prompt"这一 harness 组件——后者已外置为 `reviewpilot/prompts/reviewer.md`。两者同名不同物,别混。

## 3. "名副其实"最小集 —— 完成情况

1. ✅ 仓库级**只读上下文工具**:`read_file` / `search`(`workspace.py`,PR #40)。
2. ✅ 受限 **review loop**:模型按需取证,≤N 步,只读,全程 trace(`review_loop.py`,PR #40)。
3. ✅ **evidence validator**:finding 的 file 必须落在 diff 改动文件 ∪ 读过的文件,否则当幻觉丢弃(`guardrail`,本轮)。
4. 🟡 **run trace**:Loop trace + 护栏丢弃原因已展示、TUI 会话已落盘(`sessions_store`);但结构化 run trace(run_id/token/各阶段模型)未落盘。
5. ✅ 生产与 eval **共用同一 pipeline**(PR #33)。

## 4. 进化路线图

| 优先级 | 方向 | 状态 |
|---|---|---|
| ① | provider/model 配置化(去绑定、分阶段) | ✅ PR #13 |
| ② | **受限只读 ReAct review loop + 工具集** | ✅ PR #40(取证 trace 露出 #41,证据校验 #42) |
| 工程约定 | 根 `AGENTS.md`(对开发 agent 友好,非 agent 指令组件)+ CI 回归门(Back-Pressure) | ✅ 本轮 |
| ③ | 评审员系统提示外置为 `reviewpilot/prompts/reviewer.md`(可版本化/审计) | ✅ 本轮 |
| ④ 已排期 | **run trace 持久化**(护栏丢弃原因已露出 #46;run_id + 各阶段模型/token/findings 落盘 JSONL→SQLite 待做) | 📅 |
| ⑤ | 扩 eval:让 eval **走 review_loop** + 加"必须读仓库才能发现"的样本 | ✅ 本轮(#47;机制+样本,实测对照待跑) |
| ⑥ | 配置体系:每请求超时 / 重试 / 预算 / provider fallback | ⬜ |
| ⑦ | 跨 PR 记忆:团队规则/历史误报/已驳回结论,作为可检索证据注入 | ⬜ |

## 5. 已知短板(诚实记录)

- 已修:关联 issue 填充(PR #30/#34)、diffnorm rename/删除/binary 取名(#32)、护栏证据校验(#42)、根 `AGENTS.md` + CI 回归门(#43)、评审员系统提示外置(#44)、仓库搜索改广搜修 422(#45)、护栏失败读取漏洞 + 丢弃可观测(#46)、eval 可走 review_loop + 跨文件样本(#47)。
- 仍在:结构化 run trace 未落盘(TUI 会话与护栏丢弃已可见,但缺 run_id/token/各阶段模型的持久化记录);eval 的"loop vs chunked"实测对照待带 key 跑(机制与样本已具备);`chat` 追问仍只带 diff+历史,未接 Review Loop 的按需取证;配置体系(超时/重试/预算/fallback)与进程级沙箱未做。

## 6. 论证:为什么"领域 harness"这个定位立得住

通用 agent harness 的价值在"让模型自由操作仓库去解任意任务";它的代价是难度量、易失控。
ReviewPilot 反其道:**在 PR 评审这一个任务上,把流程固定成可观测、可对照的阶段,并用护栏约束输出**。
它的 harness 性不在"自由",而在"**可替换组件 + 可度量回归 + 可对照策略**"——
这恰好契合题面的"模型选择、上下文获取方式、误报漏报控制"都需要被**对比与量化**。
因此称其为"领域专用 PR 评审 harness"既有底气(已有可注入 LLM、typed finding、护栏、eval 对照),
又不夸大(明确不是通用 agent;核心求解面已具备,仍在补 run trace 持久化与 eval 覆盖)。
