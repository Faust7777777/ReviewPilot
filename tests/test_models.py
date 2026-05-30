from reviewpilot.models import Finding, FindingKind, Confidence, Briefing


def test_finding_defaults_to_check_manually_and_no_human_flag():
    f = Finding(kind=FindingKind.RISK, title="off-by-one")
    assert f.confidence == Confidence.CHECK_MANUALLY
    assert f.needs_human is False
    assert f.evidence == ""


def test_briefing_holds_findings_and_serializes():
    b = Briefing(pr_ref="o/r#1", findings=[Finding(kind=FindingKind.SUMMARY, title="x")])
    assert b.findings[0].kind == FindingKind.SUMMARY
    assert b.model_dump()["pr_ref"] == "o/r#1"
