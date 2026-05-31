# docs/specs/ — ReviewPilot 设计决策归档

冷启动的 agent 从这里开始了解架构"为什么"。阅读顺序:

1. **`2026-05-31-harness-positioning.md`** — 先读:定位、harness 要素对照、路线图、已知短板
2. **`2026-05-29-reviewpilot-design.md`** — PD 评审 harness 的原始设计:问题空间、核心 pipeline、组件边界
3. **`2026-05-30-large-diff-strategy.md`** — 大 diff 的分块策略、回退路径(chunked vs loop)
4. **`2026-05-31-repo-discovery-agent.md`** — ReAct 仓库发现 loop 的设计与交接

## 未落库的关键决策(从 PR description 提取概要)

以下 PR 的"为什么"未写成独立 spec,但影响架构方向。决策概要 + 代码位置:

| PR | 决策 | 为什么 | 代码锚点 |
|---|---|---|---|
| #40 ReAct review loop | 用受限只读 ReAct 取代一次性塞 diff | 模型盲猜 diff 看不到的调用方→漏报;工具取证→真读文件→基于证据出 finding | `review_loop.py:1-5` |
| #42 护栏证据校验 | finding 的 file 必须落在 diff ∪ 读过的文件 | 模型会编造"看了 x.py"的幻觉 finding(尤其是 chunked 路径) | `guardrail.py:7-37` |
| #46 护栏修正 | 读失败不算 grounded + 丢弃可见 | 模型读不存在的路径→返回 not-found→不能算"证据";丢弃不再静默 | `guardrail.py:21-31`, `inspection.py` |
| #47 eval ReAct loop | eval 走真实 review_loop(DictWorkspace 只读) | 之前 eval 只测 chunked 路径,漏了主求解面 | `evaluate.py:evaluate_pair` |
| #49 仓库发现 ReAct | 模糊输入用 tool-using agent 探索而非盲猜 | gh search 索引不可靠(小/新仓库查不到);list_repos 全量看+描述匹配 | `resolve.py:56-124` |
| #50 run trace | JSONL 追加式落盘(非 SQLite) | 先落盘、先能用;token 用量+SQLite 后续 | `runlog.py:1-5` |
| #52 eval A/B + runs | 一次 LLM→双栏对照 + 读 trace 子命令 | 旧版两次 LLM 对照被模型抖动污染;trace 只写不读是半成品 | `evaluate.py:evaluate_pair`, `cli.py:runs` |

## 已知技术债(待修,非致命)

- **ReAct 循环未统一**:`review_loop.py` 和 `resolve.py` 各自实现了消息循环+工具调用+stop,模式相似但无共享抽象。后续加第三个 ReAct 场景(chat 追问接 loop 取证)时会复制第三遍——考虑抽公共 base。
- **eval 不进 CI**:完整 eval 需要 LLM key,无法 CI 自动跑。当前只有 smoke test 验证 samples 可加载。
- **无 pre-commit hook**:提示写进 AGENTS.md 但不会自动跑。CI 是合并门,本地 hook 是开发期反馈——两层分离。
