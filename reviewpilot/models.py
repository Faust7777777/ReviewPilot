from enum import Enum
from pydantic import BaseModel


class FindingKind(str, Enum):
    SUMMARY = "summary"
    INTENT_MISMATCH = "intent_mismatch"
    RISK = "risk"
    SUGGESTION = "suggestion"


class Confidence(str, Enum):
    HIGH = "high"
    CHECK_MANUALLY = "check_manually"


class Finding(BaseModel):
    kind: FindingKind
    title: str
    file: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    evidence: str = ""
    confidence: Confidence = Confidence.CHECK_MANUALLY
    rationale: str = ""
    needs_human: bool = False


class InspectionCheck(BaseModel):
    dimension: str
    status: str = "checked"   # checked | not_applicable | needs_context
    note: str = ""


class Briefing(BaseModel):
    pr_ref: str
    findings: list[Finding] = []
    summary: str = ""
    inspected: list[InspectionCheck] = []
    limitations: list[str] = []
