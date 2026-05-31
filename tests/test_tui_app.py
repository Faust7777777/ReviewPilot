import asyncio

from reviewpilot.tui_app import ReviewPilotApp
from reviewpilot.chat import ChatSession
from reviewpilot.prfetch import PRData
from reviewpilot.resolve import Target


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        executor = getattr(loop, "_default_executor", None)
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
        loop.close()


class _StubServices:
    def __init__(self, resolve_pr):
        self._resolve_pr = resolve_pr

    def interpret(self, text):
        return Target("local", value=text.strip())

    def local_data(self, text):
        return self._resolve_pr(text)


def test_enter_then_give_pr_then_chat():
    session = ChatSession(lambda msgs: "因为 a.py:1 改了减号",
                          diff="d", title="t", body="b", issue=None, briefing_text="B")
    progress_seen = []

    def resolve_pr(text):
        assert text == "local"
        return PRData(pr_ref="local:worktree", title="t", body="", diff="d")

    def analyze_fn(pr, on_progress=None):
        if on_progress:
            on_progress("分析 a.py…")           # 进度实时回报
        progress_seen.append(pr.pr_ref)
        return f"BRIEF for {pr.pr_ref}", session

    app = ReviewPilotApp(_StubServices(resolve_pr), analyze_fn)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            # 先进界面,再在里面给 PR
            app.query_one("#ask").value = "local"
            await pilot.press("enter")
            for _ in range(200):
                if app._session is not None and not app.query_one("#ask").disabled:
                    break
                await pilot.pause(0.02)
            # 出 briefing 后继续追问
            app.query_one("#ask").value = "为什么有风险?"
            await pilot.press("enter")
            for _ in range(200):
                if len(session.messages) >= 3:
                    break
                await pilot.pause(0.02)
            # 三类视觉区分:用户气泡 / 思考进度 / 最终回复 用不同 css class
            assert app.query(".msg-user")
            assert app.query(".msg-thinking")
            assert app.query(".msg-final")

    _run(scenario())
    assert progress_seen == ["local:worktree"]
    assert app._session is session
    assert session.messages[1]["content"] == "为什么有风险?"
    assert session.messages[-1]["content"] == "因为 a.py:1 改了减号"


def _wait_run(app, scenario_body):
    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            await scenario_body(app, pilot)
    _run(scenario())


async def _wait(pilot, cond, n=200):
    for _ in range(n):
        if cond():
            return
        await pilot.pause(0.02)


def test_repo_link_lists_prs_then_pick():
    session = ChatSession(lambda m: "ok", diff="d", title="t", body="b",
                          issue=None, briefing_text="B")
    picked = {}

    class S:
        def interpret(self, text):
            return Target("repo", value="o/r")
        def list_prs(self, repo):
            return [{"number": 42, "title": "fix login", "author": "alice"},
                    {"number": 41, "title": "add tests", "author": "bob"}]
        def pr_data(self, ref):
            picked["ref"] = ref
            return PRData(pr_ref="o/r#42", title="fix login", body="", diff="d")

    app = ReviewPilotApp(S(), lambda pr, on_progress=None: ("BRIEF", session))

    async def body(app, pilot):
        app.query_one("#ask").value = "https://github.com/o/r"
        await pilot.press("enter")
        await _wait(pilot, lambda: app._pending is not None)
        assert "#42" in "\n".join(app.transcript)
        app.query_one("#ask").value = "1"
        await pilot.press("enter")
        await _wait(pilot, lambda: app._session is not None)

    _wait_run(app, body)
    assert picked["ref"] == "https://github.com/o/r/pull/42"
    assert app._session is session


def test_fuzzy_input_searches_repos_then_pick_lists_prs():
    session = ChatSession(lambda m: "ok", diff="d", title="t", body="b",
                          issue=None, briefing_text="B")

    class S:
        def interpret(self, text):
            return Target("search", value="yuyt", candidate="fausttttttt")
        def search_repos(self, query, owner=""):
            assert query == "yuyt" and owner == "fausttttttt"
            return [{"full_name": "fausttttttt/yuyt", "description": "demo repo"},
                    {"full_name": "other/yuyt", "description": ""}]
        def list_prs(self, repo):
            assert repo == "fausttttttt/yuyt"
            return [{"number": 1, "title": "x", "author": ""}]

    app = ReviewPilotApp(S(), lambda pr, on_progress=None: ("BRIEF", session))

    async def body(app, pilot):
        app.query_one("#ask").value = "fausttttttt yuyt"
        await pilot.press("enter")
        await _wait(pilot, lambda: app._pending and app._pending["kind"] == "pick_repo")
        assert "fausttttttt/yuyt" in "\n".join(app.transcript)   # 真实搜索候选
        app.query_one("#ask").value = "1"                        # 选第 1 个仓库
        await pilot.press("enter")
        await _wait(pilot, lambda: app._pending and app._pending["kind"] == "pick")

    _wait_run(app, body)
    assert "#1" in "\n".join(app.transcript)
