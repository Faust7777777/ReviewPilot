import json

from reviewpilot.evaluate import (
    Sample,
    evaluate,
    evaluate_sample,
    evaluate_pair,
    load_samples,
)


def _issue(name, expect=None):
    return Sample(
        name=name,
        title="t",
        diff="@@ +1 @@\n+x",
        label="issue",
        expect_substring=expect,
    )


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
    on = evaluate_sample(
        _clean("c3"), llm=lambda p: _RISK_NO_EVIDENCE, apply_guard=True
    )
    off = evaluate_sample(
        _clean("c3"), llm=lambda p: _RISK_NO_EVIDENCE, apply_guard=False
    )
    assert on.outcome == "TN"  # 护栏丢掉无证据 finding
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
    p.write_text(
        json.dumps([{"name": "x", "title": "t", "diff": "d", "label": "clean"}])
    )
    samples = load_samples(str(p))
    assert samples[0].name == "x" and samples[0].label == "clean"


def test_dict_workspace_read_search_exists():
    from reviewpilot.workspace import DictWorkspace

    ws = DictWorkspace({"a.py": "x = 1\nsend(y)\n"})
    assert ws.exists("a.py") and not ws.exists("ghost.py")
    assert "send(y)" in ws.read_file("a.py")
    assert "(找不到文件" in ws.read_file("ghost.py")
    assert "a.py:2:" in ws.search("send")  # 命中行带 path:line:
    assert ws.search("nope") == "(无匹配)"


def test_evaluate_sample_runs_review_loop_for_cross_file_sample():
    # repo_files + chat_tools/chat → 走 Review Loop:读 caller 才能发现的跨文件问题(analyze_chunked 看不到)
    s = Sample(
        name="x",
        title="t",
        body="b",
        label="issue",
        expect_substring="tasks.py",
        diff="--- a/notify.py\n+++ b/notify.py\n@@ -1 +1 @@\n-def send(msg):\n+def send(msg, channel):",
        repo_files={"tasks.py": 'send("done")\n'},
    )
    seq = [
        {
            "content": "",
            "calls": [{"id": "1", "name": "read_file", "args": {"path": "tasks.py"}}],
            "assistant_msg": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                    }
                ],
            },
        },
        {
            "content": "",
            "calls": [],
            "assistant_msg": {"role": "assistant", "content": ""},
        },
    ]
    chat_tools = lambda messages, tools: seq.pop(0)
    chat = lambda messages: (
        '[{"kind":"risk","title":"调用方未更新","file":"tasks.py",'
        '"evidence":"tasks.py:1 stale send() call"}]'
    )
    res = evaluate_sample(
        s, llm=lambda p: "[]", apply_guard=True, chat_tools=chat_tools, chat=chat
    )
    assert res.outcome == "TP"


def test_evaluate_pair_calls_llm_once_per_sample_deterministic_ab():
    call_count = [0]

    def counting_llm(prompt):
        call_count[0] += 1
        return _RISK_NO_EVIDENCE

    samples = [_clean("c1")]
    pair = evaluate_pair(samples, llm=counting_llm)
    assert call_count[0] == 1
    assert pair.guarded.results[0].outcome == "TN"
    assert pair.unguarded.results[0].outcome == "FP"


def test_evaluate_pair_evidenced_finding_retained_in_both():
    pair = evaluate_pair(
        [_issue("i1", expect="x")],
        llm=lambda p: (
            '[{"kind":"risk","title":"x","file":"a.py","evidence":"b","confidence":"high"}]'
        ),
    )
    g = pair.guarded.results[0]
    u = pair.unguarded.results[0]
    assert g.outcome == u.outcome == "TP"


def test_evaluate_pair_clean_sample_fp_only_in_unguarded():
    pair = evaluate_pair(
        [_clean("c1")],
        llm=lambda p: _RISK_NO_EVIDENCE,
    )
    assert pair.guarded.results[0].outcome == "TN"
    assert pair.unguarded.results[0].outcome == "FP"


def test_evaluate_pair_summary_prints_both_columns():
    pair = evaluate_pair([_issue("i1")], llm=lambda p: _RISK)
    s = pair.summary()
    assert "护栏开" in s and "护栏关" in s
    assert "同一批" in s


def test_evaluate_pair_cross_file_sample():
    s = Sample(
        name="x",
        title="t",
        label="issue",
        expect_substring="tasks.py",
        diff="--- a/notify.py\n+++ b/notify.py\n@@ -1 +1 @@\n-def send(msg):\n+def send(msg, channel):",
        repo_files={"tasks.py": 'send("done")\n'},
    )
    seq = [
        {
            "content": "",
            "calls": [{"id": "1", "name": "read_file", "args": {"path": "tasks.py"}}],
            "assistant_msg": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                    }
                ],
            },
        },
        {
            "content": "",
            "calls": [],
            "assistant_msg": {"role": "assistant", "content": ""},
        },
    ]
    chat_tools_fn = lambda messages, tools: seq.pop(0)
    chat_fn = lambda messages: (
        '[{"kind":"risk","title":"调用方未更新","file":"tasks.py",'
        '"evidence":"tasks.py:1 stale"}]'
    )
    pair = evaluate_pair(
        [s], llm=lambda p: "[]", chat_tools=chat_tools_fn, chat=chat_fn
    )
    assert pair.guarded.results[0].outcome == "TP"
    assert pair.unguarded.results[0].outcome == "TP"


def test_eval_smoke_samples_load_and_parse():
    """CI smoke:验证 samples.json 可加载、样本结构合法,无需 LLM key。"""
    samples = load_samples("evalset/samples.json")
    assert len(samples) > 0
    for s in samples:
        assert s.name and s.label in ("issue", "clean")
        assert s.diff or s.repo_files  # 样本必须有 diff 或仓库文件
