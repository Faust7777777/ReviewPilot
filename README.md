# ReviewPilot

> **领域专用 PR 评审 harness** — 把 PR review 拆成可观测的阶段,约束模型只基于证据输出少量高置信结论,并用小样本 eval 比较不同模型、上下文与护栏策略。它**不是通用 coding agent**,也**不承诺自动改代码**;目标是让 reviewer 更快重建 PR 上下文、减少噪声。

---

## 特性

### 三入口

| 入口 | 命令 | 说明 |
|---|---|---|
| 命令行 | `reviewpilot review <PR链接>` | 出一页 briefing 到终端 |
| 全屏 TUI | `reviewpilot chat` | 进全屏界面,贴 PR/输入意图,实时看分析过程,然后多轮追问 |
| 网页 GUI | `uvicorn reviewpilot.web:app` | 左右分屏(左=改动代码,右=briefing+对话式追问) |

### 核心能力

- **意图对照(主特色)**:拿 PR 描述/关联 issue 当"作者声称要做的事",核对代码做了没、有没有夹带未声明的改动。发现"你说只修登录,却顺手改了支付且没提"。
- **受限只读 ReAct 评审循环**:评审时模型按需调 `read_file` / `search` 取证(只读、限步数、全程 trace),而非一次性塞 diff 猜测——这是 harness 的核心求解面。
- **诚实护栏 + 可见的丢弃声明**:finding 的 `file` 必须落在 diff 改动文件 ∪ 读过的文件,否则视为幻觉丢弃;每类有配额;briefing 的"证据过滤"栏明确声明"已丢弃 N 条低可信结论",不静默忽略。
- **inspection:我检查了什么**:无论是否发现问题,都如实展示:看了哪些文件/搜了什么、检查了哪些维度、护栏过滤了几条、能力边界。
- **仓库发现(ReAct)**:输入"用户名 + 大概意图",另一个 ReAct loop(由 v4-pro 会话贡献)用 `list_repos`/`search_repos` 探索 GitHub 找到正确仓库,再开评审。
- **小样本 eval**:量化误报/漏报,支持护栏 on/off 对照;跨文件样本可走生产主路径 ReAct Review Loop 取证。

---

## 安装

需要 **Python 3.12**(`requires-python = ">=3.12,<3.13"`,3.13 因依赖轮子暂不可用)和 **gh CLI**(`gh auth login` 先登录)。

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e ".[dev]"
```

---

## 用法示例

### 1. 评审一个 GitHub PR

```bash
export DEEPSEEK_API_KEY=sk-xxxx              # 或其它 litellm 支持的 provider
export RP_MODEL=deepseek/deepseek-v4-flash   # 可选,默认即此

reviewpilot review https://github.com/owner/repo/pull/123
```

输出包含:briefing(意图对照、风险项、建议)+ "我检查了什么"(取证过程、护栏丢弃声明)+ 能力边界。

### 2. 本地模式(私有库/未推送分支)

不依赖 GitHub,直接读本地 `git diff`:

```bash
reviewpilot review --local                       # 工作区未提交改动
reviewpilot review --local --staged              # 仅暂存区
reviewpilot review --local --range main...HEAD   # 指定范围
reviewpilot review --local --range main...HEAD --title "修登录 bug" --body "修了 X"
```

### 3. TUI 多轮追问

```bash
reviewpilot chat                                          # 进全屏界面,再贴 PR 链接
reviewpilot chat https://github.com/owner/repo/pull/123   # 带参数自动开跑
```

全屏 TUI 支持实时看分析过程(read/search trace)、多轮追问(反驳、要求解释)、仓库模糊发现(输入"用户名 + 意图")。非 tty 自动回退普通多轮。

### 4. 网页 GUI

```bash
uvicorn reviewpilot.web:app --port 8848
# 打开 http://localhost:8848
```

左右分屏:左侧逐文件展示 diff(+/- 着色),右侧 briefing + 对话式追问框。

### 5. 换模型 / 分阶段模型

LLM 经 litellm 接入,按模型前缀自动选用对应 provider 的原生 key:

```bash
export RP_MODEL=openai/gpt-4o      && export OPENAI_API_KEY=sk-...
export RP_MODEL=anthropic/claude-… && export ANTHROPIC_API_KEY=sk-...

# 分阶段指定(便宜模型抽事实、强模型做判断、快模型做对话):
export RP_MODEL_ANALYZE=deepseek/deepseek-v4-flash
export RP_MODEL_CHAT=deepseek/deepseek-v4-flash
export RP_MODEL_EVAL=deepseek/deepseek-v4-flash
```

解析优先级:`RP_MODEL_<STAGE>` > `RP_MODEL` > 默认(`deepseek/deepseek-v4-flash`)。

### 6. eval 对照

```bash
reviewpilot eval evalset/samples.json            # 双栏:护栏开 vs 关(同一批 LLM 输出,确定性对照)
reviewpilot eval evalset/samples.json --no-guard # 仅护栏关(旧接口)
```

输出 TP/TN/FP/FN 与误报率/漏报率，并排展示护栏 on/off 的净效果。跨文件样本走 ReAct Review Loop。loop vs chunked 的实测对照需带 key 跑。

### 7. 查看 run trace

```bash
reviewpilot runs                 # 最近 10 条
reviewpilot runs --limit 20      # 最近 20 条
```

---

## 测试

```bash
pytest -q    # 全程注入式 stub,无需网络/密钥
```

---

## 设计取舍

### 模型选择:litellm + 分阶段 RP_MODEL

litellm 提供 provider 无关的 LLM 抽象,按模型前缀自动路由 key——可以在 DeepSeek / OpenAI / Anthropic 之间切换而无需改代码。`RP_MODEL_<STAGE>` 允许为"分析"、"对话"、"eval"分别指定模型,实现"便宜快模型做事实抽取、强模型做判断"的分层策略。默认选 `deepseek/deepseek-v4-flash` 兼顾性价比与速度。

### 上下文获取:ReAct 按需读仓库

评审时不再一次性塞全量 diff 让模型"猜",而是让模型按需 `read_file`/`search` 仓库取证——可以读调用方、相关配置、测试文件。只读、限步数(默认 max_steps=6)、全程 trace,读失败(幻觉路径→not-found)不算 grounded。私有仓库 PR 自动浅 clone 取证;本地模式直接读当前目录。

### 误报/漏报控制:证据护栏 + inspection + eval 对照

三层控制:① 证据门——finding 的 `file` 必须落在 diff 文件 ∪ 读过的文件,否则丢弃(防幻觉);② inspection——无论是否发现问题,都展示"我检查了哪些维度、护栏过滤了几条",让 reviewer 能核查;③ eval 对照——`reviewpilot eval --no-guard` 可关护栏对照,量化护栏对 FP/FN 的影响。每类 finding 有配额(默认 3 条),避免"100 条都是建议"的噪声。

---

## 架构概览

```
reviewpilot review <PR>  ─┐
                          ├─→ prfetch(gh 取 diff/标题/正文/issue)
GUI (web.py) ────────────┘     → workspace(只读仓库上下文:本地目录 or 浅 clone)
                                → review_loop(受限只读 ReAct:read_file/search 取证)
                                  ↑ 失败则回退 analyze_chunked(chunked diff 分析)
                                → guardrail(证据门 + 配额 + 丢弃记录)
                                → inspection(我检查了什么 + 诚实声明)
                                → briefing/GUI 渲染
```

| 模块 | 职责 |
|---|---|
| `reviewpilot/models.py` | `Finding` / `Briefing` / `InspectionCheck` 的 typed Pydantic 模型 |
| `reviewpilot/prfetch.py` | 经 `gh` 获取 PR 标题、正文、diff、issue(runner 可注入便于测试) |
| `reviewpilot/diffnorm.py` | 统一 diff → 带行号的结构化 hunk,处理 rename/删除/binary |
| `reviewpilot/workspace.py` | 只读工作区(RepoWorkspace/DictWorkspace),含路径穿越防护 |
| `reviewpilot/review_loop.py` | 受限只读 ReAct 评审循环:推理→工具取证→观察→再判断→停 |
| `reviewpilot/analyzer.py` | 构建意图对照 prompt、解析 LLM 输出为 typed findings(chunked 回退路径) |
| `reviewpilot/guardrail.py` | 诚实护栏:证据门 + 幻觉文件过滤 + 每类配额 + 丢弃记录 |
| `reviewpilot/inspection.py` | 确定性生成"我检查了什么":取证过程 + 丢弃声明 + 能力边界 |
| `reviewpilot/briefing.py` | 渲染一页 reviewer briefing(终端/Markdown) |
| `reviewpilot/resolve.py` | 仓库发现 ReAct loop:LLM 用 list_repos/search_repos 探索 GitHub |
| `reviewpilot/chat.py` | 多轮追问会话管理(ChatSession) |
| `reviewpilot/runlog.py` | 结构化 run trace JSONL 落盘;`reviewpilot runs` 可读;`RP_RUN_LOG` 覆盖/禁用 |
| `reviewpilot/evaluate.py` | 小样本 eval:FP/FN + 确定性护栏 A/B 双栏对照(`evaluate_pair`) |
| `reviewpilot/web.py` | 薄 GUI(FastAPI):表单 → 左右分屏 briefing + 对话式追问 |
| `reviewpilot/cli.py` / `llm.py` | CLI 接线(review/chat/eval/runs) + litellm 适配(分阶段模型,带 timeout) |
| `reviewpilot/prompts/` | 评审员/发现系统提示(外置 Markdown,可版本化/审计) |

---

## 能力边界(诚实声明)

- **不执行代码**:不构建、不运行 PR 代码。分析基于静态阅读 + 推理。
- **不判定业务正确性**:"这段逻辑是否符合产品需求"取决于代码之外的信息;此类一律标 `需人工确认`。
- **chat 追问仅带 diff+历史**:`chat` 多轮对话已就绪,但追问上下文仍限于 PR diff,未接 review_loop 的按需取证(待做)。
- **run trace 未完整落盘**:loop trace 与护栏丢弃已在 briefing 中展示,但结构化 run trace(run_id/token/各阶段模型)的持久化记录仍未完成(路线图 ④)。
- **超大 PR**:改动文件超出阈值时仅覆盖最相关部分,briefing 会注明。

---

## 依赖声明

**第三方依赖**(均在 `pyproject.toml` 声明):

- 运行时:`pydantic`、`litellm`(LLM provider 抽象)、`fastapi` + `uvicorn` + `python-multipart`(GUI)、`prompt_toolkit`(TUI 输入)、`textual`(全屏 TUI)。
- 开发:`pytest`、`httpx`。
- 外部工具:`gh`(GitHub CLI)用于获取 PR 数据;需提前 `gh auth login`。

**原创部分**:

- 意图对照分析(PR 描述 vs diff 的夹带改动检测)
- 诚实护栏(证据门/幻觉文件过滤/配额/丢弃可见声明)
- typed Pydantic finding 模型(`Finding` / `Briefing` / `InspectionCheck`)
- briefing/inspection 渲染(确定性"我检查了什么",非模型自由发挥)
- 受限只读 ReAct 评审循环(`review_loop.py`)
- 小样本 eval(FP/FN + 护栏 on/off 对照)
- GUI/CLI/TUI 接线

**借鉴了开源项目的设计思路**:PR-Agent(Apache-2.0)—— PR 获取/diff 规范化/大 PR 分块的处理思路。当前核心流水线未直接拷贝其源码。

**仓库发现 ReAct**(`resolve.py`)由另一 v4-pro 模型会话贡献;litellm/gh 为依赖工具,非原创实现。

---

## 进化路线图(已知待做)

| 优先级 | 方向 | 状态 |
|---|---|---|
| ④ | run trace 持久化(run_id + 各阶段模型/token/findings 落盘 JSONL→SQLite) | 📅 排期 |
| ⑤ | eval loop vs chunked 的实测对照(机制与样本已具备,需带 key 跑出) | 📅 配置 key 后可跑 |
| ⑥ | 配置体系:每请求超时/重试/预算/provider fallback | 待做 |
| ⑦ | 跨 PR 记忆:团队规则/历史误报/已驳回结论,作为可检索证据注入 | 待做 |
| — | chat 追问接 review_loop 的按需取证 | 待做 |

完整 harness 要素对照与设计论证见 [`docs/specs/2026-05-31-harness-positioning.md`](docs/specs/2026-05-31-harness-positioning.md)。

---

## demo 视频

(https://www.bilibili.com/video/BV1aTVQ6iEiJ/) 

脚本/分镜见 [`docs/demo-script.md`](docs/demo-script.md)。

---

## 许可证

待定(竞赛提交)。
