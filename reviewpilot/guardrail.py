from collections import defaultdict
from reviewpilot.diffnorm import split_diff_by_file
from reviewpilot.models import Finding, FindingKind

_EVIDENCE_REQUIRED = {FindingKind.RISK, FindingKind.SUGGESTION, FindingKind.INTENT_MISMATCH}

def apply_guardrail(findings: list[Finding], max_per_kind: int = 3,
                    diff: str | None = None, read_files=None) -> list[Finding]:
    """诚实护栏 + 证据校验:无证据丢弃、每类配额,且 file 必须落在"可取证文件集"内——
    即 diff 改动文件 ∪ 模型在 Review Loop 里读过的文件(read_files);否则视为幻觉丢弃。
    (ReAct loop 会读 diff 之外的调用方/相关文件,故 read_files 也算 grounded。)"""
    kept: list[Finding] = []
    counts: dict[FindingKind, int] = defaultdict(int)
    grounded: set[str] = set()
    if diff is not None:
        grounded |= {file for file, _ in split_diff_by_file(diff) if file}
    grounded |= {p for p in (read_files or []) if p}
    for f in findings:
        if f.kind in _EVIDENCE_REQUIRED and not f.evidence.strip():
            continue
        if f.kind in _EVIDENCE_REQUIRED and grounded and f.file and f.file not in grounded:
            continue  # file 不在 diff 也不在读过的文件 → 幻觉,丢弃
        if counts[f.kind] >= max_per_kind:
            continue
        counts[f.kind] += 1
        kept.append(f)
    return kept
