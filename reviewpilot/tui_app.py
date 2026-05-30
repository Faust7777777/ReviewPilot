"""全屏 TUI(textual):先进界面 → 在里面贴 PR → 实时看分析过程 → 出 briefing → 多轮追问。

界面立刻启动;拉取 PR、分析、追问全部走后台线程,进度实时回报到对话区。
三类消息视觉区分:用户消息 / pilot 思考·进度 / pilot 最终回复。
"""
import asyncio
import os
import shlex
from functools import partial

from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Input, Markdown

from reviewpilot.chat import ChatSession
from reviewpilot.diffnorm import split_diff_by_file
from reviewpilot.llm import chat, resolve_model
from reviewpilot.prfetch import PRData
from reviewpilot.sessions_store import list_sessions, load_session, save_session


class ReviewPilotApp(App):
    TITLE = "ReviewPilot"
    SUB_TITLE = "贴 PR 链接,或输入 local 评审本地改动"
    CSS = """
    #log { height: 1fr; padding: 0 1; }
    #ask { dock: bottom; }
    Markdown { margin: 0 0 1 0; padding: 0 1; }
    .msg-user { background: $primary 12%; border-left: thick $primary; }
    .msg-thinking { color: $text-muted; border-left: thick $warning 60%; }
    .msg-final { border-left: thick $success; }
    """
    BINDINGS = [("escape", "quit", "退出"), ("ctrl+c", "quit", "退出")]

    def __init__(self, resolve_pr, analyze_fn, initial=None):
        """resolve_pr(text)->PRData;analyze_fn(pr, on_progress)->(briefing_text, session)。"""
        super().__init__()
        self._resolve_pr = resolve_pr
        self._analyze_fn = analyze_fn
        self._initial = initial
        self._session = None
        self._pr = None
        self._briefing_text = None
        self._saved_session_id = None
        self._last_persist_error = None
        self._persistence_disabled = False
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="log")
        yield Input(placeholder="粘贴 GitHub PR 链接,或输入 local / local main...HEAD", id="ask")
        yield Footer()

    async def on_mount(self) -> None:
        await self._say("欢迎 👋 粘贴一个 **GitHub PR 链接**,或输入 `local`"
                        "(也可 `local main...HEAD` / `local --staged`)评审本地改动。")
        self.query_one("#ask", Input).focus()
        if self._initial:
            await self._user(self._initial)
            self._analyze(self._initial)

    # —— 三类消息 ——
    async def _mount(self, label: str, text: str, css: str) -> None:
        log = self.query_one("#log", VerticalScroll)
        await log.mount(Markdown(f"**{label}**\n\n{text}", classes=css))
        log.scroll_end(animate=False)

    async def _user(self, text: str) -> None:       # 用户消息
        await self._mount("你", text, "msg-user")

    async def _think(self, text: str) -> None:      # 思考 / 进度
        await self._mount("分析中", f"_{text}_", "msg-thinking")

    async def _say(self, text: str) -> None:        # 最终回复
        await self._mount("ReviewPilot", text, "msg-final")

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
        if text.startswith("/"):
            await self._handle_command(text)
            return
        await self._user(text)
        if self._session is None:
            self._analyze(text)
        else:
            self._answer(text)

    def _commands(self):
        return {
            "/help": ("列出所有命令及一句话说明。", self._cmd_help),
            "/model": ("显示或切换 analyze/chat 模型。", self._cmd_model),
            "/clear": ("清空对话区,保留当前会话。", self._cmd_clear),
            "/reset": ("清空当前会话与 PR,重新等待输入。", self._cmd_reset),
            "/files": ("列出当前 PR 改动文件。", self._cmd_files),
            "/diff": ("展示全部 diff,或指定文件 diff。", self._cmd_diff),
            "/context": ("显示当前 PR、模型、轮数和 diff 概况。", self._cmd_context),
            "/resume": ("列出或恢复已保存会话。", self._cmd_resume),
            "/quit": ("退出 ReviewPilot。", self._cmd_quit),
        }

    async def _handle_command(self, text: str) -> None:
        try:
            parts = shlex.split(text)
        except ValueError:
            await self._say("命令解析失败,/help 查看")
            return
        if not parts:
            return
        command = parts[0]
        handler = self._commands().get(command)
        if handler is None:
            await self._say("未知命令,/help 查看")
            return
        try:
            await handler[1](parts[1:])
        except Exception as exc:
            await self._say(f"命令失败:{exc}")

    async def _cmd_help(self, args: list[str]) -> None:
        lines = [f"- `{name}`: {desc}" for name, (desc, _handler) in self._commands().items()]
        await self._say("\n".join(lines))

    async def _cmd_model(self, args: list[str]) -> None:
        if not args:
            await self._say(
                f"analyze: `{resolve_model('analyze')}`\n\n"
                f"chat: `{resolve_model('chat')}`"
            )
            return
        if len(args) != 2 or args[0] not in {"chat", "analyze"}:
            await self._say("用法:`/model` 或 `/model chat <model>` / `/model analyze <model>`")
            return
        stage, model = args
        env_name = f"RP_MODEL_{stage.upper()}"
        os.environ[env_name] = model
        note = "analyze 切换不会自动重跑当前 briefing。" if stage == "analyze" else "后续追问将使用新 chat 模型。"
        await self._say(f"已切换 {stage} 模型为 `{model}`。\n\n{note}")

    async def _cmd_clear(self, args: list[str]) -> None:
        log = self.query_one("#log", VerticalScroll)
        await log.remove_children()

    async def _cmd_reset(self, args: list[str]) -> None:
        self._session = None
        self._pr = None
        self._briefing_text = None
        self._saved_session_id = None
        self._last_persist_error = None
        self._persistence_disabled = False
        self._set_busy(False, "粘贴 GitHub PR 链接,或输入 local / local main...HEAD")
        await self._say("已重置。请重新贴 PR 链接,或输入 `local`。")

    def _diff_files(self) -> list[tuple[str, str]]:
        if self._pr is None:
            return []
        return split_diff_by_file(self._pr.diff)

    async def _cmd_files(self, args: list[str]) -> None:
        if self._pr is None:
            await self._say("请先贴 PR 或输入 `local` 完成分析。")
            return
        files = [name or "(未知文件)" for name, _diff in self._diff_files()]
        await self._say("\n".join(f"- `{name}`" for name in files) or "(无文件)")

    async def _cmd_diff(self, args: list[str]) -> None:
        if self._pr is None:
            await self._say("请先贴 PR 或输入 `local` 完成分析。")
            return
        if not args:
            await self._say(f"```diff\n{self._pr.diff}\n```")
            return
        wanted = args[0]
        for name, diff in self._diff_files():
            if name == wanted:
                await self._say(f"```diff\n{diff}\n```")
                return
        await self._say(f"未找到文件:`{wanted}`")

    async def _cmd_context(self, args: list[str]) -> None:
        pr_ref = self._pr.pr_ref if self._pr else "(无)"
        messages = self._session.messages if self._session else []
        diff_len = len(self._pr.diff) if self._pr else 0
        file_count = len(self._diff_files()) if self._pr else 0
        await self._say(
            f"pr_ref: `{pr_ref}`\n\n"
            f"analyze: `{resolve_model('analyze')}`\n\n"
            f"chat: `{resolve_model('chat')}`\n\n"
            f"对话轮数: `{len(messages) // 2}`\n\n"
            f"diff 字符数: `{diff_len}`\n\n"
            f"文件数: `{file_count}`"
        )

    async def _cmd_resume(self, args: list[str]) -> None:
        if not args:
            rows = list_sessions()
            if not rows:
                await self._say("暂无已保存会话。")
                return
            await self._say("\n".join(
                f"- `{row['id']}` {row['pr_ref']} {row['created_at']}" for row in rows
            ))
            return
        state = load_session(args[0])
        pr = PRData(
            pr_ref=state["pr_ref"],
            title=state.get("title", ""),
            body=state.get("body", ""),
            issue=state.get("issue"),
            diff=state.get("diff", ""),
        )
        briefing_text = state.get("briefing_text", "")
        session = ChatSession.from_state(
            partial(chat, stage="chat"),
            pr.diff,
            pr.title,
            pr.body,
            pr.issue,
            briefing_text,
            state.get("messages", []),
        )
        self._pr = pr
        self._briefing_text = briefing_text
        self._session = session
        self._saved_session_id = state.get("id") or args[0]
        self._set_busy(False, "追问 / 反驳…(Esc 退出)")
        await self._say(f"已恢复 `{pr.pr_ref}`。\n\n{briefing_text}")

    async def _cmd_quit(self, args: list[str]) -> None:
        self.exit()

    async def _save_current_session(self) -> None:
        if (
            self._persistence_disabled
            or self._pr is None
            or self._session is None
            or self._briefing_text is None
        ):
            return
        try:
            self._saved_session_id = await asyncio.to_thread(
                save_session,
                self._pr,
                self._briefing_text,
                self._session.messages,
                session_id=self._saved_session_id,
            )
            self._last_persist_error = None
        except Exception as exc:
            self._last_persist_error = str(exc)
            self._persistence_disabled = True

    @work(exclusive=True)
    async def _analyze(self, text: str) -> None:
        self._set_busy(True, "分析中…")

        def progress(msg):  # 后台线程 → UI 进度
            self.call_from_thread(self._think, msg)

        try:
            pr = await asyncio.to_thread(self._resolve_pr, text)
            await self._think(f"已获取 {pr.pr_ref},开始分析…")
            briefing_text, session = await asyncio.to_thread(self._analyze_fn, pr, progress)
        except Exception as exc:
            await self._say(f"分析失败:{exc}")
            self._set_busy(False, "换一个 PR 链接,或输入 local")
            return
        self._pr = pr
        self._briefing_text = briefing_text
        self._session = session
        await self._save_current_session()
        await self._say(briefing_text)
        self._set_busy(False, "追问 / 反驳…(Esc 退出)")

    @work
    async def _answer(self, question: str) -> None:
        self._set_busy(True, "思考中…")
        try:
            await self._think("正在依据已审 diff 作答…")
            reply = await asyncio.to_thread(self._session.ask, question)
            await self._save_current_session()
            await self._say(reply)
        finally:
            self._set_busy(False, "追问 / 反驳…(Esc 退出)")
