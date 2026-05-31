# AGENTS.md — ReviewPilot

写给在本仓库里工作的 agent / 协作者。手写、精简,改动请保持 ≤60 行。
(给"跑在 ReviewPilot 之上的 LLM 评审员"的系统提示**不在这里**——它外置在
`reviewpilot/prompts/reviewer.md`,由代码加载;改评审行为请改那份文件,别在 .py 里另写。)

## 这是什么
ReviewPilot = 领域专用的 **PR 评审 harness**(不是通用 coding agent)。
主特色=意图对照(核对 PR 是否真做了它声称的事);底色=诚实评审(证据绑定、置信分级、越界标"需人工确认")。
核心求解面:评审是一个**受限只读 ReAct 工具循环**——LLM 按需调 `read_file`/`search` 取证再出 finding。

## 硬约束(不要破坏)
- **只读**:评审用的工具永远只读。不要给 Review Loop 加写盘 / 执行 / shell 工具。
- **证据绑定**:finding 必须能指到 diff 或读过的文件;护栏会丢弃落在其它文件上的"幻觉" finding。
- **不臆造**:拿不准就标 `needs_human` / `check_manually`,不要编。
- **密钥只走环境变量**:绝不把 API key 写进提交的文件。
- **Python 3.12**(3.13 装不上 numpy 老轮子);venv 在 `.venv/`,装依赖 `pip install -e ".[dev]"`。

## 模块地图(reviewpilot/)
- `cli.py` — 入口(`review` / `chat` / `eval`),wiring 各阶段。
- `prfetch.py` — 取数据:gh 拉 PR、本地 git diff、`list_user_repos`/`repo_exists`/`search_repos`。
- `resolve.py` — 输入→目标:确定性优先→ReAct 仓库发现(`list_repos`/`search_repos`;与评审工具隔离)。
- `review_loop.py` — **ReAct 评审循环(主求解面)**;`workspace.py` 提供只读 `read_file`/`search`(路径穿越防护、浅 clone)。
- `prompts/reviewer.md` — 评审员系统提示(`SYSTEM`/`FINISH`/`CHUNKED`/`CHAT` 四段;代码从此加载,勿在 .py 里另写)。
- `analyzer.py` — 无 workspace 时的分块回退路径(`analyze_chunked`)。
- `llm.py` — litellm 封装:`chat`/`complete`/`chat_tools`(function-calling)、`resolve_model`(`RP_MODEL_<STAGE>` 分阶段切模型)。
- `guardrail.py` — 诚实护栏:无证据丢弃 + 每类配额 + 证据落在 diff∪读过的文件。
- `runlog.py` — 结构化 run trace 落盘:每次评审追加一行 JSONL(run_id/mode/model/findings/护栏丢弃原因/reads/searches/latency;`RP_RUN_LOG` 覆盖路径或禁用;best-effort)。
- `inspection.py` — 诚实"我检查了什么"(没问题也交代检查维度与边界)。
- `models.py` / `diffnorm.py` / `briefing.py` / `chat.py` — typed finding、diff 规范化、渲染、多轮会话。
- `tui_app.py`(textual 全屏)/ `tui.py` / `web.py`(FastAPI 对话式 GUI)— 三种人机入口。
- `evaluate.py` + `evalset/` — 回归门(FP/FN、护栏 A/B 对照)。

## 改动后必做
- 任意改动:`.venv/bin/python -m pytest -q`(CI 也会跑,见 `.github/workflows/ci.yml`)。
- 动了 `analyzer.py` / `guardrail.py` / `review_loop.py` / prompt:再跑
  `reviewpilot eval evalset/samples.json`,看误报 / 漏报有没有退化。
- 决策记录写进 `docs/specs/`;提交硬规则见 `README.md`。
