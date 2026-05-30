import argparse
from reviewpilot.prfetch import fetch_pr, _default_runner
from reviewpilot.analyzer import analyze_chunked
from reviewpilot.guardrail import apply_guardrail
from reviewpilot.briefing import render_briefing
from reviewpilot.models import Briefing
from reviewpilot.llm import deepseek_llm, deepseek_chat
from reviewpilot.chat import ChatSession


def build_briefing_for(pr, llm=deepseek_llm) -> Briefing:
    findings = analyze_chunked(pr.diff, pr.title, pr.body, pr.issue, llm=llm)
    findings = apply_guardrail(findings)
    return Briefing(pr_ref=pr.pr_ref, findings=findings)


def build_briefing(url: str, llm=deepseek_llm, runner=_default_runner) -> Briefing:
    return build_briefing_for(fetch_pr(url, runner=runner), llm=llm)


def run_review(url: str, llm=deepseek_llm, runner=_default_runner) -> str:
    return render_briefing(build_briefing(url, llm=llm, runner=runner))


def run_chat(url: str, chat_llm=deepseek_chat, analyze_llm=deepseek_llm,
             runner=_default_runner, input_fn=input, output_fn=print) -> None:
    """先出 briefing,再进入多轮追问。input_fn/output_fn 可注入便于测试。"""
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


def main(argv=None):
    parser = argparse.ArgumentParser(prog="reviewpilot")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rev = sub.add_parser("review")
    rev.add_argument("pr_url")
    ch = sub.add_parser("chat")
    ch.add_argument("pr_url")
    ev = sub.add_parser("eval")
    ev.add_argument("samples", help="带标注的样本集 JSON,如 evalset/samples.json")
    ev.add_argument("--no-guard", action="store_true", help="关闭诚实护栏(用于对照)")
    args = parser.parse_args(argv)
    if args.cmd == "review":
        print(run_review(args.pr_url))
    elif args.cmd == "chat":
        run_chat(args.pr_url)
    elif args.cmd == "eval":
        from reviewpilot.evaluate import load_samples, evaluate
        result = evaluate(load_samples(args.samples), llm=deepseek_llm,
                          apply_guard=not args.no_guard)
        print(result.summary())


if __name__ == "__main__":
    main()
