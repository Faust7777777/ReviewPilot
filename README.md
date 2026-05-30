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

# 网页 GUI:填 PR 链接 → 渲染 briefing
uvicorn reviewpilot.web:app --port 8848      # 打开 http://localhost:8848
```

模型经 `litellm` 接入,把 `RP_MODEL` / key 换成 `openai/...` 或 `anthropic/...` 即可切换 provider。

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

## 未来扩展

- 跨 PR / 跨仓库的持久化评审记忆与依赖图(避免重复指正)。
- Aider 驱动的仓库级上下文检索(RepoMap)+ 多轮对话追问。
- 误报/漏报小样本评测集(含 negative 样本)与 `reviewpilot eval` 子命令;模型/上下文策略的对照数据。
- 自动行级评论回写、CI 集成。

## 许可证

待定(竞赛提交)。
