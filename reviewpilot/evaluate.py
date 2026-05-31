"""小样本 sanity eval:在带标注的样本上跑流水线,量误报率/漏报率。

样本内联 diff(可复现,不依赖外部 PR),含 negative("clean")样本专测误报。
跨文件样本可带 repo_files(内存仓库),走生产主路径 ReAct Review Loop 取证——
用来检验"必须读仓库其它文件才能发现"的问题(diff 自包含样本测不出 loop 的价值)。
不宣称"证明",只作 sanity 检查。
"""

import json
import time
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from reviewpilot.analyzer import analyze_chunked
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
    repo_files: dict[str, str] | None = (
        None  # 跨文件样本:提供"仓库其它文件"给 Review Loop 读取取证
    )


@dataclass
class SampleResult:
    name: str
    label: str
    outcome: str  # TP / TN / FP / FN
    n_problem: int  # 指认问题的 finding 数
    latency_s: float


def _pct(rate: float | None) -> str:
    return "N/A" if rate is None else f"{rate:.0%}"


@dataclass
class EvalResult:
    results: list[SampleResult]
    fp_rate: float | None
    fn_rate: float | None

    def summary(self) -> str:
        n = len(self.results)
        tp = sum(r.outcome == "TP" for r in self.results)
        tn = sum(r.outcome == "TN" for r in self.results)
        fp = sum(r.outcome == "FP" for r in self.results)
        fn = sum(r.outcome == "FN" for r in self.results)
        avg = sum(r.latency_s for r in self.results) / n if n else 0.0
        lines = [
            f"样本 {n}  TP={tp} TN={tn} FP={fp} FN={fn}",
            f"误报率(FP/clean) = {_pct(self.fp_rate)}   漏报率(FN/issue) = {_pct(self.fn_rate)}   "
            f"平均延迟 = {avg:.1f}s",
            "",
        ]
        for r in self.results:
            lines.append(
                f"  [{r.outcome}] {r.name} ({r.label}, problem findings={r.n_problem})"
            )
        return "\n".join(lines)


def _counts(r: EvalResult) -> str:
    tp = sum(x.outcome == "TP" for x in r.results)
    tn = sum(x.outcome == "TN" for x in r.results)
    fp = sum(x.outcome == "FP" for x in r.results)
    fn = sum(x.outcome == "FN" for x in r.results)
    return f"{tp}/{tn}/{fp}/{fn}"


@dataclass
class EvalPair:
    guarded: EvalResult
    unguarded: EvalResult
    n_samples: int

    def summary(self) -> str:
        g, u = self.guarded, self.unguarded
        lines = [
            f"样本 {self.n_samples}  (同一批 LLM 输出,护栏开 vs 关)",
            f"{'':>6} {'护栏开':>14} {'护栏关':>14}",
            f"{'TP/TN/FP/FN':>6} {_counts(g):>14} {_counts(u):>14}",
            f"{'误报率':>6} {_pct(g.fp_rate):>14} {_pct(u.fp_rate):>14}",
            f"{'漏报率':>6} {_pct(g.fn_rate):>14} {_pct(u.fn_rate):>14}",
            "",
        ]
        return "\n".join(lines)


def _problem_findings(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.kind in _PROBLEM_KINDS]


def evaluate_sample(
    s: Sample, llm, apply_guard: bool = True, chat_tools=None, chat=None
) -> SampleResult:
    t0 = time.perf_counter()
    if s.repo_files and chat_tools and chat:
        # 跨文件样本:走生产主路径 ReAct Review Loop(按需读 repo_files 取证)
        from reviewpilot.workspace import DictWorkspace
        from reviewpilot.review_loop import run_review_loop, grounded_read_files

        findings, trace = run_review_loop(
            s.diff,
            s.title,
            s.body,
            s.issue,
            DictWorkspace(s.repo_files),
            chat_tools=chat_tools,
            chat=chat,
        )
        read_files = grounded_read_files(trace)
    else:
        # 自包含样本:走回退路径 analyze_chunked(diff 即全部上下文)
        findings = analyze_chunked(s.diff, s.title, s.body, s.issue, llm=llm)
        read_files = None
    if apply_guard:
        findings = apply_guardrail(findings, diff=s.diff, read_files=read_files)
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


def evaluate(
    samples: list[Sample], llm, apply_guard: bool = True, chat_tools=None, chat=None
) -> EvalResult:
    results = [
        evaluate_sample(
            s, llm, apply_guard=apply_guard, chat_tools=chat_tools, chat=chat
        )
        for s in samples
    ]
    n_clean = sum(s.label == "clean" for s in samples)
    n_issue = sum(s.label == "issue" for s in samples)
    fp = sum(r.outcome == "FP" for r in results)
    fn = sum(r.outcome == "FN" for r in results)
    return EvalResult(
        results=results,
        fp_rate=fp / n_clean if n_clean else None,
        fn_rate=fn / n_issue if n_issue else None,
    )


def _classify(label: str, flagged: bool, matched: bool) -> str:
    if label == "clean":
        return "FP" if flagged else "TN"
    return "TP" if matched else "FN"


def evaluate_pair(samples: list[Sample], llm, chat_tools=None, chat=None) -> EvalPair:
    """一次 LLM 调用,从同一批 raw findings 派生护栏开/关双结果(确定性 A/B 对照)。

    消除旧版 `--no-guard 跑两次 LLM` 的抖动——护栏 on/off
    的差异现在可干净归因,不再是两次独立调用混进来的模型非确定性。"""
    guarded, unguarded = [], []
    for s in samples:
        t0 = time.perf_counter()
        if s.repo_files and chat_tools and chat:
            from reviewpilot.workspace import DictWorkspace
            from reviewpilot.review_loop import run_review_loop, grounded_read_files

            raw, trace = run_review_loop(
                s.diff,
                s.title,
                s.body,
                s.issue,
                DictWorkspace(s.repo_files),
                chat_tools=chat_tools,
                chat=chat,
            )
            read_files: list | None = grounded_read_files(trace)
        else:
            raw = analyze_chunked(s.diff, s.title, s.body, s.issue, llm=llm)
            read_files = None
        latency = time.perf_counter() - t0

        for apply_guard, results in [(True, guarded), (False, unguarded)]:
            findings = (
                apply_guardrail(raw, diff=s.diff, read_files=read_files)
                if apply_guard
                else raw
            )
            problems = _problem_findings(findings)
            flagged = len(problems) > 0
            if flagged and s.expect_substring:
                blob = " ".join(
                    f"{f.title} {f.evidence} {f.rationale}" for f in problems
                )
                matched = s.expect_substring in blob
            else:
                matched = flagged
            results.append(
                SampleResult(
                    s.name,
                    s.label,
                    _classify(s.label, flagged, matched),
                    len(problems),
                    latency,
                )
            )

    n_clean = sum(s.label == "clean" for s in samples)
    n_issue = sum(s.label == "issue" for s in samples)

    def _agg(results: list[SampleResult]) -> EvalResult:
        fp = sum(r.outcome == "FP" for r in results)
        fn = sum(r.outcome == "FN" for r in results)
        return EvalResult(
            results,
            fp_rate=fp / n_clean if n_clean else None,
            fn_rate=fn / n_issue if n_issue else None,
        )

    return EvalPair(
        guarded=_agg(guarded),
        unguarded=_agg(unguarded),
        n_samples=len(samples),
    )


def load_samples(path: str) -> list[Sample]:
    with open(path, encoding="utf-8") as fh:
        return [Sample.model_validate(item) for item in json.load(fh)]
