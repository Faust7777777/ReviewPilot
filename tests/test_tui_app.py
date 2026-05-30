import asyncio

from reviewpilot.tui_app import ReviewPilotApp
from reviewpilot.chat import ChatSession


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_app_loads_briefing_in_background_then_answers():
    session = ChatSession(lambda msgs: "因为 a.py:1 改了减号",
                          diff="d", title="t", body="b", issue=None, briefing_text="B")

    def prepare():
        return "初始BRIEF内容", session

    app = ReviewPilotApp(prepare)

    async def scenario():
        async with app.run_test() as pilot:
            for _ in range(150):          # 等后台 prepare 完成、输入框启用
                if app._session is not None and not app.query_one("#ask").disabled:
                    break
                await pilot.pause(0.02)
            app.query_one("#ask").value = "为什么有风险?"
            await pilot.press("enter")
            for _ in range(150):          # 等线程里的 session.ask 完成
                if len(session.messages) >= 3:
                    break
                await pilot.pause(0.02)

    _run(scenario())
    assert app._session is session
    assert len(session.messages) == 3            # system + user + assistant
    assert session.messages[1]["content"] == "为什么有风险?"
    assert session.messages[-1]["content"] == "因为 a.py:1 改了减号"
