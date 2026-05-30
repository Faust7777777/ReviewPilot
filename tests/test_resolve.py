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


def test_interpret_target_asks_for_confirmation_when_llm_returns_repo():
    def llm(prompt):
        assert "owner/repo" in prompt
        return "facebook/react"

    assert interpret_target("react 仓库", llm=llm) == Target(
        "confirm",
        candidate="facebook/react",
        question="你是想评审 `facebook/react` 这个仓库吗?(y/n)",
    )


def test_interpret_target_returns_unknown_when_llm_returns_none():
    assert interpret_target("react 仓库", llm=lambda prompt: "NONE") == Target("unknown")


def test_interpret_target_returns_unknown_for_fuzzy_text_without_llm():
    assert interpret_target("react 仓库") == Target("unknown")
