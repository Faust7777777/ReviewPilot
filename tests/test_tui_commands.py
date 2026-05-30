import asyncio
import os

from reviewpilot.chat import ChatSession
from reviewpilot.prfetch import PRData
from reviewpilot.resolve import Target
from reviewpilot.tui_app import ReviewPilotApp


class _StubServices:
    """注入式目标解析:local/pr 直出 PRData;repo 列 PR。"""

    def __init__(self, pr=None, prs=None):
        self._pr = pr
        self._prs = prs or []

    def interpret(self, text):
        t = text.strip()
        if t.startswith("local"):
            return Target("local", value=t)
        return Target("pr", value=t)

    def pr_data(self, ref):
        return self._pr

    def local_data(self, text):
        return self._pr

    def list_prs(self, repo):
        return self._prs

    def repo_latest(self, repo):
        return self._pr


DIFF = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-old
+new
"""


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        executor = getattr(loop, "_default_executor", None)
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
        loop.close()


def _log_text(app):
    return "\n".join(app.transcript)


def test_help_command_lists_commands_without_starting_analysis():
    app = ReviewPilotApp(_StubServices(), lambda pr, on_progress=None: None)

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
    assert app._session is None


def test_model_chat_command_updates_environment(monkeypatch):
    monkeypatch.delenv("RP_MODEL_CHAT", raising=False)
    app = ReviewPilotApp(_StubServices(), lambda pr, on_progress=None: None)

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
    pr = PRData(pr_ref="local:worktree", title="t", body="b", diff=DIFF)

    def analyze_fn(pr, on_progress=None):
        return "BRIEF", session

    app = ReviewPilotApp(_StubServices(pr=pr), analyze_fn)

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
