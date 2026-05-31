import json

from reviewpilot.prfetch import PRFetchError, is_pr_url, parse_repo
from reviewpilot.prompts import load as load_prompt


class Target:
    """轻量值对象:kind + value。不再使用 frozen dataclass(方便工具侧动态构造)。"""

    def __init__(self, kind: str, value: str | None = None):
        self.kind = kind  # "pr", "local", "repo", "fuzzy", "unknown"
        self.value = value

    def __eq__(self, other):
        if not isinstance(other, Target):
            return NotImplemented
        return self.kind == other.kind and self.value == other.value

    def __repr__(self):
        return f"Target(kind={self.kind!r}, value={self.value!r})"


def interpret_target(text: str) -> Target:
    """确定性快速解析:PR 链接 / local / owner/repo。剩下都走 ReAct 探索。"""
    s = (text or "").strip()
    if s.startswith("local"):
        return Target("local", value=s)
    if is_pr_url(s):
        return Target("pr", value=s)
    try:
        return Target("repo", value=parse_repo(s))
    except PRFetchError:
        pass
    return Target("fuzzy", value=s)


_RESOLVE_SYSTEM = load_prompt("DISCOVERY")

_RESOLVE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_repos",
            "description": "列出某 GitHub 用户/组织的公开仓库(含名称、描述、语言)。优先用此工具了解用户有哪些仓库,从描述匹配意图。",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "GitHub 用户名或组织名"},
                },
                "required": ["owner"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_repos",
            "description": "在 GitHub 上搜索仓库(按名称/描述匹配)。用于 list_repos 找不到或用户没给用户名时兜底。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["query"],
            },
        },
    },
]


def resolve_with_tools(text: str, tools: dict, chat_tools_fn) -> Target:
    """ReAct 仓库发现循环:LLM 用工具探索 GitHub,找到正确仓库后返回 Target。"""
    messages = [
        {"role": "system", "content": _RESOLVE_SYSTEM},
        {"role": "user", "content": text},
    ]
    for _ in range(5):
        out = chat_tools_fn(messages, _RESOLVE_TOOLS)
        calls = out["calls"]
        if not calls:
            data = _parse_json_obj(out["content"])
            repo = str(data.get("repo", "")).strip()
            if repo and "/" in repo:
                return Target("repo", value=repo)
            return Target("unknown")
        messages.append(out["assistant_msg"])
        for c in calls:
            fn = tools.get(c["name"])
            if fn:
                # ReAct 精髓:工具失败也要作为 observation 喂回模型,让它自救(改调
                # 另一个工具),而不是让异常冒泡中止整个循环。任何工具异常
                # (PRFetchError、LLM 传错/多余参数导致的 TypeError 等)都转成
                # 错误观察字符串。
                try:
                    result = fn(**c["args"])
                    content = json.dumps(result, ensure_ascii=False)
                except Exception as exc:  # noqa: BLE001 — 任何失败都喂回模型
                    content = json.dumps({"error": str(exc)}, ensure_ascii=False)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": c["id"],
                        "content": content,
                    }
                )
            else:
                messages.append(
                    {"role": "tool", "tool_call_id": c["id"], "content": "未知工具"}
                )
    return Target("unknown")


def _parse_json_obj(text: str) -> dict:
    import re

    text = text or ""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}
