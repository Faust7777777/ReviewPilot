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
