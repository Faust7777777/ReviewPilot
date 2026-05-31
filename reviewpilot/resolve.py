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
    prompt = (
        "用户想评审一个 GitHub 仓库,但输入可能不规范(用空格代替斜杠、大小写/拼写不准、"
        "只给项目名)。请尽量解析成最可能的 owner/repo,例如:"
        "'facebook react'->facebook/react;'fausttttttt yuyt'->fausttttttt/yuyt;"
        "'react'->facebook/react。完全无法判断才返回 NONE。"
        "只输出 owner/repo 或 NONE,不要任何解释或标点。\n用户输入:" + s
    )
    candidate = (llm(prompt) or "").strip().strip("`").strip()
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
