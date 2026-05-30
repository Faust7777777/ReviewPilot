import argparse
from functools import partial

from reviewpilot.prfetch import fetch_pr, fetch_local, _default_runner, PRFetchError
from reviewpilot.analyzer import analyze_chunked
from reviewpilot.guardrail import apply_guardrail
from reviewpilot.briefing import render_briefing
from reviewpilot.models import Briefing
from reviewpilot.llm import complete, chat
from reviewpilot.chat import ChatSession
from reviewpilot.inspection import build_inspection
from reviewpilot.tui import make_tui_input

# 各阶段默认 LLM(可经 RP_MODEL_<STAGE> 分别指定模型)
_ANALYZE_LLM = partial(complete, stage="analyze")
_CHAT_LLM = partial(chat, stage="chat")
_EVAL_LLM = partial(complete, stage="eval")


def build_briefing_for(pr, llm=_ANALYZE_LLM) -> Briefing:
    findings = analyze_chunked(pr.diff, pr.title, pr.body, pr.issue, llm=llm)
    findings = apply_guardrail(findings, diff=pr.diff)
    summary, inspected, limitations = build_inspection(pr.diff, findings)
    return Briefing(pr_ref=pr.pr_ref, findings=findings,
                    summary=summary, inspected=inspected, limitations=limitations)


def build_briefing(url: str, llm=_ANALYZE_LLM, runner=_default_runner) -> Briefing:
    return build_briefing_for(fetch_pr(url, runner=runner), llm=llm)


def run_review(url: str, llm=_ANALYZE_LLM, runner=_default_runner) -> str:
    return render_briefing(build_briefing(url, llm=llm, runner=runner))


def run_chat(url: str = None, chat_llm=_CHAT_LLM, analyze_llm=_ANALYZE_LLM,
             runner=_default_runner, input_fn=input, output_fn=print, pr=None) -> None:
    """先出 briefing,再进入多轮追问。input_fn/output_fn 可注入便于测试。
    pr 可直接传入(如本地模式),否则按 url 经 gh 获取。"""
    if pr is None:
        pr = fetch_pr(url, runner=runner)
    briefing_text = render_briefing(build_briefing_for(pr, llm=analyze_llm))
    output_fn(briefing_text)
    session = ChatSession(chat_llm, pr.diff, pr.title, pr.body, pr.issue, briefing_text)
    output_fn("\n— 进入多轮追问(输入 q / quit 退出)—")
    while True:
        try:
            q = input_fn("\n> ")
        except EOFError:
            break
        if q.strip().lower() in {"q", "quit", "exit"}:
            break
        if not q.strip():
            continue
        output_fn(session.ask(q))


def _add_pr_source_args(p):
    p.add_argument("pr_url", nargs="?", help="GitHub PR 链接;本地模式可省略")
    p.add_argument("--local", action="store_true", help="本地模式:读 git diff,不依赖 GitHub")
    p.add_argument("--staged", action="store_true", help="本地模式:仅暂存区改动")
    p.add_argument("--range", dest="diff_range", help="本地模式:diff 范围,如 main...HEAD")
    p.add_argument("--title", help="本地模式:作为'作者声称'的标题")
    p.add_argument("--body", help="本地模式:作为'作者声称'的描述")


def _pr_from_args(args):
    """按 CLI 参数得到 PRData:本地模式读 git diff,否则经 gh 取 PR。"""
    if args.local or args.staged or args.diff_range:
        return fetch_local(staged=args.staged, diff_range=args.diff_range,
                           title=args.title, body=args.body or "")
    if not args.pr_url:
        raise PRFetchError("请提供 PR 链接,或用 --local / --staged / --range 走本地模式。")
    return fetch_pr(args.pr_url)


def _run_chat_ui(pr) -> None:
    """tty 下启全屏 textual TUI;否则回退普通多轮循环(管道/CI/测试)。
    briefing 与 session 只构建一次,两条路径复用。"""
    import sys
    print("正在分析 PR…")
    briefing_text = render_briefing(build_briefing_for(pr))
    session = ChatSession(_CHAT_LLM, pr.diff, pr.title, pr.body, pr.issue, briefing_text)
    if sys.stdin.isatty():
        try:
            from reviewpilot.tui_app import ReviewPilotApp
            ReviewPilotApp(briefing_text, session).run()
            return
        except Exception as exc:  # TUI 不可用则降级,不让用户卡死
            print(f"(全屏 TUI 不可用,回退普通模式:{exc})")
    # 普通多轮(非 tty 或 TUI 失败):复用已建 session
    print(briefing_text)
    print("\n— 多轮追问(输入 q / quit 退出)—")
    ask = make_tui_input()
    while True:
        try:
            q = ask("\n> ")
        except EOFError:
            break
        if q.strip().lower() in {"q", "quit", "exit"}:
            break
        if q.strip():
            print(session.ask(q))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="reviewpilot")
    sub = parser.add_subparsers(dest="cmd", required=True)
    _add_pr_source_args(sub.add_parser("review"))
    _add_pr_source_args(sub.add_parser("chat"))
    ev = sub.add_parser("eval")
    ev.add_argument("samples", help="带标注的样本集 JSON,如 evalset/samples.json")
    ev.add_argument("--no-guard", action="store_true", help="关闭诚实护栏(用于对照)")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "review":
            print(render_briefing(build_briefing_for(_pr_from_args(args))))
        elif args.cmd == "chat":
            _run_chat_ui(_pr_from_args(args))
        elif args.cmd == "eval":
            from reviewpilot.evaluate import load_samples, evaluate
            result = evaluate(load_samples(args.samples), llm=_EVAL_LLM,
                              apply_guard=not args.no_guard)
            print(result.summary())
    except PRFetchError as exc:
        print(f"⚠️  {exc}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
