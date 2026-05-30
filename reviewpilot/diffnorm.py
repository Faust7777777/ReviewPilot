import re
from dataclasses import dataclass, field

_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

@dataclass
class Hunk:
    file: str
    new_start: int
    lines: list[str] = field(default_factory=list)

def split_diff_by_file(diff_text: str) -> list[tuple[str, str]]:
    """把一个多文件 diff 拆成 [(file, 该文件的 diff 文本)]。用于大 PR 分块分析。
    以 `diff --git ` 为文件边界;无该头时整体作为单块。"""
    blocks: list[tuple[str, str]] = []
    cur: dict | None = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if cur is not None:
                blocks.append((cur["file"], "\n".join(cur["lines"])))
            cur = {"file": "", "lines": [line]}
            continue
        if cur is None:
            cur = {"file": "", "lines": []}
        cur["lines"].append(line)
        m = _FILE_RE.match(line)
        if m:
            cur["file"] = m.group(1)
    if cur is not None:
        blocks.append((cur["file"], "\n".join(cur["lines"])))
    return blocks


def parse_unified_diff(diff_text: str) -> list[Hunk]:
    hunks: list[Hunk] = []
    cur_file: str | None = None
    cur: Hunk | None = None
    for line in diff_text.splitlines():
        m_file = _FILE_RE.match(line)
        if m_file:
            cur_file = m_file.group(1)
            cur = None
            continue
        m_hunk = _HUNK_RE.match(line)
        if m_hunk and cur_file is not None:
            cur = Hunk(file=cur_file, new_start=int(m_hunk.group(1)))
            hunks.append(cur)
            continue
        if cur is not None and line and line[0] in "+- ":
            cur.lines.append(line)
    return hunks
