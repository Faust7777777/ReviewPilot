# ReviewPilot Core Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the offline-testable core that turns a GitHub PR into a one-page reviewer briefing of typed, evidence-bound findings.

**Architecture:** A linear pipeline — `fetch PR → normalize diff → analyze (LLM) → honesty guardrail → render briefing` — wired behind a `reviewpilot review <pr>` CLI. The analyzer takes an injected `llm` callable so all logic is unit-testable without network. Live DeepSeek (via litellm) is a thin adapter plugged in only at the CLI edge.

**Tech Stack:** Python 3.12 (hard constraint), Pydantic v2, pytest, litellm (live LLM at the edge), `gh` CLI for PR data. Aider (repo-map + conversational face) and GUI/eval are Phase 2, not in this plan.

---

## File Structure

- `pyproject.toml` — package metadata, deps, pytest config
- `reviewpilot/__init__.py`
- `reviewpilot/models.py` — `FindingKind`, `Confidence`, `Finding`, `Briefing` (Pydantic)
- `reviewpilot/diffnorm.py` — `Hunk`, `parse_unified_diff()`
- `reviewpilot/guardrail.py` — `apply_guardrail()` (pure)
- `reviewpilot/briefing.py` — `render_briefing()`
- `reviewpilot/analyzer.py` — `build_prompt()`, `parse_findings()`, `analyze()` (llm injected)
- `reviewpilot/prfetch.py` — `PRData`, `fetch_pr()` (via `gh`)
- `reviewpilot/llm.py` — `deepseek_llm()` thin litellm adapter (edge only)
- `reviewpilot/cli.py` — `reviewpilot review <pr>`
- `tests/` — one test module per unit above

---

## Task 0: Scaffold the package

**Files:**
- Create: `pyproject.toml`, `reviewpilot/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "reviewpilot"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["pydantic>=2,<3", "litellm==1.81.10"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
reviewpilot = "reviewpilot.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["reviewpilot*"]
```

- [ ] **Step 2: Create empty package files**

```bash
mkdir -p reviewpilot tests
touch reviewpilot/__init__.py tests/__init__.py
```

- [ ] **Step 3: Create venv (Python 3.12) and install**

Run:
```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```
Expected: `Successfully installed reviewpilot-0.1.0 ... pydantic ... litellm`

- [ ] **Step 4: Verify pytest runs (no tests yet)**

Run: `pytest -q`
Expected: `no tests ran` (exit 5) — confirms pytest is wired.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml reviewpilot/__init__.py tests/__init__.py
git commit -m "chore: scaffold reviewpilot package (py3.12, pydantic, litellm)"
```

---

## Task 1: Typed findings model

**Files:**
- Create: `reviewpilot/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from reviewpilot.models import Finding, FindingKind, Confidence, Briefing

def test_finding_defaults_to_check_manually_and_no_human_flag():
    f = Finding(kind=FindingKind.RISK, title="off-by-one")
    assert f.confidence == Confidence.CHECK_MANUALLY
    assert f.needs_human is False
    assert f.evidence == ""

def test_briefing_holds_findings_and_serializes():
    b = Briefing(pr_ref="o/r#1", findings=[Finding(kind=FindingKind.SUMMARY, title="x")])
    assert b.findings[0].kind == FindingKind.SUMMARY
    assert b.model_dump()["pr_ref"] == "o/r#1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reviewpilot.models'`

- [ ] **Step 3: Write minimal implementation**

```python
# reviewpilot/models.py
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

class Briefing(BaseModel):
    pr_ref: str
    findings: list[Finding] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add reviewpilot/models.py tests/test_models.py
git commit -m "feat: typed Finding/Briefing models"
```

---

## Task 2: Unified diff normalization

**Files:**
- Create: `reviewpilot/diffnorm.py`
- Test: `tests/test_diffnorm.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_diffnorm.py
from reviewpilot.diffnorm import parse_unified_diff, Hunk

DIFF = """diff --git a/calc.py b/calc.py
index e69de29..0d1f2c3 100644
--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@ def add(a, b):
-    return a - b
+    return a + b
"""

def test_parses_file_and_new_start_and_lines():
    hunks = parse_unified_diff(DIFF)
    assert len(hunks) == 1
    h = hunks[0]
    assert isinstance(h, Hunk)
    assert h.file == "calc.py"
    assert h.new_start == 1
    assert "+    return a + b" in h.lines
    assert "-    return a - b" in h.lines

def test_empty_diff_returns_no_hunks():
    assert parse_unified_diff("") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_diffnorm.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reviewpilot.diffnorm'`

- [ ] **Step 3: Write minimal implementation**

```python
# reviewpilot/diffnorm.py
import re
from dataclasses import dataclass, field

_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

@dataclass
class Hunk:
    file: str
    new_start: int
    lines: list[str] = field(default_factory=list)

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_diffnorm.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add reviewpilot/diffnorm.py tests/test_diffnorm.py
git commit -m "feat: normalize unified diff into line-numbered hunks"
```

---

## Task 3: Honesty guardrail

**Files:**
- Create: `reviewpilot/guardrail.py`
- Test: `tests/test_guardrail.py`

Rules: findings of kind risk/suggestion/intent_mismatch with empty `evidence` are dropped (summary is exempt); at most `max_per_kind` per kind (keep first); order preserved.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_guardrail.py
from reviewpilot.guardrail import apply_guardrail
from reviewpilot.models import Finding, FindingKind, Confidence

def _risk(title, evidence=""):
    return Finding(kind=FindingKind.RISK, title=title, evidence=evidence)

def test_drops_risk_without_evidence_but_keeps_summary():
    out = apply_guardrail([
        _risk("no evidence"),
        _risk("good", evidence="calc.py:2 return a-b"),
        Finding(kind=FindingKind.SUMMARY, title="summary no evidence"),
    ])
    titles = [f.title for f in out]
    assert "no evidence" not in titles
    assert "good" in titles
    assert "summary no evidence" in titles

def test_caps_each_kind_to_max():
    out = apply_guardrail([_risk(f"r{i}", evidence="e") for i in range(5)], max_per_kind=3)
    assert sum(f.kind == FindingKind.RISK for f in out) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_guardrail.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reviewpilot.guardrail'`

- [ ] **Step 3: Write minimal implementation**

```python
# reviewpilot/guardrail.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_guardrail.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add reviewpilot/guardrail.py tests/test_guardrail.py
git commit -m "feat: honesty guardrail (evidence gate + per-kind quota)"
```

---

## Task 4: Briefing renderer

**Files:**
- Create: `reviewpilot/briefing.py`
- Test: `tests/test_briefing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_briefing.py
from reviewpilot.briefing import render_briefing
from reviewpilot.models import Briefing, Finding, FindingKind, Confidence

def test_render_includes_ref_kinds_and_needs_human_marker():
    b = Briefing(pr_ref="o/r#7", findings=[
        Finding(kind=FindingKind.INTENT_MISMATCH, title="夹带支付改动",
                file="pay.py", line_start=3, evidence="pay.py:3",
                confidence=Confidence.HIGH),
        Finding(kind=FindingKind.RISK, title="业务规则存疑", needs_human=True,
                evidence="order.py:10"),
    ])
    out = render_briefing(b)
    assert "o/r#7" in out
    assert "夹带支付改动" in out
    assert "pay.py:3" in out
    assert "需人工确认" in out          # needs_human rendered, not asserted as conclusion
    assert "high" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_briefing.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reviewpilot.briefing'`

- [ ] **Step 3: Write minimal implementation**

```python
# reviewpilot/briefing.py
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
    for kind, title in _KIND_TITLE.items():
        group = [f for f in b.findings if f.kind.value == kind]
        if not group:
            continue
        lines.append(f"## {title}")
        lines.extend(_render_finding(f) for f in group)
        lines.append("")
    if len(lines) == 2:
        lines.append("未发现高置信问题。")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_briefing.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add reviewpilot/briefing.py tests/test_briefing.py
git commit -m "feat: render findings into one-page reviewer briefing"
```

---

## Task 5: Analyzer (LLM injected, structured output)

**Files:**
- Create: `reviewpilot/analyzer.py`
- Test: `tests/test_analyzer.py`

The analyzer builds a prompt from diff+intent, calls an injected `llm(prompt) -> str` returning JSON, and parses it into `Finding`s. Network is never touched in tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyzer.py
import json
from reviewpilot.analyzer import analyze, parse_findings, build_prompt
from reviewpilot.models import FindingKind

def test_build_prompt_includes_intent_and_diff():
    p = build_prompt(diff="@@ +1 @@\n+x", title="fix login", body="only login",
                     issue="login times out")
    assert "fix login" in p and "login times out" in p and "+x" in p

def test_parse_findings_reads_json_array():
    raw = json.dumps([
        {"kind": "intent_mismatch", "title": "夹带改动", "file": "pay.py",
         "line_start": 3, "evidence": "pay.py:3", "confidence": "high"}
    ])
    fs = parse_findings(raw)
    assert fs[0].kind == FindingKind.INTENT_MISMATCH and fs[0].file == "pay.py"

def test_parse_findings_tolerates_code_fence_and_garbage():
    raw = "```json\n[{\"kind\":\"risk\",\"title\":\"t\",\"evidence\":\"f:1\"}]\n```"
    assert parse_findings(raw)[0].kind == FindingKind.RISK

def test_analyze_uses_injected_llm():
    stub = lambda prompt: '[{"kind":"summary","title":"changed add()"}]'
    fs = analyze(diff="d", title="t", body="b", issue=None, llm=stub)
    assert fs[0].title == "changed add()"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_analyzer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reviewpilot.analyzer'`

- [ ] **Step 3: Write minimal implementation**

```python
# reviewpilot/analyzer.py
import json
import re
from reviewpilot.models import Finding

_PROMPT = """你是只读代码评审助手。对照"作者声称要做的事"审查这个 PR 的 diff。
作者声称(标题): {title}
作者声称(描述): {body}
关联 issue: {issue}

规则:
- 每条结论必须绑定具体文件与行(evidence),没有证据就不要输出。
- 业务正确性无法判定时,confidence 用 "check_manually" 并 needs_human=true。
- 重点找:意图不符(改了没声称的东西 / 声称做了却没做)、逻辑/边界风险、测试缺口。

只输出一个 JSON 数组,元素字段:
kind(summary|intent_mismatch|risk|suggestion), title, file, line_start, line_end,
evidence, confidence(high|check_manually), rationale, needs_human(bool)。

diff:
{diff}
"""

def build_prompt(diff: str, title: str, body: str, issue: str | None) -> str:
    return _PROMPT.format(title=title, body=body, issue=issue or "(无)", diff=diff)

def _extract_json_array(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    if fenced:
        return fenced.group(1)
    start, end = text.find("["), text.rfind("]")
    return text[start:end + 1] if start != -1 and end != -1 else "[]"

def parse_findings(raw: str) -> list[Finding]:
    try:
        data = json.loads(_extract_json_array(raw))
    except json.JSONDecodeError:
        return []
    out: list[Finding] = []
    for item in data:
        try:
            out.append(Finding.model_validate(item))
        except Exception:
            continue
    return out

def analyze(diff, title, body, issue, llm) -> list[Finding]:
    return parse_findings(llm(build_prompt(diff, title, body, issue)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_analyzer.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add reviewpilot/analyzer.py tests/test_analyzer.py
git commit -m "feat: analyzer builds intent-aware prompt and parses typed findings"
```

---

## Task 6: PR fetcher via `gh`

**Files:**
- Create: `reviewpilot/prfetch.py`
- Test: `tests/test_prfetch.py`

`fetch_pr` shells out to `gh` (injected `runner` for tests). Returns `PRData(title, body, diff, issue)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prfetch.py
import json
from reviewpilot.prfetch import fetch_pr, PRData

def test_fetch_pr_parses_gh_outputs():
    def fake_runner(args):
        if args[:3] == ["gh", "pr", "view"]:
            return json.dumps({"title": "fix login", "body": "closes #5"})
        if args[:3] == ["gh", "pr", "diff"]:
            return "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n+x"
        raise AssertionError(args)
    data = fetch_pr("https://github.com/o/r/pull/7", runner=fake_runner)
    assert isinstance(data, PRData)
    assert data.title == "fix login"
    assert "+x" in data.diff
    assert data.pr_ref == "o/r#7"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_prfetch.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reviewpilot.prfetch'`

- [ ] **Step 3: Write minimal implementation**

```python
# reviewpilot/prfetch.py
import json
import re
import subprocess
from dataclasses import dataclass

@dataclass
class PRData:
    pr_ref: str
    title: str
    body: str
    diff: str
    issue: str | None = None

def _default_runner(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout

def _parse_ref(url: str) -> str:
    m = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    if not m:
        raise ValueError(f"not a PR url: {url}")
    return f"{m.group(1)}/{m.group(2)}#{m.group(3)}"

def fetch_pr(url: str, runner=_default_runner) -> PRData:
    meta = json.loads(runner(["gh", "pr", "view", url, "--json", "title,body"]))
    diff = runner(["gh", "pr", "diff", url])
    return PRData(pr_ref=_parse_ref(url), title=meta.get("title", ""),
                  body=meta.get("body", ""), diff=diff)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_prfetch.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add reviewpilot/prfetch.py tests/test_prfetch.py
git commit -m "feat: fetch PR title/body/diff via gh (injectable runner)"
```

---

## Task 7: LLM adapter + CLI wiring

**Files:**
- Create: `reviewpilot/llm.py`, `reviewpilot/cli.py`
- Test: `tests/test_cli.py`

`run_review` is the testable orchestration (llm + runner injected). `deepseek_llm` and `main` are the live edge (not unit-tested).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import json
from reviewpilot.cli import run_review

def test_run_review_end_to_end_with_stubs():
    def fake_runner(args):
        if args[:3] == ["gh", "pr", "view"]:
            return json.dumps({"title": "fix add", "body": "only fix add()"})
        if args[:3] == ["gh", "pr", "diff"]:
            return ("diff --git a/calc.py b/calc.py\n--- a/calc.py\n+++ b/calc.py\n"
                    "@@ -1,2 +1,2 @@\n-    return a - b\n+    return a + b")
        raise AssertionError(args)
    fake_llm = lambda prompt: json.dumps([
        {"kind": "summary", "title": "修正 add() 加法"},
        {"kind": "risk", "title": "无证据应被丢弃"},
        {"kind": "risk", "title": "好的风险", "evidence": "calc.py:2", "confidence": "high"},
    ])
    out = run_review("https://github.com/o/r/pull/7", llm=fake_llm, runner=fake_runner)
    assert "o/r#7" in out
    assert "修正 add() 加法" in out
    assert "好的风险" in out
    assert "无证据应被丢弃" not in out   # guardrail dropped it
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reviewpilot.cli'`

- [ ] **Step 3: Write the LLM adapter**

```python
# reviewpilot/llm.py
import os

def deepseek_llm(prompt: str, model: str | None = None) -> str:
    import litellm
    model = model or os.environ.get("RP_MODEL", "deepseek/deepseek-v4-flash")
    resp = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        api_key=os.environ["DEEPSEEK_API_KEY"],
        temperature=0,
    )
    return resp.choices[0].message.content
```

- [ ] **Step 4: Write the CLI orchestration**

```python
# reviewpilot/cli.py
import argparse
from reviewpilot.prfetch import fetch_pr, _default_runner
from reviewpilot.analyzer import analyze
from reviewpilot.guardrail import apply_guardrail
from reviewpilot.briefing import render_briefing
from reviewpilot.models import Briefing
from reviewpilot.llm import deepseek_llm

def run_review(url: str, llm=deepseek_llm, runner=_default_runner) -> str:
    pr = fetch_pr(url, runner=runner)
    findings = analyze(pr.diff, pr.title, pr.body, pr.issue, llm=llm)
    findings = apply_guardrail(findings)
    return render_briefing(Briefing(pr_ref=pr.pr_ref, findings=findings))

def main(argv=None):
    parser = argparse.ArgumentParser(prog="reviewpilot")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rev = sub.add_parser("review")
    rev.add_argument("pr_url")
    args = parser.parse_args(argv)
    if args.cmd == "review":
        print(run_review(args.pr_url))

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_cli.py -q`
Expected: PASS (1 passed)

- [ ] **Step 6: Full suite + live smoke**

Run: `pytest -q`
Expected: all green.
Then live (needs key): `DEEPSEEK_API_KEY=… reviewpilot review <a real PR url>` → prints a briefing.

- [ ] **Step 7: Commit**

```bash
git add reviewpilot/llm.py reviewpilot/cli.py tests/test_cli.py
git commit -m "feat: wire review pipeline behind CLI + DeepSeek adapter"
```

---

## Phase 2 (separate plan, not here)

- Aider integration: `RepoMap` for on-demand context retrieval + interactive multi-turn `AskCoder` chat face.
- Thin GUI (web): PR-URL input → rendered briefing; diff-paste degraded mode.
- Eval runner + 10–20 PR sanity set (incl. negatives); FP/FN/latency; guardrail on/off comparison.
- README + demo video.

## Self-Review

- **Spec coverage:** evidence-gate / honesty guardrail (§4) ✓ Task 3; intent-alignment (§1) ✓ Task 5 prompt+kind; typed findings (§4) ✓ Task 1; diff normalization (§3) ✓ Task 2; briefing (§5) ✓ Task 4; PR fetch (§5) ✓ Task 6; CLI review entry (§2) ✓ Task 7; double-provider via litellm (§8) ✓ Task 7 adapter. GUI/eval/Aider-chat (§2,§7) deferred to Phase 2 by design.
- **Placeholder scan:** no TBD/TODO; every code step has full code.
- **Type consistency:** `Finding`/`FindingKind`/`Confidence` fields identical across Tasks 1,3,4,5; `PRData.pr_ref` used in Tasks 6 & 7; `analyze(diff,title,body,issue,llm)` signature matches between Tasks 5 & 7; `apply_guardrail`/`render_briefing` names consistent.
