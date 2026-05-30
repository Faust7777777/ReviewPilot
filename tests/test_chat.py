import json

from reviewpilot.chat import ChatSession
from reviewpilot.cli import run_chat


def test_session_seeds_system_with_intent_diff_and_briefing():
    s = ChatSession(llm=lambda m: "ok", diff="+x", title="fix login",
                    body="b", issue="iss", briefing_text="BRIEF")
    sys = s.messages[0]
    assert sys["role"] == "system"
    assert "fix login" in sys["content"]
    assert "+x" in sys["content"]
    assert "BRIEF" in sys["content"]


def test_ask_maintains_history_and_passes_full_context():
    seen = []

    def llm(messages):
        seen.append(list(messages))
        return f"reply{len(seen)}"

    s = ChatSession(llm=llm, diff="d", title="t", body="b", issue=None, briefing_text="B")
    assert s.ask("Q1") == "reply1"
    assert s.ask("Q2") == "reply2"
    # 第二轮 llm 应看到 system + Q1 + reply1 + Q2
    assert len(seen[1]) == 4
    assert seen[1][1]["content"] == "Q1"
    assert seen[1][-1]["content"] == "Q2"
    assert len(s.messages) == 5  # system + 2*(user+assistant)


def test_run_chat_prints_briefing_then_answers_then_quits():
    def fake_runner(args):
        if args[:3] == ["gh", "pr", "view"]:
            return json.dumps({"title": "t", "body": "b"})
        if args[:3] == ["gh", "pr", "diff"]:
            return ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
                    "@@ -1 +1 @@\n+x")
        raise AssertionError(args)

    outputs = []
    inputs = iter(["why is it risky?", "q"])
    analyze_llm = lambda p: '[{"kind":"summary","title":"摘要S"}]'
    chat_llm = lambda messages: "因为 a.py:1"
    run_chat("https://github.com/o/r/pull/7", chat_llm=chat_llm, analyze_llm=analyze_llm,
             runner=fake_runner, input_fn=lambda prompt: next(inputs),
             output_fn=outputs.append)
    joined = "\n".join(outputs)
    assert "o/r#7" in joined and "摘要S" in joined   # 先打印 briefing
    assert "因为 a.py:1" in joined                   # 回答了追问
