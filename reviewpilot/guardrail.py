from collections import defaultdict
from reviewpilot.diffnorm import split_diff_by_file
from reviewpilot.models import Finding, FindingKind

_EVIDENCE_REQUIRED = {FindingKind.RISK, FindingKind.SUGGESTION, FindingKind.INTENT_MISMATCH}

def apply_guardrail(findings: list[Finding], max_per_kind: int = 3, diff: str | None = None) -> list[Finding]:
    kept: list[Finding] = []
    counts: dict[FindingKind, int] = defaultdict(int)
    changed_files = {file for file, _ in split_diff_by_file(diff) if file} if diff is not None else set()
    for f in findings:
        if f.kind in _EVIDENCE_REQUIRED and not f.evidence.strip():
            continue
        if f.kind in _EVIDENCE_REQUIRED and changed_files and f.file and f.file not in changed_files:
            continue
        if counts[f.kind] >= max_per_kind:
            continue
        counts[f.kind] += 1
        kept.append(f)
    return kept
