# 仓库发现从管道到 Agent —— 改动交接

> 覆盖: 模糊输入定位仓库的 bad case 修复;pre-session 发现与 review loop 的工具隔离。

## 问题

用户输入 "Faust7777777 预约" 或 "privateEye-zzy 非线性函数拟合" 时,系统无法定位仓库。根因不是搜不到——已知 owner/repo 时 API 直查比搜索索引可靠(owner 拼错仍会 404)——而是发现链路不对:

1. `gh search repos` 走搜索索引,小仓库/新仓库可能永远不在索引里
2. 即使 LLM 猜对 owner/repo,也是一次性盲猜——没有工具让它列出用户全量仓库、从描述里找匹配
3. 确认阶段 y/n 僵死,用户追问"这讲了啥"被误判为 n;LLM 空有描述却无工具去读 README

## 解决方案

把仓库发现从管道改成 **ReAct agent loop**,与评审 loop 对等设计、工具隔离。

### 架构

```
用户输入
  ├─ 确定性解析(PR 链接 / owner/repo / local) → 快路径,不变
  └─ 模糊输入 → resolve_with_tools (ReAct 仓库发现)
                 ├─ 工具: list_repos(owner), search_repos(query)
                 └─ 找到 → 确认对话(mini chat)
                           ├─ y/n → 进入/重搜
                           └─ 追问 → chat_tools + repo_readme → 作答
```

| 阶段 | 工具 | 模块 | 隔离 |
|---|---|---|---|
| 仓库发现 | `list_repos` / `search_repos` | `resolve.py` | pre-session |
| PR 评审 | `read_file` / `search` | `review_loop.py` | session 内 |
| 确认对话 | `repo_readme` | `tui_app.py` | pre-session |

每套 loop 各 2 个工具,对称、克制,互不污染。

> 命名对应:发现工具对 LLM 暴露的名字是 `list_repos`(在 `cli.py` 包装注入),底层 prfetch 函数是 `list_user_repos`——两者指同一能力,勿混。

### 改动的文件

| 文件 | 改动 |
|---|---|
| `prfetch.py` | 新增 `repo_exists`(API 验证)、`repo_readme`(读 README)、`list_user_repos`(列用户全量仓库) |
| `resolve.py` | `interpret_target` 改为纯确定性解析(不调 LLM);新增 `resolve_with_tools` ReAct 发现循环 + `_RESOLVE_SYSTEM`/`_RESOLVE_TOOLS` |
| `cli.py` | `_ChatServices` 新增 `resolve_with_tools` wiring + `repo_exists`/`repo_readme`;`interpret` 不再传 LLM |
| `tui_app.py` | 模糊输入走 `_resolve_react`(ReAct → 验证 → 确认对话);确认阶段用 `chat_tools` + `repo_readme` 作答;清理死代码 `pick_repo`/`_search`/`_try_candidates_then_search` |
| `AGENTS.md` | 更新 `prfetch.py`/`resolve.py` 模块说明 |
| `tests/` | 更新 3 个测试文件,对齐新接口 |

### 数据流

```
"Faust7777777 预约"
  → interpret_target → Target("fuzzy")
  → _resolve_react
    → resolve_with_tools(ReAct):
        LLM: list_repos("Faust7777777")
        → [{full_name:"Faust7777777/yuyt", description:"心理中心预约小程序"}, ...]
        LLM: 匹配"预约"→"yuyt",输出 {"repo":"Faust7777777/yuyt"}
    → repo_exists 验证,拿描述
    → 展示确认:"找到 Faust7777777/yuyt — 心理中心预约小程序。y/n/追问?"
  → 用户追问 → chat_tools + repo_readme → LLM 读 README → 作答
  → 用户 y → _enter_repo → 列 PR
```

### 硬约束(未破坏)

- 工具全只读(`gh api` / `gh search repos`,无写盘)
- 发现工具不进 review loop——两套 loop 在 `resolve.py` 和 `review_loop.py` 完全隔离
- 密钥只走环境变量,不写文件
- 测试: `pytest -q` 119 passed
