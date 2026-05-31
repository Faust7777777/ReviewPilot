"""受限只读 Review Loop(ReAct):评审时模型按需调只读工具取证,再出 typed findings。

这是 harness 的"求解面":不再一次性塞 diff 让模型猜,而是让它 read_file/search 仓库上下文
(只读、限步数、全程可 trace),基于"diff + 读到的证据"产出结论。
"""
from reviewpilot.analyzer import parse_findings
from reviewpilot.models import Finding
from reviewpilot.prompts import load as load_prompt

_TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "读取仓库某文件的一段内容(只读)。用于查看被改函数的定义、调用方、配置、测试等。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "相对仓库根的文件路径"},
            "start": {"type": "integer", "description": "起始行(可选)"},
            "end": {"type": "integer", "description": "结束行(可选)"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "search",
        "description": "在仓库里全文搜索(只读),用于找符号定义、调用点、相关代码。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索词(符号名/字符串)"},
        }, "required": ["query"]},
    }},
]

_SYSTEM = load_prompt("SYSTEM")
_FINISH = load_prompt("FINISH")


def run_review_loop(diff, title, body, issue, workspace, chat_tools, chat,
                    max_steps: int = 6, on_progress=None) -> tuple[list[Finding], list[dict]]:
    """返回 (findings, trace)。chat_tools:带工具的一步对话;chat:无工具的最终合成。"""
    intent = f"标题:{title}\n描述:{body}\n关联 issue:{issue or '(无)'}"
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"PR 意图:\n{intent}\n\ndiff:\n{diff}\n\n"
                                     "可调用 read_file / search 取证;够了就停。"},
    ]
    trace: list[dict] = []
    for _ in range(max_steps):
        out = chat_tools(messages, _TOOLS)
        calls = out["calls"]
        if not calls:
            break
        messages.append(out["assistant_msg"])
        for c in calls:
            a = c["args"]
            if c["name"] == "read_file":
                res = workspace.read_file(a.get("path", ""), a.get("start", 1), a.get("end"))
                trace.append({"tool": "read_file", "args": a})
                if on_progress:
                    on_progress(f"读取 {a.get('path', '')}")
            elif c["name"] == "search":
                res = workspace.search(a.get("query", ""))
                trace.append({"tool": "search", "args": a})
                if on_progress:
                    on_progress(f"搜索 “{a.get('query', '')}”")
            else:
                res = "未知工具"
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": res[:4000]})
    messages.append({"role": "user", "content": _FINISH})
    return parse_findings(chat(messages)), trace
