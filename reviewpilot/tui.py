from typing import Callable


def _fallback_input(prompt_text: str) -> str:
    return input(prompt_text)


def make_tui_input() -> Callable[[str], str]:
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import InMemoryHistory
    except ImportError:
        return _fallback_input

    import sys

    if not sys.stdin.isatty():
        return _fallback_input

    session = PromptSession(history=InMemoryHistory())
    return lambda prompt_text: session.prompt(prompt_text)
