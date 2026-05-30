"""小样本 sanity eval:在带标注的样本上跑流水线,量误报率/漏报率。

样本内联 diff(可复现,不依赖外部 PR),含 negative("clean")样本专测误报。
不宣称"证明",只作 sanity 检查。
"""
import json
import time
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from reviewpilot.analyzer import analyze
from reviewpilot.guardrail import apply_guardrail
from reviewpilot.models import Finding, FindingKind

# 视为"指认了一个问题"的 finding 类型(summary/suggestion 不算指认问题)
_PROBLEM_KINDS = {FindingKind.RISK, FindingKind.INTENT_MISMATCH}


class Sample(BaseModel):
    name: str
    title: str
    diff: str
    label: Literal["issue", "clean"]
    body: str = ""
    issue: str | None = None
    expect_substring: str | None = None  # issue 样本:命中文本应包含的提示词


@dataclass
class SampleResult:
    name: str
    label: str
    outcome: str          # TP / TN / FP / FN
    n_problem: int        # 指认问题的 finding 数
    latency_s: float


@dataclass
class EvalResult:
    results: list[SampleResult]
    fp_rate: float        # 误报率 = FP / clean 样本数
    fn_rate: float        # 漏报率 = FN / issue 样本数

    def summary(self) -> str:
        n = len(self.results)
        tp = sum(r.outcome == "TP" for r in self.results)
        tn = sum(r.outcome == "TN" for r in self.results)
        fp = sum(r.outcome == "FP" for r in self.results)
        fn = sum(r.outcome == "FN" for r in self.results)
        avg = sum(r.latency_s for r in self.results) / n if n else 0.0
        lines = [
            f"样本 {n}  TP={tp} TN={tn} FP={fp} FN={fn}",
            f"误报率(FP/clean) = {self.fp_rate:.0%}   漏报率(FN/issue) = {self.fn_rate:.0%}   "
            f"平均延迟 = {avg:.1f}s",
            "",
        ]
        for r in self.results:
            lines.append(f"  [{r.outcome}] {r.name} ({r.label}, problem findings={r.n_problem})")
        return "\n".join(lines)


def _problem_findings(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.kind in _PROBLEM_KINDS]


def evaluate_sample(s: Sample, llm, apply_guard: bool = True) -> SampleResult:
    t0 = time.perf_counter()
    findings = analyze(s.diff, s.title, s.body, s.issue, llm=llm)
    if apply_guard:
        findings = apply_guardrail(findings)
    latency = time.perf_counter() - t0

    problems = _problem_findings(findings)
    flagged = len(problems) > 0
    if flagged and s.expect_substring:
        blob = " ".join(f"{f.title} {f.evidence} {f.rationale}" for f in problems)
        matched = s.expect_substring in blob
    else:
        matched = flagged

    if s.label == "clean":
        outcome = "FP" if flagged else "TN"
    else:  # issue
        outcome = "TP" if matched else "FN"
    return SampleResult(s.name, s.label, outcome, len(problems), latency)


def evaluate(samples: list[Sample], llm, apply_guard: bool = True) -> EvalResult:
    results = [evaluate_sample(s, llm, apply_guard=apply_guard) for s in samples]
    n_clean = sum(s.label == "clean" for s in samples) or 1
    n_issue = sum(s.label == "issue" for s in samples) or 1
    fp = sum(r.outcome == "FP" for r in results)
    fn = sum(r.outcome == "FN" for r in results)
    return EvalResult(results=results, fp_rate=fp / n_clean, fn_rate=fn / n_issue)


def load_samples(path: str) -> list[Sample]:
    with open(path, encoding="utf-8") as fh:
        return [Sample.model_validate(item) for item in json.load(fh)]
