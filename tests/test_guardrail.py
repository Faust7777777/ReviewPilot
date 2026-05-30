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
