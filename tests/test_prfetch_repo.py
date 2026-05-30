import json
import subprocess

import pytest

from reviewpilot.prfetch import (
    PRData,
    PRFetchError,
    fetch_repo_latest,
    list_open_prs,
    parse_repo,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://github.com/openai/codex", "openai/codex"),
        ("https://github.com/openai/codex/pulls", "openai/codex"),
        ("https://github.com/openai/codex.git", "openai/codex"),
        ("openai/codex", "openai/codex"),
    ],
)
def test_parse_repo_accepts_supported_shapes(text, expected):
    assert parse_repo(text) == expected


def test_parse_repo_rejects_unknown_text():
    with pytest.raises(PRFetchError):
        parse_repo("not a repo")


def test_list_open_prs_parses_number_title_and_author_login():
    def runner(args):
        assert args == [
            "gh",
            "pr",
            "list",
            "-R",
            "openai/codex",
            "--state",
            "open",
            "-L",
            "30",
            "--json",
            "number,title,author",
        ]
        return json.dumps(
            [
                {"number": 2, "title": "fix auth", "author": {"login": "alice"}},
                {"number": 3, "title": "docs", "author": None},
            ]
        )

    assert list_open_prs("openai/codex", runner=runner) == [
        {"number": 2, "title": "fix auth", "author": "alice"},
        {"number": 3, "title": "docs", "author": ""},
    ]


def test_list_open_prs_wraps_gh_errors():
    def runner(args):
        raise subprocess.CalledProcessError(1, args, stderr="HTTP 404: Not Found")

    with pytest.raises(PRFetchError) as excinfo:
        list_open_prs("openai/missing", runner=runner)

    assert "找不到" in str(excinfo.value)


def test_fetch_repo_latest_builds_prdata_from_latest_commit_files():
    calls = []

    def runner(args):
        calls.append(args)
        if args == ["gh", "api", "repos/openai/codex/commits?per_page=1"]:
            return json.dumps(
                [
                    {
                        "sha": "abcdef1234567890",
                        "commit": {"message": "fix parser\n\nbody"},
                    }
                ]
            )
        if args == ["gh", "api", "repos/openai/codex/commits/abcdef1234567890"]:
            return json.dumps(
                {
                    "files": [
                        {
                            "filename": "reviewpilot/prfetch.py",
                            "patch": "@@ -1 +1 @@\n-old\n+new",
                        },
                        {"filename": "binary.bin"},
                    ]
                }
            )
        raise AssertionError(args)

    data = fetch_repo_latest("openai/codex", runner=runner)

    assert isinstance(data, PRData)
    assert data.pr_ref == "openai/codex@abcdef1"
    assert data.title == "fix parser"
    assert data.body == ""
    assert "diff --git a/reviewpilot/prfetch.py b/reviewpilot/prfetch.py" in data.diff
    assert "@@ -1 +1 @@" in data.diff
    assert "binary.bin" not in data.diff
    assert len(calls) == 2
