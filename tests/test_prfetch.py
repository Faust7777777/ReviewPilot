import json
import subprocess

import pytest

from reviewpilot.prfetch import fetch_pr, fetch_local, PRData, PRFetchError

def test_fetch_pr_parses_gh_outputs():
    def fake_runner(args):
        if args[:3] == ["gh", "pr", "view"]:
            return json.dumps({"title": "fix login", "body": "closes #5"})
        if args[:3] == ["gh", "pr", "diff"]:
            return "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n+x"
        raise AssertionError(args)
    data = fetch_pr("https://github.com/o/r/pull/7", runner=fake_runner)
    assert isinstance(data, PRData)
    assert data.title == "fix login"
    assert "+x" in data.diff
    assert data.pr_ref == "o/r#7"


def test_fetch_pr_parses_issue_from_body_closing_keywords():
    def runner(args):
        if args[:3] == ["gh", "pr", "view"]:
            # 只请求 title,body(不依赖旧版 gh 不支持的 closingIssuesReferences)
            assert args[-1] == "title,body"
            return json.dumps({"title": "fix login", "body": "登录超时。Closes #5, also fixes #7"})
        if args[:3] == ["gh", "pr", "diff"]:
            return "diff"
        raise AssertionError(args)
    data = fetch_pr("https://github.com/o/r/pull/7", runner=runner)
    assert data.issue == "关联 issue: #5, #7"


def test_fetch_pr_issue_none_when_no_closing_refs():
    def runner(args):
        if args[:3] == ["gh", "pr", "view"]:
            return json.dumps({"title": "t", "body": "b"})
        if args[:3] == ["gh", "pr", "diff"]:
            return "diff"
        raise AssertionError(args)
    assert fetch_pr("https://github.com/o/r/pull/7", runner=runner).issue is None


def test_parse_ref_strips_git_suffix():
    def fake_runner(args):
        if args[:3] == ["gh", "pr", "view"]:
            return json.dumps({"title": "t", "body": ""})
        if args[:3] == ["gh", "pr", "diff"]:
            return "d"
        raise AssertionError(args)
    data = fetch_pr("https://github.com/o/r.git/pull/7", runner=fake_runner)
    assert data.pr_ref == "o/r#7"


def test_fetch_pr_classifies_auth_error():
    def boom(args):
        raise subprocess.CalledProcessError(1, args, stderr="gh: not logged in to any hosts")
    with pytest.raises(PRFetchError) as ei:
        fetch_pr("https://github.com/o/r/pull/7", runner=boom)
    assert "登录" in str(ei.value)


def test_fetch_local_worktree_builds_prdata():
    def runner(args):
        assert args[:4] == ["git", "-C", ".", "diff"]
        return "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n+x"
    data = fetch_local(runner=runner)
    assert data.pr_ref == "local:worktree"
    assert data.title == "(本地改动)" and "+x" in data.diff


def test_fetch_local_range_and_title():
    data = fetch_local(diff_range="main...HEAD", title="我的改动",
                       runner=lambda args: "+y")
    assert data.pr_ref == "local:main...HEAD" and data.title == "我的改动"


def test_fetch_local_empty_diff_raises():
    with pytest.raises(PRFetchError):
        fetch_local(runner=lambda args: "   \n")
