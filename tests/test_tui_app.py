import asyncio

from reviewpilot.tui_app import ReviewPilotApp
from reviewpilot.chat import ChatSession
from reviewpilot.prfetch import PRData


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


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

    app = ReviewPilotApp(resolve_pr, analyze_fn)

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

    _run(scenario())
    assert progress_seen == ["local:worktree"]
    assert app._session is session
    assert session.messages[1]["content"] == "为什么有风险?"
    assert session.messages[-1]["content"] == "因为 a.py:1 改了减号"
