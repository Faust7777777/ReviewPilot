import re

from fastapi.testclient import TestClient

from reviewpilot.web import render_briefing_html, render_page, create_app
from reviewpilot.models import Briefing, Finding, FindingKind, Confidence
from reviewpilot.chat import ChatSession


def _briefing():
    return Briefing(pr_ref="o/r#7", findings=[
        Finding(kind=FindingKind.INTENT_MISMATCH, title="夹带支付改动", file="pay.py",
                line_start=3, evidence="pay.py:3", confidence=Confidence.HIGH),
        Finding(kind=FindingKind.RISK, title="业务规则存疑", needs_human=True,
                evidence="order.py:10"),
    ])


def _prepare(url):
    session = ChatSession(lambda msgs: "因为 pay.py:3 改了支付", diff="d", title="t",
                          body="b", issue=None, briefing_text="B")
    return _briefing(), session


# ---- 纯渲染 ----
def test_render_html_has_ref_titles_badges_and_escapes():
    out = render_briefing_html(_briefing())
    assert "o/r#7" in out and "夹带支付改动" in out and "pay.py:3" in out
    assert "需人工确认" in out and "b-high" in out


def test_render_html_empty_shows_no_issue():
    assert "未发现高置信问题" in render_briefing_html(Briefing(pr_ref="o/r#1"))


def test_render_page_escapes_pr_url():
    assert "&lt;x&gt;" in render_page(pr_url="<x>")


# ---- 端点 ----
def test_index_returns_form():
    client = TestClient(create_app(prepare_fn=_prepare))
    r = client.get("/")
    assert r.status_code == 200 and 'name="pr_url"' in r.text


def test_review_renders_briefing_and_ask_form():
    client = TestClient(create_app(prepare_fn=_prepare))
    r = client.post("/review", data={"pr_url": "https://github.com/o/r/pull/7"})
    assert r.status_code == 200
    assert "夹带支付改动" in r.text
    assert 'name="session_id"' in r.text and 'action="/ask"' in r.text


def test_review_empty_url_shows_error():
    client = TestClient(create_app(prepare_fn=_prepare))
    r = client.post("/review", data={"pr_url": ""})
    assert "请填写 PR 链接" in r.text


def test_ask_continues_conversation():
    client = TestClient(create_app(prepare_fn=_prepare))
    r1 = client.post("/review", data={"pr_url": "https://github.com/o/r/pull/7"})
    sid = re.search(r'name="session_id" value="([0-9a-f]+)"', r1.text).group(1)
    r2 = client.post("/ask", data={"session_id": sid, "question": "为什么夹带?"})
    assert r2.status_code == 200
    assert "为什么夹带?" in r2.text                 # 用户问题回显
    assert "因为 pay.py:3 改了支付" in r2.text        # 助手回答


def test_ask_unknown_session_reports_expired():
    client = TestClient(create_app(prepare_fn=_prepare))
    r = client.post("/ask", data={"session_id": "deadbeef", "question": "x"})
    assert "会话已过期" in r.text


def test_review_failure_shown_explicitly():
    def boom(url):
        raise RuntimeError("gh failed")
    client = TestClient(create_app(prepare_fn=boom))
    r = client.post("/review", data={"pr_url": "x"})
    assert "评审失败" in r.text and "gh failed" in r.text
