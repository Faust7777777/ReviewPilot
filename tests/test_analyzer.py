import json
from reviewpilot.analyzer import analyze, parse_findings, build_prompt
from reviewpilot.models import FindingKind


def test_build_prompt_includes_intent_and_diff():
    p = build_prompt(diff="@@ +1 @@\n+x", title="fix login", body="only login",
                     issue="login times out")
    assert "fix login" in p and "login times out" in p and "+x" in p


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
