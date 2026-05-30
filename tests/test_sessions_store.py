from reviewpilot import sessions_store
from reviewpilot.prfetch import PRData


def test_save_list_load_session_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    pr = PRData(
        pr_ref="owner/repo#7",
        title="Fix login",
        body="Body",
        issue="ISS-1",
        diff="diff --git a/a.py b/a.py\n+++ b/a.py\n+x",
    )
    messages = [
        {"role": "system", "content": "briefing context"},
        {"role": "user", "content": "why?"},
        {"role": "assistant", "content": "because"},
    ]

    session_id = sessions_store.save_session(pr, "BRIEF", messages, session_id="s1")

    assert session_id == "s1"
    listed = sessions_store.list_sessions()
    assert listed == [{"id": "s1", "pr_ref": "owner/repo#7", "created_at": listed[0]["created_at"]}]

    loaded = sessions_store.load_session("s1")
    assert loaded["pr_ref"] == "owner/repo#7"
    assert loaded["title"] == "Fix login"
    assert loaded["body"] == "Body"
    assert loaded["issue"] == "ISS-1"
    assert loaded["diff"] == pr.diff
    assert loaded["briefing_text"] == "BRIEF"
    assert loaded["messages"] == messages
