from dataclasses import dataclass

from reviewpilot.prfetch import PRFetchError, is_pr_url, parse_repo


@dataclass(frozen=True)
class Target:
    kind: str
    value: str | None = None
    candidate: str | None = None
    question: str | None = None


def interpret_target(text: str, llm=None) -> Target:
    s = (text or "").strip()
    if s.startswith("local"):
        return Target("local", value=s)
    if is_pr_url(s):
        return Target("pr", value=s)
    try:
        return Target("repo", value=parse_repo(s))
    except PRFetchError:
        pass

    if llm is None:
        return Target("unknown")
    candidate = (llm(f"从用户输入中识别 GitHub 仓库,只返回 owner/repo 或 NONE。用户输入:{s}") or "").strip()
    if not candidate or candidate.upper() == "NONE":
        return Target("unknown")
    try:
        repo = parse_repo(candidate)
    except PRFetchError:
        return Target("unknown")
    return Target(
        "confirm",
        candidate=repo,
        question=f"你是想评审 `{repo}` 这个仓库吗?(y/n)",
    )
