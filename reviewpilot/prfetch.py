import json
import re
import shutil
import subprocess
from dataclasses import dataclass


class PRFetchError(Exception):
    """面向用户的获取失败:带可操作提示,而非抛裸 Python 异常。"""


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
    m = re.search(r"github\.com/([^/]+)/(.+?)(?:\.git)?/pull/(\d+)(?:[/?#]|$)", url)
    if not m:
        raise PRFetchError(f"无法识别的 PR 链接:{url}")
    return f"{m.group(1)}/{m.group(2)}#{m.group(3)}"


def parse_repo(text: str) -> str:
    s = (text or "").strip()
    bare = re.fullmatch(r"([\w.-]+)/([\w.-]+)", s)
    if bare:
        return f"{bare.group(1)}/{bare.group(2)}"

    m = re.search(r"github\.com/([^/\s]+)/([^/\s?#]+)", s)
    if m:
        owner = m.group(1)
        repo = re.sub(r"\.git$", "", m.group(2))
        if repo and repo not in {"pull", "pulls"}:
            return f"{owner}/{repo}"

    raise PRFetchError(f"无法识别的仓库:{text}")


def is_pr_url(text: str) -> bool:
    s = (text or "").strip()
    if re.search(r"github\.com/[^/\s]+/[^/\s?#]+(?:\.git)?/pull/\d+(?:[/?#]|$)", s):
        return True
    return re.fullmatch(r"[\w.-]+/[\w.-]+#\d+", s) is not None


def _classify_gh_error(stderr: str) -> str:
    s = (stderr or "").lower()
    if "not logged" in s or "authentication" in s:
        return "gh 未登录。请先 `gh auth login`,或设置 GH_TOKEN;私有库还需 token 对该仓库有权限。"
    if "404" in s or "not found" in s or "not accessible" in s:
        return "找不到该 PR 或无访问权限(私有库需 token 有权限,或改用本地模式 --local)。"
    if "rate limit" in s:
        return "触发 GitHub API 速率限制,请稍后再试。"
    if "saml" in s or "sso" in s:
        return "该组织启用 SSO,请为 token 授权 SSO 后重试。"
    return f"gh 调用失败:{(stderr or '').strip()[:200]}"


def fetch_pr(url: str, runner=_default_runner) -> PRData:
    pr_ref = _parse_ref(url)
    if runner is _default_runner and shutil.which("gh") is None:
        raise PRFetchError("未找到 gh(GitHub CLI)。请安装并 `gh auth login`,或改用本地模式 --local。")
    try:
        # 只用 title,body(所有 gh 版本都支持;closingIssuesReferences 旧版 gh 不支持会整体报错)
        meta = json.loads(runner(["gh", "pr", "view", url, "--json", "title,body"]))
        diff = runner(["gh", "pr", "diff", url])
    except subprocess.CalledProcessError as exc:
        raise PRFetchError(_classify_gh_error(getattr(exc, "stderr", "") or "")) from exc
    body = meta.get("body", "")
    return PRData(pr_ref=pr_ref, title=meta.get("title", ""),
                  body=body, diff=diff, issue=_issue_from_body(body))


_CLOSING_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)


def _issue_from_body(body: str) -> str | None:
    """从 PR 正文解析 closes/fixes/resolves #N 关联 issue 作意图信号(不依赖 gh 字段)。"""
    nums = _CLOSING_RE.findall(body or "")
    if not nums:
        return None
    seen = list(dict.fromkeys(nums))  # 去重保序
    return "关联 issue: " + ", ".join(f"#{n}" for n in seen)


def list_open_prs(repo: str, runner=_default_runner) -> list[dict]:
    try:
        raw = runner([
            "gh", "pr", "list", "-R", repo, "--state", "open",
            "-L", "30", "--json", "number,title,author",
        ])
    except subprocess.CalledProcessError as exc:
        raise PRFetchError(_classify_gh_error(getattr(exc, "stderr", "") or "")) from exc

    prs = json.loads(raw)
    return [
        {
            "number": item.get("number"),
            "title": item.get("title", ""),
            "author": (item.get("author") or {}).get("login", ""),
        }
        for item in prs
    ]


def search_repos(query: str, owner: str = "", runner=_default_runner) -> list[dict]:
    """联网搜 GitHub 真实仓库(用户只记得大概名字/内容时)。返回 [{full_name, description}]。
    owner 用 --owner 限定(能精确搜到该用户的仓库);若搜空(如 owner 拼错)再回退广搜关键词。"""
    q, ow = (query or "").strip(), (owner or "").strip()
    base = ["gh", "search", "repos", "-L", "10", "--json", "fullName,description"]
    attempts = []
    if ow:
        attempts.append(base + ["--owner", ow] + ([q] if q else []))
    if q:
        attempts.append(base + [q])  # 回退:不限 owner 的广搜(owner 拼错/不在文本时)
    rows = []
    for args in attempts:
        try:
            rows = json.loads(runner(args))
        except subprocess.CalledProcessError as exc:
            raise PRFetchError(_classify_gh_error(getattr(exc, "stderr", "") or "")) from exc
        if rows:
            break
    return [{"full_name": it.get("fullName", ""),
             "description": (it.get("description") or "").strip()}
            for it in rows if it.get("fullName")]


def fetch_repo_latest(repo: str, runner=_default_runner) -> PRData:
    try:
        commits = json.loads(runner(["gh", "api", f"repos/{repo}/commits?per_page=1"]))
        if not commits:
            raise PRFetchError(f"仓库没有可评审的提交:{repo}")
        latest = commits[0]
        sha = latest.get("sha", "")
        message = (latest.get("commit") or {}).get("message", "")
        detail = json.loads(runner(["gh", "api", f"repos/{repo}/commits/{sha}"]))
    except subprocess.CalledProcessError as exc:
        raise PRFetchError(_classify_gh_error(getattr(exc, "stderr", "") or "")) from exc

    blocks = []
    for item in detail.get("files", []):
        patch = item.get("patch")
        filename = item.get("filename", "")
        if not patch or not filename:
            continue
        # 补 ---/+++ 头,让下游按文件名解析(否则文件名为空、显示"改动")
        blocks.append(
            f"diff --git a/{filename} b/{filename}\n"
            f"--- a/{filename}\n+++ b/{filename}\n{patch}"
        )

    title = message.splitlines()[0] if message else ""
    return PRData(
        pr_ref=f"{repo}@{sha[:7]}",
        title=title,
        body="",
        diff="\n".join(blocks),
    )


def fetch_local(staged: bool = False, diff_range: str | None = None,
                title: str | None = None, body: str = "", repo_dir: str = ".",
                runner=_default_runner) -> PRData:
    """本地模式:直接读 git diff,不依赖 GitHub。适合私有库 / 未推送分支 / 审前自检。"""
    if diff_range:
        args, ref = ["git", "-C", repo_dir, "diff", diff_range], f"local:{diff_range}"
    elif staged:
        args, ref = ["git", "-C", repo_dir, "diff", "--staged"], "local:staged"
    else:
        args, ref = ["git", "-C", repo_dir, "diff"], "local:worktree"
    try:
        diff = runner(args)
    except subprocess.CalledProcessError as exc:
        raise PRFetchError(f"git diff 失败:{getattr(exc, 'stderr', '') or exc}") from exc
    if not diff.strip():
        raise PRFetchError("没有检测到改动(本地 diff 为空)。试试 --staged 或 --range main...HEAD。")
    return PRData(pr_ref=ref, title=title or "(本地改动)", body=body, diff=diff)
