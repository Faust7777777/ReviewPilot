"""ReviewPilot 技术验证 spike(day 2)。

目的:在写一行产品代码前,先用最小脚本钉死三件事——
  A. Aider 能否当依赖被程序化驱动,并跑只读问答模式 AskCoder;
  B. 选定的 LLM(DeepSeek,经 litellm)能否真实调用;
  C. 端到端:用 Aider+LLM 评审一个含 bug 的文件,且全程不改动目标仓库(只读)。

运行(必须 Python 3.12;3.13 因 numpy 老轮子缺失会装不上):
    python3.12 -m venv .venv && . .venv/bin/activate
    pip install setuptools wheel aider-chat
    DEEPSEEK_API_KEY=sk-xxx RP_MODEL=deepseek/deepseek-v4-flash python spikes/smoke_aider_deepseek.py

key 只从环境变量读,绝不硬编码。
"""
import os
import subprocess
import tempfile
import traceback

MODEL = os.environ.get("RP_MODEL", "deepseek/deepseek-v4-flash")
KEY = os.environ.get("DEEPSEEK_API_KEY", "")


def section(title):
    print(f"\n===== {title} =====", flush=True)


def main():
    # ---- A. Aider 能否 import + 实例化只读 AskCoder ----
    section("A. import & instantiate Aider (read-only)")
    coder = None
    target_repo = None
    try:
        from aider.coders import Coder
        from aider.io import InputOutput
        from aider.models import Model
        print("import OK: Coder, Model, InputOutput")

        target_repo = tempfile.mkdtemp(prefix="rp_repo_")
        buggy = os.path.join(target_repo, "calc.py")
        with open(buggy, "w") as fh:
            fh.write("def add(a, b):\n    return a - b  # bug: should be a + b\n")

        io = InputOutput(yes=True, pretty=False)
        model = Model(MODEL)
        coder = Coder.create(
            main_model=model,
            io=io,
            edit_format="ask",            # 只读问答,不进编辑循环
            fnames=[],
            read_only_fnames=[buggy],
            auto_commits=False,
            dirty_commits=False,
            dry_run=True,
            suggest_shell_commands=False,
            use_git=False,
            stream=False,
        )
        print(
            f"AskCoder ready: edit_format={coder.edit_format}, "
            f"auto_commits={coder.auto_commits}, dry_run={coder.dry_run}, "
            f"type={type(coder).__name__}"
        )
    except Exception:
        print("PART A FAILED:")
        traceback.print_exc()

    # ---- B. LLM 直连(litellm)真实调用 ----
    section("B. direct litellm call")
    try:
        import litellm

        resp = litellm.completion(
            model=MODEL,
            messages=[{"role": "user", "content": "只回复两个字:可以"}],
            api_key=KEY,
            max_tokens=20,
        )
        print("litellm OK, reply:", resp.choices[0].message.content.strip())
    except Exception:
        print("PART B FAILED:")
        traceback.print_exc()

    # ---- C. 端到端 review + 只读校验 ----
    section("C. real review via Aider AskCoder")
    try:
        answer = coder.run(
            with_message=(
                "你是代码评审助手,只看不改。这个文件有没有 bug?"
                "一句话指出,并给证据(哪一行)。"
            )
        )
        print("review answer:", (answer or "").strip()[:400])
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=target_repo,
            capture_output=True,
            text=True,
        ).stdout
        print("target repo git status (空=只读成立):", status or "(clean)")
    except Exception:
        print("PART C FAILED:")
        traceback.print_exc()

    section("DONE")


if __name__ == "__main__":
    main()
