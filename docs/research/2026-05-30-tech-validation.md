# 技术验证 (Day 2 · 2026-05-30)

> 目的:在写产品代码前,用真实运行排掉最大风险——"骨架到底能不能跑"。
> 方法:codex 实读 Aider/PR-Agent 源码(带文件名+行号)+ 一个真实安装 & 调用的冒烟测试。

## 1. 结论:技术地基全部验证通过 ✅

`spikes/smoke_aider_deepseek.py` 在隔离 venv 中真实运行,三项全过:

| 验证项 | 结果 |
|---|---|
| Aider 当依赖、程序化驱动 | ✅ `Coder.create(edit_format="ask")` 得到只读 `AskCoder` |
| 只读保证 | ✅ `dry_run=True` + `auto_commits=False`,跑完目标仓库 `git status` 干净 |
| LLM(DeepSeek via litellm)真实调用 | ✅ `deepseek/deepseek-v4-flash` 正常返回(带 reasoning tokens) |
| 端到端 review | ✅ 准确指出示例文件 `return a - b` 应为 `a + b`,并给出行号证据 |

## 2. 钉死的工程约束(写进 spec 当硬约束)

- **运行环境必须 Python 3.12**。3.13 会因 `numpy==1.24.3` 无对应 wheel 而源码 build 失败;3.12 一次通过(解析到 numpy 1.26.4)。
- 锁定版本:`aider-chat 0.86.2`、`litellm 1.81.10`、`openai 2.20.0`。
- 安装注意:venv 需先装 `setuptools`+`wheel`(3.12 venv 默认不带);国内走清华镜像更稳。GitHub clone 在代理下需 `http.version=HTTP/1.1` + 关压缩。
- 只读配方(已验证):`AskCoder` + `dry_run=True` + `auto_commits=False` + `dirty_commits=False` + 文件放 `read_only_fnames`。注意 `RepoMap` 会写 `.aider.tags.cache`,需用临时/隔离 workspace。
- provider 经 litellm,`deepseek/` 前缀直通;Anthropic/OpenAI 同理(双 provider 路径成立)。

## 3. 源码级架构验证(codex 实读)

### Aider(我们的引擎,Apache-2.0,`aider-chat`)
- 程序化入口:`aider/coders/base_coder.py` `Coder.create()/run()`;只读模式 `aider/coders/ask_coder.py` `AskCoder`。
- provider:`aider/llm.py` `LazyLiteLLM` → `aider/models.py` `Model.send_completion()` → `litellm.completion()`。
- 仓库上下文:`aider/repomap.py` `RepoMap`(tree-sitter + grep_ast + networkx pagerank),可复用做"找相关文件"。
- 会话:`Coder.cur_messages`/`done_messages` + `aider/history.py` `ChatSummary`(纯 ask 模式不自动裁剪,需自管)。
- **短板**:无 PR 获取、无 diff 规范化、无结构化 finding。

### PR-Agent(借鉴对象,Apache-2.0,不照搬 bot 架构)
- PR 获取/diff 规范化:`pr_agent/git_providers/`(`GitProvider` 抽象、`get_diff_files()`)→ 统一结构 `pr_agent/algo/types.py` `FilePatchInfo`。
- 带行号的 `__new hunk__`/`__old hunk__` patch 格式:`pr_agent/algo/git_patch_processing.py`。
- 大 PR 策略:`pr_agent/algo/pr_processing.py`(token 预算、压缩、`get_pr_multi_diffs` 分块)。
- 模型抽象:`LiteLLMAIHandler`(同样 litellm)。

## 4. 据此确定的架构

> **Aider = 引擎**(repo 会话 + 多轮 chat + repo-map + litellm 双 provider,跑 `AskCoder` 只读)
> **借鉴 PR-Agent** = PR 获取 + diff 规范化 + 大 PR 分块(仅借鉴,不引入其 bot 架构)
> **ReviewPilot 原创** = 意图对照 + 诚实护栏(证据绑定/置信分级,typed Pydantic finding)+ reviewer briefing + 薄 GUI + eval

## 5. 合规声明(对应提交规则)

- 第三方框架:`aider-chat`(Apache-2.0)作为依赖引入,不拷贝其源码进本仓库;`PR-Agent`(Apache-2.0)仅借鉴设计思路。两者均会在 README 列明。
- 原创边界:意图对照、诚实护栏、typed finding、briefing、GUI、eval 为本作品原创。
- 复用来源:如后续借鉴 PR-Agent 的具体 diff 处理代码,将在对应 PR 描述中注明来源与许可证。
