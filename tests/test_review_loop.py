from reviewpilot.review_loop import run_review_loop
from reviewpilot.models import FindingKind


class _FakeWS:
    def __init__(self):
        self.reads = []
        self.searches = []

    def read_file(self, path, start=1, end=None):
        self.reads.append(path)
        return f"内容 of {path}"

    def search(self, query):
        self.searches.append(query)
        return f"命中: {query}"


def _tool_call(cid, name, args_json="{}"):
    return {"id": cid, "type": "function",
            "function": {"name": name, "arguments": args_json}}


def test_loop_gathers_via_tools_then_synthesizes_findings():
    ws = _FakeWS()
    calls_seq = [
        # 第1步:模型调 read_file + search 取证
        {"content": "", "calls": [
            {"id": "1", "name": "read_file", "args": {"path": "auth.py", "start": 1}},
            {"id": "2", "name": "search", "args": {"query": "login"}},
        ], "assistant_msg": {"role": "assistant", "content": "",
                             "tool_calls": [_tool_call("1", "read_file"), _tool_call("2", "search")]}},
        # 第2步:不再调工具 → 结束取证
        {"content": "", "calls": [], "assistant_msg": {"role": "assistant", "content": ""}},
    ]

    def chat_tools(messages, tools):
        return calls_seq.pop(0)

    chat = lambda messages: '[{"kind":"risk","title":"调用方未处理新异常","file":"auth.py","evidence":"auth.py:1"}]'

    findings, trace = run_review_loop("diff", "t", "b", None, ws, chat_tools, chat, max_steps=6)

    assert ws.reads == ["auth.py"] and ws.searches == ["login"]   # 真的去取证了
    assert [t["tool"] for t in trace] == ["read_file", "search"]  # 有 trace
    assert findings and findings[0].kind == FindingKind.RISK      # 最终合成出 finding


def test_loop_stops_at_max_steps():
    ws = _FakeWS()

    def chat_tools(messages, tools):  # 永远要调工具
        return {"content": "", "calls": [{"id": "x", "name": "search", "args": {"query": "q"}}],
                "assistant_msg": {"role": "assistant", "content": "",
                                  "tool_calls": [_tool_call("x", "search")]}}

    chat = lambda messages: "[]"
    _findings, trace = run_review_loop("d", "t", "b", None, ws, chat_tools, chat, max_steps=3)
    assert len(trace) == 3   # 限步数:最多 3 步
