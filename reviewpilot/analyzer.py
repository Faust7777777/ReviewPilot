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


# 生成类/二进制文件:不值得逐行审,且会拖垮分析(如 40KB 的 svg、lock 文件)
_SKIP_SUFFIXES = (".svg", ".map", ".min.js", ".min.css", ".png", ".jpg", ".jpeg",
                  ".gif", ".pdf", ".ico", ".woff", ".woff2", ".lock")
# vendored/生成目录:整段排除(node_modules/.bin/pbjs 这类根本不该审)
_SKIP_DIR_SEGMENTS = frozenset({
    "node_modules", "dist", "build", "vendor", ".next", "out", "target",
    "__pycache__", ".venv", "venv", "site-packages", "bower_components",
    "coverage", ".git", "third_party", ".idea", ".gradle",
})
# 源码扩展名:评审优先级最高
_SOURCE_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".rb", ".rs",
                ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".php", ".kt", ".swift",
                ".scala", ".sh", ".rs", ".m", ".mm", ".vue")


def _should_skip(fname: str, file_diff: str, max_file_chars: int) -> bool:
    low = fname.lower()
    if any(seg in _SKIP_DIR_SEGMENTS for seg in low.split("/")):
        return True  # vendored/生成目录
    if any(low.endswith(s) for s in _SKIP_SUFFIXES):
        return True
    if "lock" in low and low.endswith((".json", ".yaml", ".yml", ".toml")):
        return True  # package-lock.json / poetry.lock 之类
    if len(file_diff) > max_file_chars:
        return True  # 单文件 diff 过大,跳过以保证响应速度
    return False


def _review_score(fname: str, file_diff: str) -> int:
    """评审优先级:源码 > 其它;改动行数越多越靠前。用于'取最该审的 N 个'而非字母序。"""
    score = 1000 if fname.lower().endswith(_SOURCE_EXTS) else 0
    churn = sum(1 for ln in file_diff.splitlines() if ln[:1] in "+-")
    return score + churn


def _pack(blocks: list[tuple[str, str]], max_chars: int) -> list[list[tuple[str, str]]]:
    """把多个文件按字符预算打包成几批,每批 ≤ max_chars(单文件超限自成一批)。"""
    batches: list[list[tuple[str, str]]] = []
    cur: list[tuple[str, str]] = []
    cur_len = 0
    for f, d in blocks:
        if cur and cur_len + len(d) > max_chars:
            batches.append(cur)
            cur, cur_len = [], 0
        cur.append((f, d))
        cur_len += len(d)
    if cur:
        batches.append(cur)
    return batches


DEFAULT_MAX_FILES = 40  # 超过则只深审最相关的这么多个(见诚实范围提示)


def analyze_chunked(diff, title, body, issue, llm, max_chars: int = 6000,
                    max_file_chars: int = 12000, max_files: int = DEFAULT_MAX_FILES,
                    on_progress=None) -> list[Finding]:
    """大 PR 分块:diff 超过 max_chars 时按文件拆分,**按预算打包成几批**(而非逐文件一次调用)
    再合并;跳过生成类/二进制/超大文件;文件过多则只分析前 max_files 个。小 PR 走单次调用。
    on_progress(msg) 可选:逐步回报进度。"""
    if len(diff) <= max_chars:
        if on_progress:
            on_progress("分析改动…")
        return analyze(diff, title, body, issue, llm)
    from reviewpilot.diffnorm import split_diff_by_file
    blocks = [(f, d) for f, d in split_diff_by_file(diff)
              if not _should_skip(f, d, max_file_chars)]
    # 排序:源码 + 改动多的优先,取"最该审的",而非 split/字母序
    blocks.sort(key=lambda fd: _review_score(fd[0], fd[1]), reverse=True)
    if len(blocks) > max_files:
        if on_progress:
            on_progress(f"改动较大(过滤生成/依赖后仍 {len(blocks)} 个文件),"
                        f"按相关性只深审最该看的 {max_files} 个;其余未覆盖,建议给具体 PR 或缩小范围。")
        blocks = blocks[:max_files]
    batches = _pack(blocks, max_chars)
    findings: list[Finding] = []
    for i, batch in enumerate(batches, 1):
        if on_progress:
            names = ", ".join(f or "改动" for f, _d in batch[:3])
            more = "…" if len(batch) > 3 else ""
            on_progress(f"分析第 {i}/{len(batches)} 批({len(batch)} 文件:{names}{more})…")
        joined = "\n".join(d for _f, d in batch)
        findings.extend(analyze(joined, title, body, issue, llm))
    return findings
