import json
import re
from reviewpilot.models import Finding

_PROMPT = """你是只读代码评审助手。对照"作者声称要做的事"审查这个 PR 的 diff。
作者声称(标题): {title}
作者声称(描述): {body}
关联 issue: {issue}

规则(务必遵守):
- 证据是强制的。每一条 risk / intent_mismatch / suggestion 都必须填 file、line_start,
  并在 evidence 里【原样引用 diff 中的那一行代码】。无法定位到具体行的,就不要输出该条。
- 重点找:意图不符(改了没声称的东西 / 声称做了却没做)、逻辑/边界风险、测试缺口。
- 低风险改动默认不要指认为 risk/intent_mismatch:纯新增测试、重命名、注释/拼写修正、
  纯格式化——除非其中确有缺陷。
- 业务正确性(是否符合产品/需求)无法仅凭代码判定时,confidence 用 "check_manually"
  且 needs_human=true,不要臆断为权威结论。

只输出一个 JSON 数组,元素字段:
kind(summary|intent_mismatch|risk|suggestion), title, file, line_start, line_end,
evidence, confidence(high|check_manually), rationale, needs_human(bool)。

diff:
{diff}
"""


def build_prompt(diff: str, title: str, body: str, issue: str | None) -> str:
    return _PROMPT.format(title=title, body=body, issue=issue or "(无)", diff=diff)


def _first_json_array(text: str) -> list | None:
    """扫描每个 '[' 候选位置,用 raw_decode 返回首个能解析成 list 的 JSON 数组。
    比'首个[到最后]切片'稳健:前缀里出现 `[备注]` 之类不会污染解析。"""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "[":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, list):
            return obj
    return None


def parse_findings(raw: str) -> list[Finding]:
    data: list | None = None
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.S)
    if fenced:
        try:
            cand = json.loads(fenced.group(1))
            data = cand if isinstance(cand, list) else None
        except json.JSONDecodeError:
            data = None
    if data is None:
        data = _first_json_array(raw)
    if data is None:
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
