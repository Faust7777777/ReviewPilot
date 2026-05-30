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
