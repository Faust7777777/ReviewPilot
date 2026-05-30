"""多轮对话式评审会话。

reviewer 不是许愿机:出了 briefing 后,开发者可以追问"第2条为什么"、反驳"这是故意的"。
ChatSession 维护消息历史,逐轮把完整上下文交给 LLM。llm 为注入式(接收 messages 列表),
便于测试与切换 provider。
"""
_SYSTEM = """你是只读代码评审助手,正在就一个 PR 与开发者多轮对话。
你之前已产出初始 briefing(见下)。现在回答开发者的追问、解释你的判断依据、
接受合理的反驳并修正立场;业务正确性拿不准时老实说"需人工确认",不要编造。
只依据下面给出的 diff 与上下文,不臆测看不到的代码。

PR 声称(标题): {title}
PR 声称(描述): {body}
关联 issue: {issue}

diff:
{diff}

你的初始 briefing:
{briefing}
"""


class ChatSession:
    def __init__(self, llm, diff, title, body, issue, briefing_text):
        self.llm = llm
        system = _SYSTEM.format(title=title, body=body, issue=issue or "(无)",
                                diff=diff, briefing=briefing_text)
        self.messages: list[dict] = [{"role": "system", "content": system}]

    def ask(self, user_msg: str) -> str:
        self.messages.append({"role": "user", "content": user_msg})
        reply = self.llm(self.messages)
        self.messages.append({"role": "assistant", "content": reply})
        return reply
