from reviewpilot.briefing import render_briefing
from reviewpilot.models import Briefing, Finding, FindingKind, Confidence


def test_render_includes_ref_kinds_and_needs_human_marker():
    b = Briefing(pr_ref="o/r#7", findings=[
        Finding(kind=FindingKind.INTENT_MISMATCH, title="夹带支付改动",
                file="pay.py", line_start=3, evidence="pay.py:3",
                confidence=Confidence.HIGH),
        Finding(kind=FindingKind.RISK, title="业务规则存疑", needs_human=True,
                evidence="order.py:10"),
    ])
    out = render_briefing(b)
    assert "o/r#7" in out
    assert "夹带支付改动" in out
    assert "pay.py:3" in out
    assert "需人工确认" in out
    assert "high" in out.lower()
