"""全屏 TUI(textual):上方滚动对话区 + 底部输入框 + Header/Footer。

界面立刻启动,briefing 在后台线程生成(避免"卡在分析中进不去");
LLM 调用全程走线程不阻塞 UI。复用 ChatSession,核心逻辑不变。
"""
import asyncio

from textual import work
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

    def __init__(self, prepare):
        """prepare() -> (briefing_text, session),在后台线程执行(会调 LLM)。"""
        super().__init__()
        self._prepare = prepare
        self._session = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="log")
        yield Input(placeholder="正在分析,请稍候…", id="ask", disabled=True)
        yield Footer()

    async def on_mount(self) -> None:
        await self._write("ReviewPilot", "_正在分析 PR…_")
        self._load()

    @work(exclusive=True)
    async def _load(self) -> None:
        try:
            briefing_text, session = await asyncio.to_thread(self._prepare)
        except Exception as exc:  # 分析失败显式提示,不卡死
            await self._write("ReviewPilot", f"分析失败:{exc}")
            return
        self._session = session
        await self._write("ReviewPilot", briefing_text)
        inp = self.query_one("#ask", Input)
        inp.placeholder = "追问 / 反驳…(Esc 退出)"
        inp.disabled = False
        inp.focus()

    async def _write(self, who: str, text: str) -> None:
        log = self.query_one("#log", VerticalScroll)
        await log.mount(Markdown(f"**{who}**\n\n{text}"))
        log.scroll_end(animate=False)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._session is None:
            return
        question = event.value.strip()
        event.input.value = ""
        if not question:
            return
        await self._write("你", question)
        reply = await asyncio.to_thread(self._session.ask, question)
        await self._write("ReviewPilot", reply)
