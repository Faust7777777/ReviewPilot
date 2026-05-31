from reviewpilot.resolve import Target, interpret_target, resolve_with_tools


def test_interpret_target_recognizes_local_input():
    assert interpret_target(" local --staged ") == Target(
        "local", value="local --staged"
    )


def test_interpret_target_recognizes_pr_url():
    text = "https://github.com/openai/codex/pull/12"
    assert interpret_target(text) == Target("pr", value=text)


def test_interpret_target_recognizes_repo_input():
    assert interpret_target("https://github.com/openai/codex.git") == Target(
        "repo", value="openai/codex"
    )


def test_interpret_target_returns_fuzzy_for_ambiguous_text():
    # 模糊输入不再做 one-shot LLM 抽取,直接标记 fuzzy,交给 ReAct resolve_with_tools
    assert interpret_target("fausttttttt yuyt") == Target(
        "fuzzy", value="fausttttttt yuyt"
    )
    assert interpret_target("预约相关仓库") == Target("fuzzy", value="预约相关仓库")


def test_interpret_target_returns_fuzzy_for_unknown_without_llm():
    assert interpret_target("???") == Target("fuzzy", value="???")


def test_chat_services_interpret_is_deterministic(monkeypatch):
    # 回归:interpret 不再调 LLM,纯确定性解析
    from reviewpilot import cli

    called = []

    def fake_complete(*args, **kwargs):
        called.append(1)
        return "{}"

    monkeypatch.setattr(cli, "complete", fake_complete)
    target = cli._ChatServices().interpret("分析 react 项目")
    assert called == []  # LLM 不应被调用
    assert target.kind == "fuzzy"
    assert target.value == "分析 react 项目"


def test_resolve_with_tools_calls_chat_tools_and_returns_repo():
    chat_log = []

    def chat_fn(messages, tools):
        chat_log.append(len(messages))
        # 第一轮:LLM 调 list_repos
        if len(chat_log) == 1:
            return {
                "content": "",
                "calls": [
                    {"id": "c1", "name": "list_repos", "args": {"owner": "faust"}}
                ],
                "assistant_msg": {"role": "assistant", "content": ""},
            }
        # 第二轮:LLM 看到结果,输出最终答案
        return {
            "content": '{"repo": "faust/yuyt"}',
            "calls": [],
            "assistant_msg": {"role": "assistant", "content": '{"repo": "faust/yuyt"}'},
        }

    def _list(owner):
        return '[{"full_name": "faust/yuyt", "description": "预约小程序"}]'

    tools = {"list_repos": _list}
    target = resolve_with_tools("faust的预约仓库", tools, chat_fn)
    assert target == Target("repo", value="faust/yuyt")
    assert chat_log == [2, 4]  # 两轮对话:初始+用户 / +tool


def test_resolve_with_tools_returns_unknown_when_not_found():
    def chat_fn(messages, tools):
        return {
            "content": '{"repo": ""}',
            "calls": [],
            "assistant_msg": {"role": "assistant", "content": '{"repo": ""}'},
        }

    target = resolve_with_tools("不存在的仓库", {}, chat_fn)
    assert target == Target("unknown")


def test_resolve_with_tools_parses_fenced_json():
    def chat_fn(messages, tools):
        return {
            "content": '```json\n{"repo": "a/b"}\n```',
            "calls": [],
            "assistant_msg": {"role": "assistant", "content": "```"},
        }

    target = resolve_with_tools("test", {}, chat_fn)
    assert target == Target("repo", value="a/b")


def test_resolve_with_tools_tool_failure_becomes_observation_and_model_recovers():
    # 修复 1:第一个工具(list_repos,owner 拼错)抛异常 → 异常被转成错误观察喂回模型、
    # 循环不崩 → 模型改调 search_repos 成功 → 返回正确 Target("repo")。
    from reviewpilot.prfetch import PRFetchError

    rounds = []
    observed = []  # 记录模型看到的 tool 观察内容

    def chat_fn(messages, tools):
        rounds.append(1)
        # 把上一条 tool 消息(观察)记下来,断言失败确实作为 observation 喂回。
        if messages and messages[-1].get("role") == "tool":
            observed.append(messages[-1]["content"])
        if len(rounds) == 1:
            # 第一轮:猜了一个拼错的 owner,调 list_repos
            return {
                "content": "",
                "calls": [
                    {"id": "c1", "name": "list_repos", "args": {"owner": "faustttt"}}
                ],
                "assistant_msg": {"role": "assistant", "content": ""},
            }
        if len(rounds) == 2:
            # 第二轮:看到 list_repos 失败的观察 → fallback 到 search_repos
            return {
                "content": "",
                "calls": [
                    {"id": "c2", "name": "search_repos", "args": {"query": "预约"}}
                ],
                "assistant_msg": {"role": "assistant", "content": ""},
            }
        # 第三轮:看到搜索结果 → 输出最终答案
        return {
            "content": '{"repo": "faust/yuyt"}',
            "calls": [],
            "assistant_msg": {"role": "assistant", "content": '{"repo": "faust/yuyt"}'},
        }

    def _list(owner):
        raise PRFetchError(f"找不到用户或组织 `{owner}`(可能拼写有误)。")

    def _search(query):
        return '[{"full_name": "faust/yuyt", "description": "预约小程序"}]'

    tools = {"list_repos": _list, "search_repos": _search}
    target = resolve_with_tools("faust 的预约仓库", tools, chat_fn)

    assert target == Target("repo", value="faust/yuyt")
    assert len(rounds) == 3  # 工具失败没有中止循环
    # 第一条观察是 list_repos 的失败,被包成 {"error": ...} 喂回模型
    assert '"error"' in observed[0]
    assert "找不到用户或组织" in observed[0]


def test_resolve_with_tools_all_tools_fail_returns_unknown_without_raising():
    # 修复 1:所有工具都抛异常 → 不应有异常逃逸,最终返回 Target("unknown")。
    from reviewpilot.prfetch import PRFetchError

    rounds = []

    def chat_fn(messages, tools):
        rounds.append(1)
        # 模型每轮都执着地调 list_repos(每次都失败),从不输出最终 JSON。
        return {
            "content": "",
            "calls": [
                {"id": f"c{len(rounds)}", "name": "list_repos", "args": {"owner": "x"}}
            ],
            "assistant_msg": {"role": "assistant", "content": ""},
        }

    def _boom(owner):
        raise PRFetchError("boom")

    tools = {"list_repos": _boom}
    # 不应抛异常;循环耗尽后返回 unknown
    target = resolve_with_tools("反复失败", tools, chat_fn)
    assert target == Target("unknown")
    assert len(rounds) == 5  # 循环跑满 5 轮,每轮工具失败都被吞成观察
