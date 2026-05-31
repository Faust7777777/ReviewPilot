"""ReviewPilot 评审员指令的单一可信来源。

评审员的系统提示外置在同目录 `reviewer.md`(按 `## 大写KEY` 分小节),代码从这里加载,
而不是把 prompt 硬编码在 .py 字符串里——这样它可版本化、可 diff、可审计,正是 harness 的
"system prompts" 组件。注意:这与**根目录** `AGENTS.md` 是两回事,后者是给"开发本仓库的
agent"的指令,不是 ReviewPilot 喂给它所驱动评审员的提示。
"""
import re
from functools import lru_cache
from importlib.resources import files

# 小节以行首 `## KEY`(全大写,机器读取的键)分隔;中文小标题不会被当作 KEY。
_SECTION_RE = re.compile(r"^##[ \t]+([A-Z_]+)[ \t]*$", re.MULTILINE)


@lru_cache(maxsize=1)
def _raw() -> str:
    return files(__package__).joinpath("reviewer.md").read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def load(section: str) -> str:
    """返回 `reviewer.md` 中 `## <section>` 小节的正文(去首尾空白)。缺失则抛 KeyError。"""
    text = _raw()
    marks = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(marks):
        if m.group(1) == section:
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            return text[m.end():end].strip()
    raise KeyError(f"reviewer.md 缺少小节:## {section}")
