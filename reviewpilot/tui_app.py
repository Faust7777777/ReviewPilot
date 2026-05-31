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
from textual.widgets import Footer, Header, Input, Markdown, Static

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
    Markdown, Static { margin: 0 0 1 0; padding: 0 1; }
    .msg-user { background: $primary 12%; border-left: thick $primary; }
    .msg-thinking { color: $text-muted; border-left: thick $warning 60%; }
    .msg-final { border-left: thick $success; }
    """
    BINDINGS = [("escape", "quit", "退出"), ("ctrl+c", "quit", "退出")]

    def __init__(self, services, analyze_fn, initial=None):
        """services:目标解析能力(interpret/pr_data/local_data/list_prs/repo_latest);
        analyze_fn(pr, on_progress)->(briefing_text, session)。"""
        super().__init__()
        self._services = services
        self._analyze_fn = analyze_fn
        self._initial = initial
        self._pending = None  # 待用户回复的状态:pick(选PR)/ confirm(y-n)
        self._session = None
        self._pr = None
        self._briefing_text = None
        self._saved_session_id = None
        self._last_persist_error = None
        self._persistence_disabled = False
        self._busy = False
        self.transcript: list[str] = []  # 渲染过的消息文本(便于测试/检索)

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="log")
        yield Input(
            placeholder="粘贴 GitHub PR 链接,或输入 local / local main...HEAD", id="ask"
        )
        yield Footer()

    async def on_mount(self) -> None:
        lines = [
            "欢迎 👋 粘贴一个 **GitHub PR 链接**,或输入 `local`"
            "(也可 `local main...HEAD` / `local --staged`)评审本地改动。",
        ]
        pre = self._preflight()
        if pre:
            lines.append(f"\n⚠️  {pre}")
            lines.append(
                "  `/key` 设 API key | `/auth` 查 gh 登录 | `/model` 切模型 | `/help` 全部命令"
            )
        await self._say("\n\n".join(lines))
        self.query_one("#ask", Input).focus()
        if self._initial:
            await self._user(self._initial)
            self._resolve(self._initial)

    # —— 三类消息 ——
    async def _mount(self, label: str, text: str, css: str) -> None:
        self.transcript.append(f"{label}\n{text}")
        log = self.query_one("#log", VerticalScroll)
        content = f"**{label}**\n\n{text}"
        # Textual Markdown can deadlock under run_test while mounting nested widgets.
        # The real TUI keeps Markdown/link behavior; headless tests use plain Static.
        widget = (
            Static(content, classes=css)
            if self.is_headless
            else Markdown(content, classes=css, open_links=False)
        )
        await log.mount(widget)
        log.scroll_end(animate=False)

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        # 不打开浏览器,改为把链接填进输入框:点 PR 链接 → 回车即评审
        inp = self.query_one("#ask", Input)
        inp.value = event.href
        inp.focus()

    async def _user(self, text: str) -> None:  # 用户消息
        await self._mount("你", text, "msg-user")

    async def _think(self, text: str) -> None:  # 思考 / 进度
        await self._mount("分析中", f"_{text}_", "msg-thinking")

    async def _say(self, text: str) -> None:  # 最终回复
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
        if self._pending is not None:
            self._resume_pending(text)
        elif self._session is None:
            self._resolve(text)
        else:
            self._answer(text)

    def _commands(self):
        return {
            "/help": ("列出所有命令及一句话说明。", self._cmd_help),
            "/model": ("显示/切换 analyze/chat 模型。", self._cmd_model),
            "/key": ("显示/设置 API key(按 provider 存进环境变量)。", self._cmd_key),
            "/auth": ("检查 gh 登录状态并引导认证。", self._cmd_auth),
            "/clear": ("清空对话区,保留当前会话。", self._cmd_clear),
            "/reset": ("清空当前会话与 PR,重新等待输入。", self._cmd_reset),
            "/files": ("列出当前 PR 改动文件。", self._cmd_files),
            "/diff": ("展示全部 diff,或指定文件 diff。", self._cmd_diff),
            "/context": (
                "显示当前 PR、模型、key/auth 状态和 diff 概况。",
                self._cmd_context,
            ),
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
        lines = [
            f"- `{name}`: {desc}" for name, (desc, _handler) in self._commands().items()
        ]
        await self._say("\n".join(lines))

    async def _cmd_model(self, args: list[str]) -> None:
        if not args:
            await self._say(
                f"analyze: `{resolve_model('analyze')}`\n\n"
                f"chat: `{resolve_model('chat')}`"
            )
            return
        if len(args) != 2 or args[0] not in {"chat", "analyze"}:
            await self._say(
                "用法:`/model` 或 `/model chat <model>` / `/model analyze <model>`"
            )
            return
        stage, model = args
        env_name = f"RP_MODEL_{stage.upper()}"
        os.environ[env_name] = model
        note = (
            "analyze 切换不会自动重跑当前 briefing。"
            if stage == "analyze"
            else "后续追问将使用新 chat 模型。"
        )
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
        key_status = self._key_status()
        auth_status = self._gh_auth_summary()
        await self._say(
            f"pr_ref: `{pr_ref}`\n\n"
            f"analyze: `{resolve_model('analyze')}`\n\n"
            f"chat: `{resolve_model('chat')}`\n\n"
            f"对话轮数: `{len(messages) // 2}`\n\n"
            f"diff 字符数: `{diff_len}`\n\n"
            f"文件数: `{file_count}`\n\n"
            f"API key: {key_status}\n\n"
            f"gh: {auth_status}"
        )

    @staticmethod
    def _key_status() -> str:
        providers = {
            "DEEPSEEK_API_KEY": "deepseek",
            "OPENAI_API_KEY": "openai",
            "ANTHROPIC_API_KEY": "anthropic",
        }
        parts = []
        for env, name in providers.items():
            val = os.environ.get(env, "")
            if val:
                masked = val[:8] + "…" + val[-4:] if len(val) > 12 else "***"
                parts.append(f"`{name}` ✅ ({masked})")
            else:
                parts.append(f"`{name}` ❌")
        return "  ".join(parts)

    @staticmethod
    def _gh_auth_summary() -> str:
        import subprocess

        try:
            out = subprocess.run(
                ["gh", "auth", "status"], capture_output=True, text=True, timeout=5
            )
            return (
                "✅ 已登录"
                if out.returncode == 0
                else f"❌ ({out.stderr.strip()[:60]})"
            )
        except Exception:
            return "❓ (gh 未安装或不可用)"

    def _preflight(self) -> str:
        issues = []
        if (
            not os.environ.get("DEEPSEEK_API_KEY")
            and not os.environ.get("OPENAI_API_KEY")
            and not os.environ.get("ANTHROPIC_API_KEY")
        ):
            issues.append("未检测到 API key(`/key` 设置)")
        import subprocess

        try:
            if (
                subprocess.run(
                    ["gh", "auth", "status"], capture_output=True, timeout=5
                ).returncode
                != 0
            ):
                issues.append("gh 未登录(`/auth` 引导)")
        except Exception:
            issues.append("gh 未检测到(`/auth` 引导)")
        return "; ".join(issues) if issues else ""

    async def _cmd_key(self, args: list[str]) -> None:
        known = {
            "deepseek": "DEEPSEEK_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        if not args:
            await self._say(
                f"当前 key 状态:\n\n{self._key_status()}\n\n设置:`/key deepseek sk-xxx`"
            )
            return
        if len(args) == 2 and args[0] in known:
            os.environ[known[args[0]]] = args[1]
            await self._say(f"已设置 `{args[0]}` API key。以 `{args[1][:8]}…` 开头。")
        elif len(args) == 1 and args[0] in known:
            os.environ[known[args[0]]] = ""
            await self._say(f"已清除 `{args[0]}` API key。")
        else:
            await self._say(
                f"用法:`/key` 或 `/key deepseek sk-xxx`(provider:{' '.join(known)})"
            )

    async def _cmd_auth(self, args: list[str]) -> None:
        import asyncio, subprocess

        await self._say(self._gh_auth_summary())
        try:
            proc = await asyncio.create_subprocess_exec(
                "gh",
                "auth",
                "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                msg = stderr.decode().strip()[:200] if stderr else ""
                await self._say(
                    f"gh 认证状态异常:\n\n```\n{msg}\n```\n\n"
                    "请在终端运行 `gh auth login` 完成 GitHub 登录后回来。"
                )
        except Exception:
            await self._say("未检测到 gh CLI。安装:https://cli.github.com")

    async def _cmd_resume(self, args: list[str]) -> None:
        if not args:
            rows = list_sessions()
            if not rows:
                await self._say("暂无已保存会话。")
                return
            await self._say(
                "\n".join(
                    f"- `{row['id']}` {row['pr_ref']} {row['created_at']}"
                    for row in rows
                )
            )
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

    async def _save_current_session(self, messages: list[dict] | None = None) -> None:
        if (
            self._persistence_disabled
            or self._pr is None
            or self._session is None
            or self._briefing_text is None
        ):
            return
        messages = messages if messages is not None else self._session.messages
        try:
            self._saved_session_id = await asyncio.to_thread(
                save_session,
                self._pr,
                self._briefing_text,
                messages,
                session_id=self._saved_session_id,
            )
            self._last_persist_error = None
        except Exception as exc:
            self._last_persist_error = str(exc)
            self._persistence_disabled = True

    @work(exclusive=True)
    async def _resolve(self, text: str) -> None:
        """解析输入意图:pr/local 直接分析;repo 列 PR 选;模糊则 y/n 确认。"""
        self._set_busy(True, "识别中…")
        try:
            target = await asyncio.to_thread(self._services.interpret, text)
        except Exception as exc:
            await self._say(f"识别失败:{exc}")
            self._set_busy(False, "粘贴 PR / repo 链接,或 local")
            return
        if target.kind == "pr":
            await self._fetch_and_analyze(lambda: self._services.pr_data(target.value))
        elif target.kind == "local":
            await self._fetch_and_analyze(
                lambda: self._services.local_data(target.value)
            )
        elif target.kind == "repo":
            await self._enter_repo(target.value)
        elif target.kind == "fuzzy":
            await self._resolve_react(target.value or text)
        else:  # unknown
            await self._say(
                "无法识别。请给 PR 链接、`owner/repo#N`、repo 链接,或 `local`。"
            )
            self._set_busy(False, "粘贴 PR / repo 链接,或 local")

    async def _resolve_react(self, text: str) -> None:
        """ReAct 仓库发现:LLM 用工具探索 GitHub → 验证 → 确认对话(mini chat)。"""
        await self._think("探索 GitHub…")
        try:
            target = await asyncio.to_thread(self._services.resolve_with_tools, text)
        except Exception as exc:
            await self._say(f"探索失败:{exc}")
            self._set_busy(False, "换个关键词,或贴链接")
            return
        if target.kind != "repo" or not target.value:
            await self._say("没找到匹配的仓库。换个关键词,或直接贴 PR/repo 链接。")
            self._set_busy(False, "换个关键词,或贴链接")
            return
        # 验证仓库存在并拿描述
        repo = target.value
        owner, _, repo_name = repo.partition("/")
        info = await asyncio.to_thread(self._services.repo_exists, owner, repo_name)
        desc = (info or {}).get("description", "")
        self._pending = {"kind": "confirm_repo", "repo": repo, "desc": desc}
        hint = f" — {desc}" if desc else ""
        await self._say(
            f'找到 `{repo}`{hint}\n\n是这个吗? 输 y 确认 / n 重新搜 / 或追问(如"这讲了啥")。'
        )
        self._set_busy(False, "y 确认 / n 否 / 追问")

    async def _enter_repo(self, repo: str) -> None:
        await self._think(f"列出 {repo} 的 open PR…")
        try:
            prs = await asyncio.to_thread(self._services.list_prs, repo)
        except Exception as exc:
            await self._say(f"列出 PR 失败:{exc}")
            self._set_busy(False, "换一个链接,或输入 local")
            return
        if not prs:
            await self._think(f"{repo} 无 open PR,改为分析默认分支最新改动…")
            await self._fetch_and_analyze(lambda: self._services.repo_latest(repo))
            return
        lines = [
            f"{i}. #{pr['number']} {pr['title']}"
            + (f" — {pr['author']}" if pr.get("author") else "")
            for i, pr in enumerate(prs, 1)
        ]
        self._pending = {"kind": "pick", "repo": repo, "prs": prs}
        await self._say(
            f"`{repo}` 的 open PR:\n\n"
            + "\n".join(lines)
            + "\n\n输入编号选择,或直接贴别的链接。"
        )
        self._set_busy(False, "输入编号选择 PR")

    async def _fetch_and_analyze(self, fetch_callable) -> None:
        self._set_busy(True, "分析中…")

        def progress(msg):  # 后台线程 → UI 进度
            self.call_from_thread(self._think, msg)

        try:
            pr = await asyncio.to_thread(fetch_callable)
            await self._think(f"已获取 {pr.pr_ref},开始分析…")
            briefing_text, session = await asyncio.to_thread(
                self._analyze_fn, pr, progress
            )
        except Exception as exc:
            await self._say(f"分析失败:{exc}")
            self._set_busy(False, "换一个链接,或输入 local")
            return
        self._pr = pr
        self._briefing_text = briefing_text
        self._session = session
        await self._save_current_session()
        await self._say(briefing_text)
        self._set_busy(False, "追问 / 反驳…(Esc 退出)")

    @work(exclusive=True)
    async def _resume_pending(self, text: str) -> None:
        pending = self._pending
        self._pending = None
        if pending["kind"] == "confirm_repo":
            ans = text.strip().lower()
            if ans in ("y", "yes"):
                await self._enter_repo(pending["repo"])
                return
            if ans in ("n", "no"):
                await self._say("请换个描述重新搜索,或直接贴 PR/repo 链接。")
                self._set_busy(False, "换个关键词,或贴链接")
                return
            # 追问:chat LLM + repo_readme 工具,让它真去看仓库
            self._pending = pending
            self._set_busy(True, "了解中…")
            try:
                from reviewpilot.llm import chat_tools, chat

                repo = pending["repo"]
                owner, _, repo_name = repo.partition("/")
                desc = pending.get("desc", "")
                confirm_tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": "repo_readme",
                            "description": "读取仓库 README 文件内容,了解仓库用途、技术栈、使用方法。",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "owner": {"type": "string"},
                                    "repo": {"type": "string"},
                                },
                                "required": ["owner", "repo"],
                            },
                        },
                    }
                ]
                messages = [
                    {
                        "role": "system",
                        "content": f"用户正在确认仓库 `{repo}`。描述:'{desc}'。"
                        "回答用户对仓库的问题;描述不够时可调 repo_readme 看 README。"
                        "不要催问是否确认,只回答问题(≤150字)。",
                    },
                    {"role": "user", "content": text.strip()},
                ]
                out = await asyncio.to_thread(
                    chat_tools, messages, confirm_tools, stage="chat"
                )
                calls = out["calls"]
                if calls:
                    messages.append(out["assistant_msg"])
                    for c in calls:
                        if c["name"] == "repo_readme":
                            a = c["args"]
                            raw = await asyncio.to_thread(
                                self._services.repo_readme,
                                a.get("owner", owner),
                                a.get("repo", repo_name),
                            )
                            content = raw if raw else "(该仓库没有 README)"
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": c["id"],
                                    "content": content[:2000],
                                }
                            )
                    reply = await asyncio.to_thread(chat, messages, stage="chat")
                else:
                    reply = out["content"]
                await self._say(reply)
            except Exception as exc:
                await self._say(f"回答失败:{exc}")
            self._set_busy(False, "y 确认 / n 否 / 追问")
            return
        # pick (PR)
        prs, repo = pending["prs"], pending["repo"]
        sel = text.strip().lstrip("#")
        chosen = None
        if sel.isdigit():
            n = int(sel)
            if 1 <= n <= len(prs):
                chosen = prs[n - 1]
            else:
                chosen = next((p for p in prs if p["number"] == n), None)
        if chosen is None:
            self._pending = pending
            await self._say("无效编号,请重新输入,或直接贴链接。")
            self._set_busy(False, "输入编号选择 PR")
            return
        url = f"https://github.com/{repo}/pull/{chosen['number']}"
        await self._fetch_and_analyze(lambda: self._services.pr_data(url))

    @work
    async def _answer(self, question: str) -> None:
        self._set_busy(True, "思考中…")
        try:
            await self._think("正在依据已审 diff 作答…")
            messages = list(self._session.messages)
            messages.append({"role": "user", "content": question})
            reply = await asyncio.to_thread(self._session.llm, messages)
            messages.append({"role": "assistant", "content": reply})
            await self._save_current_session(messages)
            await self._say(reply)
            self._session.messages = messages
        finally:
            self._set_busy(False, "追问 / 反驳…(Esc 退出)")
