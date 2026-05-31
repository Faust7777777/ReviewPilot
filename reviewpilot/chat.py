"""多轮对话式评审会话。

reviewer 不是许愿机:出了 briefing 后,开发者可以追问"第2条为什么"、反驳"这是故意的"。
ChatSession 维护消息历史,逐轮把完整上下文交给 LLM。llm 为注入式(接收 messages 列表),
便于测试与切换 provider。
"""
from reviewpilot.prompts import load as load_prompt

_SYSTEM = load_prompt("CHAT")  # 评审员提示外置在 reviewpilot/prompts/reviewer.md


class ChatSession:
    def __init__(self, llm, diff, title, body, issue, briefing_text):
        self.llm = llm
        system = _SYSTEM.format(title=title, body=body, issue=issue or "(无)",
                                diff=diff, briefing=briefing_text)
        self.messages: list[dict] = [{"role": "system", "content": system}]

    @classmethod
    def from_state(cls, llm, diff, title, body, issue, briefing_text, messages):
        session = cls(llm, diff, title, body, issue, briefing_text)
        session.messages = list(messages)
        return session

    def ask(self, user_msg: str) -> str:
        self.messages.append({"role": "user", "content": user_msg})
        reply = self.llm(self.messages)
        self.messages.append({"role": "assistant", "content": reply})
        return reply
