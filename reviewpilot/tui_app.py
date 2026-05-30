"""全屏 TUI(textual):上方滚动对话区 + 底部输入框 + Header/Footer。

复用 ChatSession;LLM 调用走线程不阻塞 UI。核心会话逻辑不变,这里只是界面层。
"""
import asyncio

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Input, Markdown


class ReviewPilotApp(App):
    TITLE = "ReviewPilot"
    SUB_TITLE = "PR 评审 · 多轮追问"
    CSS = """
    #log { height: 1fr; padding: 0 1; }
    #ask { dock: bottom; }
    Markdown { margin: 0 0 1 0; }
    """
    BINDINGS = [("escape", "quit", "退出"), ("ctrl+c", "quit", "退出")]

    def __init__(self, briefing_text: str, session):
        super().__init__()
        self._briefing_text = briefing_text
        self._session = session

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="log")
        yield Input(placeholder="追问 / 反驳…(Esc 退出)", id="ask")
        yield Footer()

    async def on_mount(self) -> None:
        await self._write("ReviewPilot", self._briefing_text)
        self.query_one("#ask", Input).focus()

    async def _write(self, who: str, text: str) -> None:
        log = self.query_one("#log", VerticalScroll)
        await log.mount(Markdown(f"**{who}**\n\n{text}"))
        log.scroll_end(animate=False)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        event.input.value = ""
        if not question:
            return
        await self._write("你", question)
        await self._write("ReviewPilot", "_思考中…_")
        reply = await asyncio.to_thread(self._session.ask, question)
        # 替换"思考中"为真实回复:简单做法是直接再追加一条
        await self._write("ReviewPilot", reply)
