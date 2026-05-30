import json
from reviewpilot.prfetch import fetch_pr, PRData

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


def test_parse_ref_strips_git_suffix():
    def fake_runner(args):
        if args[:3] == ["gh", "pr", "view"]:
            return json.dumps({"title": "t", "body": ""})
        if args[:3] == ["gh", "pr", "diff"]:
            return "d"
        raise AssertionError(args)
    data = fetch_pr("https://github.com/o/r.git/pull/7", runner=fake_runner)
    assert data.pr_ref == "o/r#7"
