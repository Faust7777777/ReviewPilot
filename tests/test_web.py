from fastapi.testclient import TestClient

from reviewpilot.web import render_briefing_html, render_page, create_app
from reviewpilot.models import Briefing, Finding, FindingKind, Confidence


def _briefing():
    return Briefing(pr_ref="o/r#7", findings=[
        Finding(kind=FindingKind.INTENT_MISMATCH, title="夹带支付改动", file="pay.py",
                line_start=3, evidence="pay.py:3", confidence=Confidence.HIGH),
        Finding(kind=FindingKind.RISK, title="业务规则存疑", needs_human=True,
                evidence="order.py:10"),
    ])


def test_render_html_has_ref_titles_badges_and_escapes():
    out = render_briefing_html(_briefing())
    assert "o/r#7" in out
    assert "夹带支付改动" in out and "pay.py:3" in out
    assert "需人工确认" in out and "b-high" in out


def test_render_html_empty_shows_no_issue():
    assert "未发现高置信问题" in render_briefing_html(Briefing(pr_ref="o/r#1"))


def test_render_page_escapes_pr_url():
    assert "&lt;x&gt;" in render_page(pr_url="<x>")


def test_index_returns_form():
    client = TestClient(create_app(briefing_fn=lambda url: _briefing()))
    r = client.get("/")
    assert r.status_code == 200 and 'name="pr_url"' in r.text


def test_review_endpoint_renders_briefing():
    client = TestClient(create_app(briefing_fn=lambda url: _briefing()))
    r = client.post("/review", data={"pr_url": "https://github.com/o/r/pull/7"})
    assert r.status_code == 200
    assert "夹带支付改动" in r.text and "需人工确认" in r.text


def test_review_endpoint_reports_error_explicitly():
    def boom(url):
        raise RuntimeError("gh failed")
    client = TestClient(create_app(briefing_fn=boom))
    r = client.post("/review", data={"pr_url": "x"})
    assert r.status_code == 200 and "评审失败" in r.text and "gh failed" in r.text


def test_review_endpoint_empty_url_shows_error_page():
    client = TestClient(create_app(briefing_fn=lambda url: _briefing()))
    r = client.post("/review", data={"pr_url": ""})
    assert r.status_code == 200 and "请填写 PR 链接" in r.text
