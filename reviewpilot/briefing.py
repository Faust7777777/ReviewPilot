from reviewpilot.models import Briefing, Finding

_KIND_TITLE = {
    "summary": "变更总结",
    "intent_mismatch": "意图对照",
    "risk": "风险",
    "suggestion": "建议",
}


def _render_finding(f: Finding) -> str:
    loc = ""
    if f.file:
        loc = f.file + (f":{f.line_start}" if f.line_start else "")
    tag = "需人工确认" if f.needs_human else f.confidence.value
    head = f"- [{tag}] {f.title}"
    parts = [head]
    if loc:
        parts.append(f"  位置: {loc}")
    if f.evidence:
        parts.append(f"  证据: {f.evidence}")
    if f.rationale:
        parts.append(f"  说明: {f.rationale}")
    return "\n".join(parts)


def render_briefing(b: Briefing) -> str:
    lines = [f"# ReviewPilot — {b.pr_ref}", ""]
    if b.summary:
        lines += ["## 结论", b.summary, ""]
    for kind, title in _KIND_TITLE.items():
        group = [f for f in b.findings if f.kind.value == kind]
        if not group:
            continue
        lines.append(f"## {title}")
        lines.extend(_render_finding(f) for f in group)
        lines.append("")
    if b.inspected:
        lines.append("## 我检查了什么")
        lines += [f"- {c.dimension}:{c.note}" for c in b.inspected]
        lines.append("")
    if b.limitations:
        lines.append("## 限制")
        lines += [f"- {x}" for x in b.limitations]
        lines.append("")
    if not b.summary and not b.findings and not b.inspected:
        lines.append("未发现高置信问题。")
    return "\n".join(lines).rstrip() + "\n"
