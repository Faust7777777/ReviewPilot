from reviewpilot.inspection import build_inspection
from reviewpilot.models import Finding, FindingKind

DIFF = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-x
+y
"""


def test_empty_findings_still_reports_what_was_checked():
    summary, inspected, limitations = build_inspection(DIFF, [])
    assert "未发现高置信问题" in summary
    dims = [c.dimension for c in inspected]
    assert dims == ["变更范围", "意图一致性", "边界/逻辑风险", "测试缺口", "接口影响"]
    assert "1 个文件" in inspected[0].note and "1 个 hunk" in inspected[0].note
    assert "未发现声明外改动" in inspected[1].note
    assert len(limitations) == 3 and "未运行测试" in limitations


def test_findings_reflected_in_summary_and_dimensions():
    findings = [Finding(kind=FindingKind.RISK, title="r", file="a.py", evidence="a.py:1")]
    summary, inspected, _ = build_inspection(DIFF, findings)
    assert "发现 1 条" in summary
    risk_dim = next(c for c in inspected if c.dimension == "边界/逻辑风险")
    assert "发现 1 处" in risk_dim.note


def test_inspection_flags_oversized_change_honestly():
    big = "".join(
        f"diff --git a/f{i}.py b/f{i}.py\n--- a/f{i}.py\n+++ b/f{i}.py\n@@ -1 +1 @@\n+x{i}\n"
        for i in range(45)
    )
    _summary, _inspected, limitations = build_inspection(big, [])
    assert any("超出一次可信完整评审" in x for x in limitations)


def test_inspection_small_change_has_no_oversized_note():
    _summary, _inspected, limitations = build_inspection(DIFF, [])
    assert not any("超出一次可信" in x for x in limitations)
