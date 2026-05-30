import json
from reviewpilot.cli import run_review


def test_run_review_end_to_end_with_stubs():
    def fake_runner(args):
        if args[:3] == ["gh", "pr", "view"]:
            return json.dumps({"title": "fix add", "body": "only fix add()"})
        if args[:3] == ["gh", "pr", "diff"]:
            return ("diff --git a/calc.py b/calc.py\n--- a/calc.py\n+++ b/calc.py\n"
                    "@@ -1,2 +1,2 @@\n-    return a - b\n+    return a + b")
        raise AssertionError(args)
    fake_llm = lambda prompt: json.dumps([
        {"kind": "summary", "title": "修正 add() 加法"},
        {"kind": "risk", "title": "无证据应被丢弃"},
        {"kind": "risk", "title": "好的风险", "evidence": "calc.py:2", "confidence": "high"},
    ])
    out = run_review("https://github.com/o/r/pull/7", llm=fake_llm, runner=fake_runner)
    assert "o/r#7" in out
    assert "修正 add() 加法" in out
    assert "好的风险" in out
    assert "无证据应被丢弃" not in out
