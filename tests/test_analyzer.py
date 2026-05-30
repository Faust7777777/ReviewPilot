import json
from reviewpilot.analyzer import analyze, parse_findings, build_prompt
from reviewpilot.models import FindingKind


def test_build_prompt_includes_intent_and_diff():
    p = build_prompt(diff="@@ +1 @@\n+x", title="fix login", body="only login",
                     issue="login times out")
    assert "fix login" in p and "login times out" in p and "+x" in p


def test_build_prompt_enforces_evidence_and_low_risk_guidance():
    p = build_prompt(diff="d", title="t", body="b", issue=None)
    assert "证据是强制的" in p and "新增测试" in p


def test_parse_findings_reads_json_array():
    raw = json.dumps([
        {"kind": "intent_mismatch", "title": "夹带改动", "file": "pay.py",
         "line_start": 3, "evidence": "pay.py:3", "confidence": "high"}
    ])
    fs = parse_findings(raw)
    assert fs[0].kind == FindingKind.INTENT_MISMATCH and fs[0].file == "pay.py"


def test_parse_findings_tolerates_code_fence_and_garbage():
    raw = "```json\n[{\"kind\":\"risk\",\"title\":\"t\",\"evidence\":\"f:1\"}]\n```"
    assert parse_findings(raw)[0].kind == FindingKind.RISK


def test_analyze_uses_injected_llm():
    stub = lambda prompt: '[{"kind":"summary","title":"changed add()"}]'
    fs = analyze(diff="d", title="t", body="b", issue=None, llm=stub)
    assert fs[0].title == "changed add()"


def test_parse_findings_ignores_bracket_prefix_text():
    raw = '见 [备注] 如下:\n[{"kind":"risk","title":"t","evidence":"f:1"}]'
    fs = parse_findings(raw)
    assert len(fs) == 1 and fs[0].title == "t"


def test_parse_findings_returns_empty_on_non_list_json():
    assert parse_findings('{"kind":"risk","title":"t"}') == []


def test_analyze_chunked_single_call_under_threshold():
    calls = []
    stub = lambda p: calls.append(p) or '[{"kind":"summary","title":"s"}]'
    from reviewpilot.analyzer import analyze_chunked
    analyze_chunked("small diff", "t", "b", None, llm=stub, max_chars=6000)
    assert len(calls) == 1


def test_analyze_chunked_splits_per_file_over_threshold():
    big = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n+y\n"
           "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n+n\n")
    calls = []
    stub = lambda p: calls.append(p) or '[{"kind":"summary","title":"s"}]'
    from reviewpilot.analyzer import analyze_chunked
    findings = analyze_chunked(big, "t", "b", None, llm=stub, max_chars=10)
    assert len(calls) == 2          # 按文件拆成 2 次调用
    assert len(findings) == 2       # 合并两块的 findings
