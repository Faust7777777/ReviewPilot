import json
import re
import subprocess
from dataclasses import dataclass

@dataclass
class PRData:
    pr_ref: str
    title: str
    body: str
    diff: str
    issue: str | None = None

def _default_runner(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout

def _parse_ref(url: str) -> str:
    m = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    if not m:
        raise ValueError(f"not a PR url: {url}")
    return f"{m.group(1)}/{m.group(2)}#{m.group(3)}"

def fetch_pr(url: str, runner=_default_runner) -> PRData:
    meta = json.loads(runner(["gh", "pr", "view", url, "--json", "title,body"]))
    diff = runner(["gh", "pr", "diff", url])
    return PRData(pr_ref=_parse_ref(url), title=meta.get("title", ""),
                  body=meta.get("body", ""), diff=diff)
