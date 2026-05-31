"""受限只读 Review Loop(ReAct):评审时模型按需调只读工具取证,再出 typed findings。

这是 harness 的"求解面":不再一次性塞 diff 让模型猜,而是让它 read_file/search 仓库上下文
(只读、限步数、全程可 trace),基于"diff + 读到的证据"产出结论。
"""

from reviewpilot.analyzer import parse_findings
from reviewpilot.models import Finding
from reviewpilot.prompts import load as load_prompt


def _hit_files(search_output: str) -> list[str]:
    """从 rg/grep 的 `path:line:content` 输出里抽出命中的文件路径(供 grounding)。"""
    files = []
    for ln in (search_output or "").splitlines():
        parts = ln.split(":", 2)
        if len(parts) >= 3 and parts[1].strip().isdigit() and parts[0].strip():
            files.append(parts[0].strip())
    return list(dict.fromkeys(files))


def grounded_read_files(trace) -> list[str]:
    """从 trace 提取"可作 grounding 的文件":成功读到的文件 + 搜索命中的文件。
    读失败(幻觉路径返回 not-found)的**不算**——这是护栏防幻觉的关键。"""
    files = []
    for t in trace or []:
        if t.get("tool") == "read_file" and t.get("ok"):
            p = (t.get("args") or {}).get("path", "")
            if p:
                files.append(p)
        elif t.get("tool") == "search":
            files.extend(t.get("hits", []))
    return list(dict.fromkeys(files))


_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取仓库某文件的一段内容(只读)。用于查看被改函数的定义、调用方、配置、测试等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对仓库根的文件路径"},
                    "start": {"type": "integer", "description": "起始行(可选)"},
                    "end": {"type": "integer", "description": "结束行(可选)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "在仓库里全文搜索(只读),用于找符号定义、调用点、相关代码。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索词(符号名/字符串)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_type",
            "description": "检测文件类型(file 命令)。用于分辨文本/二进制/压缩/可执行文件,不读内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对仓库根的文件路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hex_preview",
            "description": "文件前 N 字节 hex dump(xxd)。用于快速审视二进制/压缩文件的头部信息(魔数、格式),不解压、不执行。默认 256 字节。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对仓库根的文件路径"},
                    "max_bytes": {
                        "type": "integer",
                        "description": "最多返回多少字节(默认 256,上限 4096)",
                    },
                },
                "required": ["path"],
            },
        },
    },
]

_SYSTEM = load_prompt("SYSTEM")
_FINISH = load_prompt("FINISH")


def run_review_loop(
    diff,
    title,
    body,
    issue,
    workspace,
    chat_tools,
    chat,
    max_steps: int = 6,
    on_progress=None,
) -> tuple[list[Finding], list[dict]]:
    """返回 (findings, trace)。chat_tools:带工具的一步对话;chat:无工具的最终合成。"""
    intent = f"标题:{title}\n描述:{body}\n关联 issue:{issue or '(无)'}"
    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": f"PR 意图:\n{intent}\n\ndiff:\n{diff}\n\n"
            "可调用 read_file / search 取证;够了就停。",
        },
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
                path = a.get("path", "")
                res = workspace.read_file(path, a.get("start", 1), a.get("end"))
                # 仅"真实存在的文件"算 grounding:防"幻觉路径→读到 not-found→当证据"绕过护栏
                trace.append(
                    {"tool": "read_file", "args": a, "ok": workspace.exists(path)}
                )
                if on_progress:
                    on_progress(f"读取 {path}")
            elif c["name"] == "search":
                res = workspace.search(a.get("query", ""))
                trace.append({"tool": "search", "args": a, "hits": _hit_files(res)})
                if on_progress:
                    on_progress(f"搜索 “{a.get('query', '')}”")
            elif c["name"] == "file_type":
                res = workspace.file_type(a.get("path", ""))
                trace.append(
                    {
                        "tool": "file_type",
                        "args": a,
                        "ok": bool(res and not res.startswith("(")),
                    }
                )
                if on_progress:
                    on_progress(f"检测 {a.get('path', '')} 类型")
            elif c["name"] == "hex_preview":
                res = workspace.hex_preview(a.get("path", ""), a.get("max_bytes", 256))
                trace.append(
                    {
                        "tool": "hex_preview",
                        "args": a,
                        "ok": bool(res and not res.startswith("(")),
                    }
                )
                if on_progress:
                    on_progress(f"hex 预览 {a.get('path', '')}")
            else:
                res = "未知工具"
            messages.append(
                {"role": "tool", "tool_call_id": c["id"], "content": res[:4000]}
            )
    messages.append({"role": "user", "content": _FINISH})
    return parse_findings(chat(messages)), trace
