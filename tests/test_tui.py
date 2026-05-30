import builtins
import sys

from reviewpilot.tui import _fallback_input, make_tui_input


def test_fallback_input_uses_builtin_input(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda prompt_text: "hi")

    assert _fallback_input("> ") == "hi"


def test_make_tui_input_returns_callable():
    assert callable(make_tui_input())


def test_make_tui_input_falls_back_when_not_tty(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(builtins, "input", lambda prompt_text: "pipe")

    ask = make_tui_input()

    assert ask("> ") == "pipe"
