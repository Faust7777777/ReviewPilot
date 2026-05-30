import json

from reviewpilot.evaluate import Sample, evaluate, evaluate_sample, load_samples


def _issue(name, expect=None):
    return Sample(name=name, title="t", diff="@@ +1 @@\n+x", label="issue",
                  expect_substring=expect)


def _clean(name):
    return Sample(name=name, title="t", diff="@@ +1 @@\n+x", label="clean")


# LLM stubs: produce findings depending on what we want to simulate
_RISK = '[{"kind":"risk","title":"越界","evidence":"f:1","confidence":"high"}]'
_RISK_NO_EVIDENCE = '[{"kind":"risk","title":"越界"}]'
_SUMMARY_ONLY = '[{"kind":"summary","title":"改了 x"}]'


def test_clean_sample_with_problem_finding_is_false_positive():
    r = evaluate_sample(_clean("c1"), llm=lambda p: _RISK)
    assert r.outcome == "FP"


def test_clean_sample_without_problem_finding_is_true_negative():
    r = evaluate_sample(_clean("c2"), llm=lambda p: _SUMMARY_ONLY)
    assert r.outcome == "TN"


def test_issue_sample_flagged_is_true_positive():
    r = evaluate_sample(_issue("i1"), llm=lambda p: _RISK)
    assert r.outcome == "TP"


def test_issue_sample_not_flagged_is_false_negative():
    r = evaluate_sample(_issue("i2"), llm=lambda p: _SUMMARY_ONLY)
    assert r.outcome == "FN"


def test_guardrail_off_lets_evidenceless_finding_cause_false_positive():
    on = evaluate_sample(_clean("c3"), llm=lambda p: _RISK_NO_EVIDENCE, apply_guard=True)
    off = evaluate_sample(_clean("c3"), llm=lambda p: _RISK_NO_EVIDENCE, apply_guard=False)
    assert on.outcome == "TN"   # 护栏丢掉无证据 finding
    assert off.outcome == "FP"  # 关护栏则误报


def test_rates_aggregate_correctly():
    samples = [_clean("c1"), _clean("c2"), _issue("i1"), _issue("i2")]
    # llm flags everything -> clean become FP, issue become TP
    res = evaluate(samples, llm=lambda p: _RISK)
    assert res.fp_rate == 1.0 and res.fn_rate == 0.0
    assert "误报率" in res.summary()


def test_rates_are_none_when_label_absent():
    res = evaluate([_clean("c1"), _clean("c2")], llm=lambda p: _SUMMARY_ONLY)
    assert res.fn_rate is None and res.fp_rate == 0.0
    assert "N/A" in res.summary()


def test_load_samples_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps([{"name": "x", "title": "t", "diff": "d", "label": "clean"}]))
    samples = load_samples(str(p))
    assert samples[0].name == "x" and samples[0].label == "clean"
