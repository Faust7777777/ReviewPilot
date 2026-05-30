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
        meta = json.loads(runner(["gh", "pr", "view", url, "--json", "title,body"]))
        diff = runner(["gh", "pr", "diff", url])
    except subprocess.CalledProcessError as exc:
        raise PRFetchError(_classify_gh_error(getattr(exc, "stderr", "") or "")) from exc
    return PRData(pr_ref=pr_ref, title=meta.get("title", ""),
                  body=meta.get("body", ""), diff=diff)


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
