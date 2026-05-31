from reviewpilot.resolve import Target, interpret_target


def test_interpret_target_recognizes_local_input():
    assert interpret_target(" local --staged ") == Target("local", value="local --staged")


def test_interpret_target_recognizes_pr_url():
    text = "https://github.com/openai/codex/pull/12"
    assert interpret_target(text) == Target("pr", value=text)


def test_interpret_target_recognizes_repo_input():
    assert interpret_target("https://github.com/openai/codex.git") == Target(
        "repo", value="openai/codex"
    )


def test_interpret_target_extracts_search_terms_via_llm():
    def llm(prompt):
        assert "JSON" in prompt
        return '{"owner": "fausttttttt", "query": "yuyt"}'
    # 模糊输入 → 抽取 owner+query 去联网搜(不编仓库)
    assert interpret_target("fausttttttt yuyt", llm=llm) == Target(
        "search", value="yuyt", candidate="fausttttttt"
    )


def test_interpret_target_tolerates_fenced_json():
    llm = lambda p: '```json\n{"owner":"","query":"vue"}\n```'
    assert interpret_target("分析 vue", llm=llm) == Target("search", value="vue", candidate="")


def test_interpret_target_unknown_when_llm_extracts_nothing():
    assert interpret_target("???", llm=lambda p: '{"owner":"","query":""}') == Target("unknown")
    assert interpret_target("???", llm=lambda p: "NONE") == Target("unknown")


def test_interpret_target_returns_unknown_for_fuzzy_text_without_llm():
    assert interpret_target("react 仓库") == Target("unknown")


def test_chat_services_interpret_passes_string_prompt_to_llm(monkeypatch):
    # 回归:cli 给 interpret_target 传"字符串型 complete",而非接收 messages 列表的 chat
    from reviewpilot import cli
    seen = {}

    def fake_complete(prompt, model=None, stage=None):
        seen["type"] = type(prompt).__name__
        return '{"owner": "facebook", "query": "react"}'

    monkeypatch.setattr(cli, "complete", fake_complete)
    target = cli._ChatServices().interpret("分析 react 项目")
    assert seen["type"] == "str"
    assert target.kind == "search" and target.value == "react" and target.candidate == "facebook"
