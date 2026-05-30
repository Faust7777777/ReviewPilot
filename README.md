# ReviewPilot

> AI PR Review 助手 — **核对这个 PR 是否真的做了它声称要做的事,并对拿不准的地方诚实。**

用户指定一个 GitHub PR,ReviewPilot 自动获取代码变更并智能分析,产出一页面向 reviewer 的 briefing。它不追求"比谁挑出的 bug 多",而是做一件资深 reviewer 最先做、机器却普遍做不好的事:**意图对照**——拿 PR 描述 / 关联 issue 当"作者声称要做的事",核对代码做了没、有没有夹带未声明的改动;并以**诚实**为底色:每条结论绑定 diff 证据、标注置信度,越过能力边界(业务正确性)就明说"需人工确认",绝不硬给权威结论。

## 特色

- **意图对照(主特色)**:发现"你说只修登录,却顺手改了支付且没提"这类夹带改动。
- **诚实评审(底色)**:证据门(无 diff 证据的结论一律丢弃)+ 置信分级(`high` / `check manually`)+ 每类配额 + `需人工确认` 标注,直击 AI review 的"噪声/误报"软肋。
- **可对照的设计**:模型、上下文获取方式可切换,便于用数据说明设计取舍(见"未来扩展"与 eval)。

## 快速开始

需要 **Python 3.12**(3.13 因依赖 `numpy` 旧轮子暂不可用)与 `gh`(GitHub CLI,已登录)。

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e .

export DEEPSEEK_API_KEY=sk-xxxx              # 或其它 litellm 支持的 provider
export RP_MODEL=deepseek/deepseek-v4-flash   # 可选,默认即此

# 命令行:对一个 PR 出 briefing
reviewpilot review https://github.com/owner/repo/pull/123

# 多轮对话评审:全屏 TUI。先进界面、再贴 PR(能实时看到分析过程),然后继续追问
reviewpilot chat                                          # 进 TUI 后粘贴 PR 链接 / 输入 local
reviewpilot chat https://github.com/owner/repo/pull/123   # 带参数则自动开跑
# 非 tty 自动回退普通多轮;全屏界面预览见 docs/tui-screenshot.svg

# 网页 GUI:填 PR 链接 → 左右分屏(左=改动代码,右=briefing+对话式追问)
uvicorn reviewpilot.web:app --port 8848      # 打开 http://localhost:8848
```

**换模型 / 换 provider:** 模型经 `litellm` 接入,按模型前缀自动选用对应 provider 的原生 key。例如:

```bash
export RP_MODEL=openai/gpt-4o      OPENAI_API_KEY=sk-...        # 切 OpenAI
export RP_MODEL=anthropic/claude-… ANTHROPIC_API_KEY=sk-...      # 切 Anthropic
# 分阶段指定模型(便宜模型抽事实、强模型做判断、快模型做对话):
export RP_MODEL_ANALYZE=...  RP_MODEL_CHAT=...  RP_MODEL_EVAL=...
```

解析优先级:阶段 env `RP_MODEL_<STAGE>` > `RP_MODEL` > 默认(`deepseek/deepseek-v4-flash`)。

**私有仓库 / 本地模式:** 私有库的 PR 同样可评——`gh` 已登录且 token 有权限即可(`gh auth login` 或 `GH_TOKEN`)。若不想/不能走 GitHub(私有内网、未推送分支、审前自检),用**本地模式**直接读 `git diff`:

```bash
reviewpilot review --local                       # 工作区未提交改动
reviewpilot review --local --staged              # 仅暂存区
reviewpilot review --local --range main...HEAD   # 指定范围,可加 --title/--body 提供"意图"
```

获取失败会给可操作提示(未登录 / 无权限 / 速率限制 / 改用 --local),而非裸异常。

## 架构

```
reviewpilot review <PR>  ─┐
                          ├─→ prfetch(gh 取 diff/标题/正文)
GUI (web.py) ────────────┘     → analyzer(意图对照 prompt + 解析 typed findings,经 litellm 调 LLM)
                                → guardrail(证据门 + 置信分级 + 配额)
                                → briefing / GUI 渲染
```

| 模块 | 职责 |
|---|---|
| `reviewpilot/models.py` | `Finding` / `Briefing` 的 typed(Pydantic)模型 |
| `reviewpilot/prfetch.py` | 经 `gh` 获取 PR 标题、正文、diff(runner 可注入,便于测试) |
| `reviewpilot/diffnorm.py` | 统一 diff → 带行号的结构化 hunk |
| `reviewpilot/analyzer.py` | 构建意图对照 prompt、解析 LLM 输出为 typed findings |
| `reviewpilot/guardrail.py` | 诚实护栏:无证据则丢弃、每类配额 |
| `reviewpilot/briefing.py` | 渲染一页 reviewer briefing(终端/Markdown) |
| `reviewpilot/web.py` | 薄 GUI(FastAPI):表单 → 渲染 briefing |
| `reviewpilot/cli.py` / `llm.py` | CLI 接线 + LLM(litellm)适配 |

**定位:** ReviewPilot 是一个**领域专用的 PR 评审 harness**——把 PR review 拆成可替换、可度量、可对照的阶段(获取→上下文→分析→护栏→渲染→eval),而非通用 coding agent。定位论证、harness 要素对照与进化路线图见 [`docs/specs/2026-05-31-harness-positioning.md`](docs/specs/2026-05-31-harness-positioning.md)。

设计与决策详见 [`docs/specs/`](docs/specs/) 与 [`docs/research/`](docs/research/);实现计划见 [`docs/plans/`](docs/plans/)。

## 能力边界(诚实声明)

- **不执行代码**:不构建、不运行 PR 代码(沙箱/依赖/安全成本过高)。分析基于静态阅读 + 推理。
- **不判定业务正确性**:"这段逻辑是否符合产品需求"取决于代码之外的信息(PRD、需求);此类一律标 `需人工确认`,不臆断。
- 超大 PR 目前按全量 diff 处理并受模型上下文限制(分块为后续工作)。

## 依赖与原创声明

**第三方依赖**(均在 `pyproject.toml` 声明):
- 运行时:`pydantic`、`litellm`(LLM provider 抽象)、`fastapi` + `uvicorn` + `python-multipart`(GUI)。
- 开发:`pytest`、`httpx`。
- 外部工具:`gh`(GitHub CLI)用于获取 PR 数据。

**原创部分**:意图对照分析、诚实护栏(证据门/置信分级/配额)、typed finding 模型、briefing 渲染、GUI 与 CLI 接线、diff 规范化与 PR 获取层,均为本作品按自有设计原创实现。

**技术验证中调研/借鉴的开源项目**:`Aider`(Apache-2.0)、`PR-Agent`(Apache-2.0)——前者用于早期可行性验证与未来的仓库上下文/多轮对话方向,后者用于借鉴 PR 获取与 diff 处理的设计思路;当前核心流水线未直接拷贝其源码,如后续复用具体代码将在对应提交中注明来源与许可证。

## 测试

```bash
pip install -e ".[dev]"
pytest -q          # 全程注入式 stub,无需网络/密钥
```

## 评测(sanity eval)

小样本评测集(`evalset/samples.json`,含 negative 样本)+ `reviewpilot eval` 子命令,量化误报/漏报:

```bash
reviewpilot eval evalset/samples.json            # 护栏开
reviewpilot eval evalset/samples.json --no-guard # 对照
```

一次真实结果(DeepSeek,8 样本)与**诚实分析**(含证据门过严导致的漏报、改进项)见 [`evalset/RESULTS.md`](evalset/RESULTS.md)。结论方向性,非基准证明。

## 未来扩展

- 跨 PR / 跨仓库的持久化评审记忆与依赖图(避免重复指正)。
- Aider 驱动的仓库级上下文检索(RepoMap):让对话能按需读取调用方/相关文件(当前 `chat` 多轮对话已就绪,但上下文限于 PR diff)。
- 评测发现的改进:强制每条 finding 带行号证据、护栏按 kind 分级、模型分层降延迟(详见 RESULTS.md)。
- 扩充评测集、模型/上下文策略的对照数据。
- 自动行级评论回写、CI 集成。

## 许可证

待定(竞赛提交)。
