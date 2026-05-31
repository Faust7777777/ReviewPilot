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
    # 不让 LLM"编"仓库;只抽取联网搜索线索(用户名 + 关键词),交给 gh search 找真实仓库
    prompt = (
        "用户想找一个 GitHub 仓库来评审,但只记得大概(用户名 / 关键词 / 内容描述)。"
        '请抽取用于联网搜索的线索,只输出 JSON:{"owner": <GitHub 用户名,没有就空字符串>, '
        '"query": <搜索关键词,通常是仓库名或内容词>}。'
        '完全无法判断就输出 {"owner":"","query":""}。只输出 JSON,不要解释。\n输入:' + s
    )
    data = _parse_json_obj(llm(prompt) or "")
    owner = str(data.get("owner") or "").strip()
    query = str(data.get("query") or "").strip()
    if not owner and not query:
        return Target("unknown")
    return Target("search", value=query, candidate=owner)


def _parse_json_obj(text: str) -> dict:
    """从 LLM 输出里宽容地取第一个 JSON 对象({...});失败返回 {}。"""
    import json
    import re
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}
