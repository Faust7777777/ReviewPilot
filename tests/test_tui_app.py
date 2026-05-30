import asyncio

from reviewpilot.tui_app import ReviewPilotApp
from reviewpilot.chat import ChatSession


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_app_mounts_briefing_and_answers_question():
    session = ChatSession(lambda msgs: "因为 a.py:1 改了减号",
                          diff="d", title="t", body="b", issue=None, briefing_text="B")
    app = ReviewPilotApp("初始BRIEF内容", session)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#ask").value = "为什么有风险?"
            await pilot.press("enter")
            for _ in range(100):          # 等线程里的 session.ask 完成
                if len(session.messages) >= 3:
                    break
                await pilot.pause(0.02)

    _run(scenario())
    # system + user + assistant
    assert len(session.messages) == 3
    assert session.messages[1]["content"] == "为什么有风险?"
    assert session.messages[-1]["content"] == "因为 a.py:1 改了减号"
