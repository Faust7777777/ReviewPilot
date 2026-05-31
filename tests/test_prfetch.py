import json
import subprocess

import pytest

from reviewpilot.prfetch import (
    fetch_pr, fetch_local, search_repos, PRData, PRFetchError)


def test_search_repos_parses_results():
    def runner(args):
        assert args[:3] == ["gh", "search", "repos"]
        return json.dumps([
            {"fullName": "facebook/react", "description": "A JS library"},
            {"fullName": "vuejs/vue", "description": None},
            {"fullName": "", "description": "skip-me"},
        ])
    res = search_repos("react", owner="", runner=runner)
    assert res[0]["full_name"] == "facebook/react" and res[0]["description"] == "A JS library"
    assert res[1]["description"] == ""           # None 归一化为空串
    assert all(r["full_name"] for r in res)      # 空 full_name 被过滤


def test_search_repos_broad_search_without_owner_filter():
    # 去掉 --owner 硬过滤:作者与关键词一并当普通搜索词广搜(避免 422 / 过度约束)
    seen = []
    def runner(args):
        seen.append(args)
        return json.dumps([{"fullName": "real/yuyt", "description": "hit"}])
    res = search_repos("yuyt", owner="typo", runner=runner)
    assert res == [{"full_name": "real/yuyt", "description": "hit"}]
    flat = " ".join(seen[0])
    assert "--owner" not in seen[0] and "user:" not in flat   # 无硬过滤
    assert "yuyt" in flat and "typo" in flat                  # 作者+关键词都进了广搜词


def test_search_repos_empty_terms_returns_empty_without_calling_gh():
    called = []
    search_repos("", owner="", runner=lambda a: called.append(a) or "[]")
    assert called == []                              # 无搜索词时不调 gh


def test_search_repos_wraps_gh_errors_as_prfetcherror():
    def runner(args):
        raise subprocess.CalledProcessError(1, args, stderr="HTTP 503 upstream")
    with pytest.raises(PRFetchError):
        search_repos("yuyt", owner="", runner=runner)


def test_classify_gh_error_friendly_for_invalid_search_query():
    from reviewpilot.prfetch import _classify_gh_error
    msg = _classify_gh_error('Invalid search query "user:x". ... cannot be searched ...')
    assert ("拼写" in msg) or ("没搜到" in msg)
    assert "Invalid search query" not in msg         # 不把裸错误甩给用户

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
