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


def build_briefing_for(pr, llm=_ANALYZE_LLM, on_progress=None, workspace=None) -> Briefing:
    if workspace is not None:
        # 受限只读 Review Loop:模型按需 read_file/search 取证再出 finding(harness 主求解面)
        from reviewpilot.review_loop import run_review_loop
        from reviewpilot.llm import chat_tools
        findings, _trace = run_review_loop(
            pr.diff, pr.title, pr.body, pr.issue, workspace,
            chat_tools=partial(chat_tools, stage="analyze"),
            chat=partial(chat, stage="analyze"),
            on_progress=on_progress)
    else:
        findings = analyze_chunked(pr.diff, pr.title, pr.body, pr.issue, llm=llm,
                                   on_progress=on_progress)
    findings = apply_guardrail(findings, diff=pr.diff)
    summary, inspected, limitations = build_inspection(pr.diff, findings)
    return Briefing(pr_ref=pr.pr_ref, findings=findings,
                    summary=summary, inspected=inspected, limitations=limitations)


def workspace_for(pr, on_progress=None):
    """为评审取得只读工作区:local 用当前目录;PR/repo 浅 clone。失败返回 None(回退 analyze_chunked)。"""
    from reviewpilot.workspace import RepoWorkspace
    ref = pr.pr_ref or ""
    try:
        if ref.startswith("local"):
            return RepoWorkspace(".")
        repo = ref.split("#")[0].split("@")[0].strip()  # owner/repo#N 或 owner/repo@sha
        if "/" in repo:
            if on_progress:
                on_progress(f"浅 clone {repo} 供取证…")
            return RepoWorkspace.clone(repo)
    except Exception:
        return None
    return None


def build_briefing(url: str, llm=_ANALYZE_LLM, runner=_default_runner) -> Briefing:
    return build_briefing_for(fetch_pr(url, runner=runner), llm=llm)


def run_review(url: str, llm=_ANALYZE_LLM, runner=_default_runner) -> str:
    return render_briefing(build_briefing(url, llm=llm, runner=runner))


def resolve_pr_text(text: str):
    """把用户在 TUI 里输入的一行解析为 PRData:
    GitHub PR 链接 → fetch_pr;`local` / `local main...HEAD` / `local --staged` → fetch_local。"""
    text = text.strip()
    low = text.lower()
    if low == "local":
        return fetch_local()
    if low.startswith("local"):
        rest = text[len("local"):].strip()
        if rest in ("--staged", "staged"):
            return fetch_local(staged=True)
        if rest.startswith("--range"):
            rest = rest[len("--range"):].strip()
        return fetch_local(diff_range=rest) if rest else fetch_local()
    return fetch_pr(text)


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


def _analyze_to_session(pr, on_progress=None):
    """(briefing_text, session):分析 PR 出 briefing 并建会话。on_progress 透传给分析。"""
    ws = workspace_for(pr, on_progress=on_progress)
    briefing_text = render_briefing(build_briefing_for(pr, on_progress=on_progress, workspace=ws))
    session = ChatSession(_CHAT_LLM, pr.diff, pr.title, pr.body, pr.issue, briefing_text)
    return briefing_text, session


class _ChatServices:
    """TUI 的目标解析能力:确定性解析 + repo 列 PR + 模糊→大模型解析候选(待用户确认)。"""

    def interpret(self, text):
        from reviewpilot.resolve import interpret_target
        # interpret_target 调 llm(字符串),必须用字符串型 complete(而非接收 messages 列表的 chat)
        return interpret_target(text, llm=partial(complete, stage="analyze"))

    def pr_data(self, ref):
        return fetch_pr(ref)

    def local_data(self, text):
        return resolve_pr_text(text)

    def list_prs(self, repo):
        from reviewpilot.prfetch import list_open_prs
        return list_open_prs(repo)

    def repo_latest(self, repo):
        from reviewpilot.prfetch import fetch_repo_latest
        return fetch_repo_latest(repo)

    def search_repos(self, query, owner=""):
        from reviewpilot.prfetch import search_repos
        return search_repos(query, owner)


def _run_chat_ui(initial: str = None) -> None:
    """tty 下启全屏 TUI(先进界面、再在里面给 PR/repo,看分析过程);否则回退普通多轮。
    initial:可选的初始文本(命令行传了 PR/repo/--local 时自动开跑)。"""
    import sys
    if sys.stdin.isatty():
        try:
            from reviewpilot.tui_app import ReviewPilotApp
            ReviewPilotApp(_ChatServices(), _analyze_to_session, initial=initial).run()
            return
        except Exception as exc:  # TUI 不可用则降级
            print(f"(全屏 TUI 不可用,回退普通模式:{exc})")
    # 非 tty 回退:需要初始 PR
    if not initial:
        print("⚠️  非交互终端请直接给 PR:reviewpilot chat <PR链接> 或 --local")
        return
    print("正在分析 PR…")
    try:
        pr = resolve_pr_text(initial)
        briefing_text, session = _analyze_to_session(pr)
    except Exception as exc:
        print(f"⚠️  分析失败:{exc}")
        return
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
            pr = _pr_from_args(args)
            ws = workspace_for(pr)   # 取只读工作区 → 走 ReAct Review Loop(失败则回退)
            print(render_briefing(build_briefing_for(pr, workspace=ws)))
        elif args.cmd == "chat":
            initial = None  # chat 可不带 PR:进 TUI 后再输入
            if args.diff_range:
                initial = f"local {args.diff_range}"
            elif args.staged:
                initial = "local --staged"
            elif args.local:
                initial = "local"
            elif args.pr_url:
                initial = args.pr_url
            _run_chat_ui(initial)
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
