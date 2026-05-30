import argparse
from reviewpilot.prfetch import fetch_pr, _default_runner
from reviewpilot.analyzer import analyze_chunked
from reviewpilot.guardrail import apply_guardrail
from reviewpilot.briefing import render_briefing
from reviewpilot.models import Briefing
from reviewpilot.llm import deepseek_llm


def build_briefing(url: str, llm=deepseek_llm, runner=_default_runner) -> Briefing:
    pr = fetch_pr(url, runner=runner)
    findings = analyze_chunked(pr.diff, pr.title, pr.body, pr.issue, llm=llm)
    findings = apply_guardrail(findings)
    return Briefing(pr_ref=pr.pr_ref, findings=findings)


def run_review(url: str, llm=deepseek_llm, runner=_default_runner) -> str:
    return render_briefing(build_briefing(url, llm=llm, runner=runner))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="reviewpilot")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rev = sub.add_parser("review")
    rev.add_argument("pr_url")
    ev = sub.add_parser("eval")
    ev.add_argument("samples", help="带标注的样本集 JSON,如 evalset/samples.json")
    ev.add_argument("--no-guard", action="store_true", help="关闭诚实护栏(用于对照)")
    args = parser.parse_args(argv)
    if args.cmd == "review":
        print(run_review(args.pr_url))
    elif args.cmd == "eval":
        from reviewpilot.evaluate import load_samples, evaluate
        result = evaluate(load_samples(args.samples), llm=deepseek_llm,
                          apply_guard=not args.no_guard)
        print(result.summary())


if __name__ == "__main__":
    main()
