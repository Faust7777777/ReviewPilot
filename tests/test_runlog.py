import json

from reviewpilot import runlog
from reviewpilot.cli import build_briefing_for
from reviewpilot.models import Finding, FindingKind
from reviewpilot.prfetch import PRData


def _findings():
    return [
        Finding(kind=FindingKind.SUMMARY, title="改了登录流程", file=None),
        Finding(
            kind=FindingKind.RISK,
            title="未校验空输入",
            file="auth.py",
            evidence="L10",
        ),
    ]


def test_build_run_record_shape():
    dropped = [{"finding": object(), "reason": "无证据"}]
    trace = [
        {"tool": "read_file", "args": {"path": "auth.py"}, "ok": True},
        {"tool": "read_file", "args": {"path": "ghost.py"}, "ok": False},
        {"tool": "search", "args": {"query": "login"}, "hits": ["auth.py"]},
    ]
    rec = runlog.build_run_record(
        "owner/repo#7", "loop", "deepseek/x", _findings(), dropped, trace, 1.236
    )

    assert rec["pr_ref"] == "owner/repo#7"
    assert rec["mode"] == "loop"
    assert rec["model"] == "deepseek/x"
    assert rec["run_id"].endswith("-owner-repo-7")
    assert rec["ts"]
    assert rec["n_findings"] == 2
    assert rec["findings"] == [
        {"kind": "summary", "title": "改了登录流程", "file": None},
        {"kind": "risk", "title": "未校验空输入", "file": "auth.py"},
    ]
    assert rec["dropped"] == [{"reason": "无证据"}]
    # 只有 ok 的 read_file 进 reads;失败读取(ghost.py)被排除(防幻觉)
    assert rec["reads"] == ["auth.py"]
    assert rec["searches"] == ["login"]
    assert rec["latency_s"] == 1.24


def test_build_run_record_none_trace():
    rec = runlog.build_run_record(
        "local", "chunked", "m", [], [], None, 0.5
    )
    assert rec["reads"] == []
    assert rec["searches"] == []
    assert rec["n_findings"] == 0


def test_record_run_append_and_readback(tmp_path):
    path = str(tmp_path / "runs.jsonl")
    r1 = runlog.build_run_record("a#1", "chunked", "m", [], [], None, 0.1)
    r2 = runlog.build_run_record("b#2", "loop", "m", [], [], None, 0.2)

    assert runlog.record_run(r1, path=path) == path
    assert runlog.record_run(r2, path=path) == path

    lines = (tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["pr_ref"] == "a#1"
    assert json.loads(lines[1])["pr_ref"] == "b#2"


def test_record_run_best_effort_unwritable(tmp_path, capsys):
    # 把一个文件当成目录的父级 → mkdir/open 必失败,但不应抛
    afile = tmp_path / "afile"
    afile.write_text("x", encoding="utf-8")
    bad = str(afile / "sub" / "runs.jsonl")
    rec = runlog.build_run_record("a#1", "chunked", "m", [], [], None, 0.1)

    assert runlog.record_run(rec, path=bad) is None
    err = capsys.readouterr().err
    assert "run trace" in err  # 打了告警,不是静默吞错


def test_record_run_disabled_via_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RP_RUN_LOG", "off")
    rec = runlog.build_run_record("a#1", "chunked", "m", [], [], None, 0.1)
    # 不传 path → 走 _runs_path → 禁用 → 不写、返回 None
    assert runlog.record_run(rec) is None


def test_build_briefing_for_writes_when_run_log(tmp_path, monkeypatch):
    logpath = tmp_path / "runs.jsonl"
    monkeypatch.setenv("RP_RUN_LOG", str(logpath))
    pr = PRData(
        pr_ref="owner/repo#9",
        title="t",
        body="b",
        diff="diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n",
    )

    build_briefing_for(pr, llm=lambda prompt: "[]", run_log=True)

    lines = logpath.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["mode"] == "chunked"  # 无 workspace → chunked
    assert rec["pr_ref"] == "owner/repo#9"


def test_build_briefing_for_no_write_by_default(tmp_path, monkeypatch):
    logpath = tmp_path / "runs.jsonl"
    monkeypatch.setenv("RP_RUN_LOG", str(logpath))
    pr = PRData(
        pr_ref="owner/repo#9",
        title="t",
        body="b",
        diff="diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n",
    )

    build_briefing_for(pr, llm=lambda prompt: "[]")  # run_log 默认 False

    assert not logpath.exists()
