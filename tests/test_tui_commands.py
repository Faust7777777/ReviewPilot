import asyncio
import os

from reviewpilot.chat import ChatSession
from reviewpilot.prfetch import PRData
from reviewpilot.tui_app import ReviewPilotApp


DIFF = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-old
+new
"""


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _log_text(app):
    return "\n".join(
        getattr(widget, "source", "") or getattr(widget, "_initial_markdown", "")
        for widget in app.query("Markdown")
    )


def test_help_command_lists_commands_without_starting_analysis():
    analyzed = []

    def resolve_pr(text):
        analyzed.append(text)
        raise AssertionError("slash commands must not resolve PRs")

    app = ReviewPilotApp(resolve_pr, lambda pr, on_progress=None: None)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#ask").value = "/help"
            await pilot.press("enter")
            await pilot.pause()
            text = _log_text(app)
            assert "/help" in text
            assert "/model" in text
            assert "/files" in text

    _run(scenario())
    assert analyzed == []
    assert app._session is None


def test_model_chat_command_updates_environment(monkeypatch):
    monkeypatch.delenv("RP_MODEL_CHAT", raising=False)
    app = ReviewPilotApp(lambda text: None, lambda pr, on_progress=None: None)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#ask").value = "/model chat foo"
            await pilot.press("enter")
            await pilot.pause()

    _run(scenario())
    assert os.environ["RP_MODEL_CHAT"] == "foo"


def test_files_and_diff_commands_after_analysis(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    session = ChatSession(lambda msgs: "reply", DIFF, "t", "b", None, "BRIEF")

    def resolve_pr(text):
        return PRData(pr_ref="local:worktree", title="t", body="b", diff=DIFF)

    def analyze_fn(pr, on_progress=None):
        return "BRIEF", session

    app = ReviewPilotApp(resolve_pr, analyze_fn)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#ask").value = "local"
            await pilot.press("enter")
            for _ in range(200):
                if app._session is not None and not app.query_one("#ask").disabled:
                    break
                await pilot.pause(0.02)

            app.query_one("#ask").value = "/files"
            await pilot.press("enter")
            await pilot.pause()
            assert "a.py" in _log_text(app)

            app.query_one("#ask").value = "/diff"
            await pilot.press("enter")
            await pilot.pause()
            assert "+new" in _log_text(app)

    _run(scenario())
