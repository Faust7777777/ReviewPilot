"""确定性生成"我检查了什么"——补"诚实评审"的信任缺口。

即使没找到问题,也如实交代:看了多少改动、检查了哪些维度、为何判定无高置信问题、
以及能力边界。内容由 diff 与 findings 推导(不是模型自由发挥),固定维度、避免噪声。
"""
from reviewpilot.diffnorm import parse_unified_diff, split_diff_by_file
from reviewpilot.models import Finding, FindingKind, InspectionCheck

_LIMITATIONS = ["仅基于 PR 描述与 diff", "未运行测试", "未读取完整仓库上下文"]


def _summarize_trace(trace) -> str:
    reads = list(dict.fromkeys(t["args"].get("path", "") for t in trace
                               if t.get("tool") == "read_file" and t.get("ok", True)
                               and t["args"].get("path")))  # 只报真读到的,读失败的不算
    searches = list(dict.fromkeys(t["args"].get("query", "") for t in trace
                                  if t.get("tool") == "search" and t["args"].get("query")))
    parts = []
    if reads:
        parts.append("读取 " + "、".join(reads))
    if searches:
        parts.append("搜索 " + "、".join(f"“{s}”" for s in searches))
    return ";".join(parts)


def build_inspection(diff: str, findings: list[Finding],
                     trace=None, dropped=None) -> tuple[str, list[InspectionCheck], list[str]]:
    from reviewpilot.analyzer import _should_skip, DEFAULT_MAX_FILES
    all_blocks = split_diff_by_file(diff)
    files = [f for f, _ in all_blocks if f]
    reviewable = [(f, d) for f, d in all_blocks if not _should_skip(f, d, 12000)]
    hunks = parse_unified_diff(diff)
    n_intent = sum(f.kind == FindingKind.INTENT_MISMATCH for f in findings)
    n_risk = sum(f.kind == FindingKind.RISK for f in findings)

    scope_note = f"{len(files)} 个文件,{len(hunks)} 个 hunk"
    if len(reviewable) != len(files):
        scope_note += f"(过滤生成/依赖后可审 {len(reviewable)} 个)"
    inspected = [
        InspectionCheck(dimension="变更范围", note=scope_note),
        InspectionCheck(dimension="意图一致性",
                        note=f"发现 {n_intent} 处声明外/不符" if n_intent else "未发现声明外改动"),
        InspectionCheck(dimension="边界/逻辑风险",
                        note=f"发现 {n_risk} 处" if n_risk else "未发现可由 diff 直接证明的问题"),
        InspectionCheck(dimension="测试缺口",
                        status="needs_context",
                        note="见风险项" if n_risk else "未发现明确缺失;充分性需结合测试策略"),
        InspectionCheck(dimension="接口影响",
                        note="见风险项" if n_risk else "未发现签名/调用约定变化"),
    ]
    if trace:  # ReAct 取证过程:展示模型实际读了哪些文件/搜了什么(可见可信)
        summary_t = _summarize_trace(trace)
        if summary_t:
            inspected.insert(1, InspectionCheck(dimension="取证过程", note=summary_t))
    if dropped:  # 诚实声明:护栏丢弃了哪些低可信项(不静默忽略)
        from collections import Counter
        reasons = Counter(d["reason"] for d in dropped)
        detail = "、".join(f"{r} {n} 条" for r, n in reasons.items())
        inspected.append(InspectionCheck(
            dimension="证据过滤",
            note=f"已丢弃 {len(dropped)} 条低可信结论({detail})——诚实声明,非静默忽略"))
    if findings:
        summary = f"发现 {len(findings)} 条可报告项(见下);其余维度已检查。"
    else:
        summary = "未发现高置信问题——以下维度均已检查,无可由 diff 直接证明的问题。"
    limitations = list(_LIMITATIONS)
    if len(reviewable) > DEFAULT_MAX_FILES:
        limitations.append(
            f"改动较大(共 {len(files)} 个文件,过滤生成/依赖后约 {len(reviewable)} 个),"
            f"超出一次可信完整评审范围;仅覆盖最相关的 {DEFAULT_MAX_FILES} 个。"
            f"疑似初始导入/大同步时,建议给具体 PR、commit range 或缩小到某目录。"
        )
    return summary, inspected, limitations
