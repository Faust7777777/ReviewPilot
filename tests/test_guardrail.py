from reviewpilot.guardrail import apply_guardrail
from reviewpilot.models import Finding, FindingKind, Confidence

def _risk(title, evidence=""):
    return Finding(kind=FindingKind.RISK, title=title, evidence=evidence)

def test_drops_risk_without_evidence_but_keeps_summary():
    out = apply_guardrail([
        _risk("no evidence"),
        _risk("good", evidence="calc.py:2 return a-b"),
        Finding(kind=FindingKind.SUMMARY, title="summary no evidence"),
    ])
    titles = [f.title for f in out]
    assert "no evidence" not in titles
    assert "good" in titles
    assert "summary no evidence" in titles

def test_caps_each_kind_to_max():
    out = apply_guardrail([_risk(f"r{i}", evidence="e") for i in range(5)], max_per_kind=3)
    assert sum(f.kind == FindingKind.RISK for f in out) == 3

def test_drops_evidence_required_findings_for_files_not_changed_in_diff():
    diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-old
+new
"""
    out = apply_guardrail([
        Finding(kind=FindingKind.RISK, title="real risk", file="a.py", evidence="a.py:1 new"),
        Finding(kind=FindingKind.RISK, title="ghost risk", file="ghost.py", evidence="ghost.py:1 nope"),
    ], diff=diff)
    titles = [f.title for f in out]
    assert "real risk" in titles
    assert "ghost risk" not in titles

def test_does_not_filter_files_when_diff_is_not_provided():
    out = apply_guardrail([
        Finding(kind=FindingKind.RISK, title="ghost risk", file="ghost.py", evidence="ghost.py:1 nope"),
    ])
    assert [f.title for f in out] == ["ghost risk"]

def test_summary_without_file_is_not_filtered_by_diff_files():
    diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-old
+new
"""
    out = apply_guardrail([
        Finding(kind=FindingKind.SUMMARY, title="summary no file"),
    ], diff=diff)
    assert [f.title for f in out] == ["summary no file"]


_DIFF_A = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n"


def test_keeps_finding_about_read_file_outside_diff():
    # ReAct loop 读了 caller.py(不在 diff)发现调用方问题 → 应保留(grounded by read_files)
    f = Finding(kind=FindingKind.RISK, title="调用方未处理新异常",
                file="caller.py", evidence="caller.py:10")
    out = apply_guardrail([f], diff=_DIFF_A, read_files=["caller.py"])
    assert [x.title for x in out] == ["调用方未处理新异常"]


def test_drops_finding_in_neither_diff_nor_read_files():
    f = Finding(kind=FindingKind.RISK, title="幻觉", file="ghost.py", evidence="ghost.py:1")
    out = apply_guardrail([f], diff=_DIFF_A, read_files=["caller.py"])
    assert out == []
