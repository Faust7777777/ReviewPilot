"""全屏 TUI(textual):先进界面 → 在里面贴 PR → 实时看分析过程 → 出 briefing → 多轮追问。

界面立刻启动;拉取 PR、分析、追问全部走后台线程,进度实时回报到对话区。
复用 resolve_pr / analyze_fn / ChatSession,核心逻辑不在这里。
"""
import asyncio

from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Input, Markdown


class ReviewPilotApp(App):
    TITLE = "ReviewPilot"
    SUB_TITLE = "贴 PR 链接,或输入 local 评审本地改动"
    CSS = """
    #log { height: 1fr; padding: 0 1; }
    #ask { dock: bottom; }
    Markdown { margin: 0 0 1 0; }
    """
    BINDINGS = [("escape", "quit", "退出"), ("ctrl+c", "quit", "退出")]

    def __init__(self, resolve_pr, analyze_fn, initial=None):
        """resolve_pr(text)->PRData;analyze_fn(pr, on_progress)->(briefing_text, session)。"""
        super().__init__()
        self._resolve_pr = resolve_pr
        self._analyze_fn = analyze_fn
        self._initial = initial
        self._session = None
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="log")
        yield Input(placeholder="粘贴 GitHub PR 链接,或输入 local / local main...HEAD", id="ask")
        yield Footer()

    async def on_mount(self) -> None:
        await self._write(
            "ReviewPilot",
            "欢迎 👋 粘贴一个 **GitHub PR 链接**,或输入 `local`"
            "(也可 `local main...HEAD` / `local --staged`)评审本地改动。",
        )
        self.query_one("#ask", Input).focus()
        if self._initial:
            await self._write("你", self._initial)
            self._analyze(self._initial)

    async def _write(self, who: str, text: str) -> None:
        log = self.query_one("#log", VerticalScroll)
        await log.mount(Markdown(f"**{who}**\n\n{text}"))
        log.scroll_end(animate=False)

    def _set_busy(self, busy: bool, placeholder: str) -> None:
        self._busy = busy
        inp = self.query_one("#ask", Input)
        inp.disabled = busy
        inp.placeholder = placeholder
        if not busy:
            inp.focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._busy:
            return
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        await self._write("你", text)
        if self._session is None:
            self._analyze(text)
        else:
            self._answer(text)

    @work(exclusive=True)
    async def _analyze(self, text: str) -> None:
        self._set_busy(True, "分析中…")

        def progress(msg):  # 从后台线程把进度回报到 UI
            self.call_from_thread(self._write, "ReviewPilot", f"_{msg}_")

        try:
            pr = await asyncio.to_thread(self._resolve_pr, text)
            await self._write("ReviewPilot", f"已获取 `{pr.pr_ref}`,开始分析…")
            briefing_text, session = await asyncio.to_thread(self._analyze_fn, pr, progress)
        except Exception as exc:
            await self._write("ReviewPilot", f"分析失败:{exc}")
            self._set_busy(False, "换一个 PR 链接,或输入 local")
            return
        self._session = session
        await self._write("ReviewPilot", briefing_text)
        self._set_busy(False, "追问 / 反驳…(Esc 退出)")

    @work
    async def _answer(self, question: str) -> None:
        self._set_busy(True, "思考中…")
        try:
            reply = await asyncio.to_thread(self._session.ask, question)
            await self._write("ReviewPilot", reply)
        finally:
            self._set_busy(False, "追问 / 反驳…(Esc 退出)")
