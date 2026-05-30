from collections import defaultdict
from reviewpilot.models import Finding, FindingKind

_EVIDENCE_REQUIRED = {FindingKind.RISK, FindingKind.SUGGESTION, FindingKind.INTENT_MISMATCH}

def apply_guardrail(findings: list[Finding], max_per_kind: int = 3) -> list[Finding]:
    kept: list[Finding] = []
    counts: dict[FindingKind, int] = defaultdict(int)
    for f in findings:
        if f.kind in _EVIDENCE_REQUIRED and not f.evidence.strip():
            continue
        if counts[f.kind] >= max_per_kind:
            continue
        counts[f.kind] += 1
        kept.append(f)
    return kept
