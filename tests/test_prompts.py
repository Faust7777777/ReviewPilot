import pytest

from reviewpilot.prompts import load
from reviewpilot.analyzer import build_prompt
from reviewpilot.chat import ChatSession


def test_loads_all_sections_nonempty():
    for key in ("SYSTEM", "FINISH", "CHUNKED", "CHAT", "DISCOVERY"):
        assert load(key).strip(), f"section {key} 为空"


def test_discovery_section_matches_resolve_system():
    # 修复 2:resolve.py 的 _RESOLVE_SYSTEM 应从 reviewer.md 的 DISCOVERY 小节加载,
    # 且文本与原硬编码一致(尾随空白忽略)。
    from reviewpilot.resolve import _RESOLVE_SYSTEM

    discovery = load("DISCOVERY")
    assert discovery  # 非空
    assert discovery.rstrip() == _RESOLVE_SYSTEM.rstrip()


def test_system_and_finish_stay_single_line():
    # 这两段原本是拼接的单行字符串,外置成 .md 后不应被换行污染
    assert "\n" not in load("SYSTEM")
    assert "\n" not in load("FINISH")
    assert load("SYSTEM").startswith("你是只读代码评审助手")


def test_chunked_has_placeholders_and_formats_cleanly():
    chunked = load("CHUNKED")
    for ph in ("{title}", "{body}", "{issue}", "{diff}"):
        assert ph in chunked
    out = build_prompt("DIFFTEXT", "T", "B", "ISS")  # build_prompt(diff,title,body,issue)
    assert "DIFFTEXT" in out and "T" in out
    assert "{title}" not in out and "{diff}" not in out  # 占位符已被替换


def test_chat_template_formats_via_session():
    chat = load("CHAT")
    for ph in ("{title}", "{body}", "{issue}", "{diff}", "{briefing}"):
        assert ph in chat
    # ChatSession 构造时会 .format 这个模板,不应抛 KeyError
    s = ChatSession(lambda msgs: "ok", "D", "T", "B", "ISS", "BRIEF")
    assert "{title}" not in s.messages[0]["content"]
    assert "BRIEF" in s.messages[0]["content"]


def test_missing_section_raises():
    with pytest.raises(KeyError):
        load("DOES_NOT_EXIST")
