"""Disk persistence for TUI review sessions."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from reviewpilot.prfetch import PRData


def _state_root() -> Path:
    base = Path.home() / ".local/state"
    import os

    if os.environ.get("XDG_STATE_HOME"):
        base = Path(os.environ["XDG_STATE_HOME"])
    return base.expanduser() / "reviewpilot/sessions"


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-")
    return slug[:60] or "session"


def _new_id(pr_ref: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{_slug(pr_ref)}"


def _session_path(session_id: str) -> Path:
    if Path(session_id).name != session_id or session_id in {"", ".", ".."}:
        raise ValueError("invalid session id")
    return _state_root() / f"{session_id}.json"


def save_session(
    pr: PRData,
    briefing_text: str,
    messages: list[dict],
    session_id: str | None = None,
) -> str:
    """Save a session and return its stable id."""
    session_id = session_id or _new_id(pr.pr_ref)
    root = _state_root()
    root.mkdir(parents=True, exist_ok=True)
    path = _session_path(session_id)
    created_at = datetime.now(timezone.utc).isoformat()
    if path.exists():
        try:
            created_at = json.loads(path.read_text(encoding="utf-8")).get("created_at") or created_at
        except Exception:
            pass
    state = {
        "id": session_id,
        "pr_ref": pr.pr_ref,
        "title": pr.title,
        "body": pr.body,
        "issue": pr.issue,
        "diff": pr.diff,
        "briefing_text": briefing_text,
        "messages": list(messages),
        "created_at": created_at,
    }
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return session_id


def list_sessions() -> list[dict]:
    root = _state_root()
    if not root.exists():
        return []
    rows = []
    for path in root.glob("*.json"):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append({
            "id": state.get("id") or path.stem,
            "pr_ref": state.get("pr_ref", ""),
            "created_at": state.get("created_at", ""),
        })
    return sorted(rows, key=lambda row: row["created_at"], reverse=True)


def load_session(session_id: str) -> dict:
    path = _session_path(session_id)
    return json.loads(path.read_text(encoding="utf-8"))
