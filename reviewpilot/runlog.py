"""结构化 run trace 落盘(可观测性)。

每次评审追加一行 JSONL,记录这次 run 的最小但真实的轨迹:
run_id / mode / model / findings / 护栏丢弃原因 / reads / searches / latency。

落盘是 **best-effort**:磁盘/权限失败只在 stderr 告警并返回 None,
绝不让评审因日志失败而崩(有意的非致命降级,不是静默吞错)。
默认路径 `~/.local/state/reviewpilot/runs/runs.jsonl`(honor XDG_STATE_HOME);
环境变量 `RP_RUN_LOG` 可覆盖路径,设为 off/0/空 则禁用。
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_DISABLED = {"off", "0", ""}


def _runs_path() -> Path | None:
    """返回 runs.jsonl 路径;若经 RP_RUN_LOG 禁用则返回 None。"""
    override = os.environ.get("RP_RUN_LOG")
    if override is not None:
        if override.strip().lower() in _DISABLED:
            return None
        return Path(override).expanduser()
    base = Path.home() / ".local/state"
    if os.environ.get("XDG_STATE_HOME"):
        base = Path(os.environ["XDG_STATE_HOME"])
    return base.expanduser() / "reviewpilot/runs/runs.jsonl"


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", text or "").strip("-")
    return slug[:60] or "run"


def _new_id(pr_ref: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{_slug(pr_ref)}"


def build_run_record(pr_ref, mode, model, findings, dropped, trace, latency_s) -> dict:
    """组装一次评审的结构化记录(纯函数,无副作用)。

    - findings:列表,每项 {kind,title,file}(kind 取 f.kind.value)。
    - dropped:来自 guardrail 的 {"finding","reason"} 字典列表 → 每项 {reason}。
    - trace:Review Loop 轨迹;reads = 成功 read_file 的 path;searches = search 的 query。
      trace 为 None 时 reads/searches 为空列表。
    """
    reads: list[str] = []
    searches: list[str] = []
    for t in trace or []:
        if t.get("tool") == "read_file" and t.get("ok"):
            path = (t.get("args") or {}).get("path", "")
            if path:
                reads.append(path)
        elif t.get("tool") == "search":
            query = (t.get("args") or {}).get("query", "")
            if query:
                searches.append(query)
    return {
        "run_id": _new_id(pr_ref),
        "ts": datetime.now(timezone.utc).isoformat(),
        "pr_ref": pr_ref,
        "mode": mode,
        "model": model,
        "n_findings": len(findings),
        "findings": [
            {"kind": f.kind.value, "title": f.title, "file": f.file} for f in findings
        ],
        "dropped": [{"reason": d.get("reason", "")} for d in (dropped or [])],
        "reads": reads,
        "searches": searches,
        "latency_s": round(latency_s, 2),
    }


def record_run(record: dict, path: str | None = None) -> str | None:
    """把 record 作为一行 JSON 追加到文件(父目录自动建)。

    best-effort:任何异常只在 stderr 打一行告警并返回 None。
    禁用(RP_RUN_LOG=off)时直接返回 None、不写。成功返回写入路径字符串。
    """
    target = Path(path).expanduser() if path else _runs_path()
    if target is None:
        return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return str(target)
    except Exception as exc:  # 非致命降级:不让评审因日志失败而崩
        print(f"⚠️  run trace 落盘失败({target}):{exc}", file=sys.stderr)
        return None
