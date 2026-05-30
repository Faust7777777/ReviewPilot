"""薄 GUI:填 PR 链接 → 渲染 reviewer briefing。内部复用 CLI 引擎(build_briefing)。"""
import html

from reviewpilot.models import Briefing, Finding

_KIND_TITLE = {
    "summary": "变更总结",
    "intent_mismatch": "意图对照",
    "risk": "风险",
    "suggestion": "建议",
}

_PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ReviewPilot</title>
<style>
 :root {{ --bg:#0f1117; --card:#1a1d27; --line:#2a2f3a; --fg:#e6e8ee; --mut:#9aa3b2;
          --hi:#2ec07a; --warn:#e0a93b; --hum:#7b8494; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; background:var(--bg); color:var(--fg);
         font:15px/1.6 -apple-system,Segoe UI,Roboto,"PingFang SC",sans-serif; }}
 .wrap {{ max-width:780px; margin:0 auto; padding:32px 20px 64px; }}
 h1 {{ font-size:22px; margin:0 0 4px; }} .sub {{ color:var(--mut); margin:0 0 24px; }}
 form {{ display:flex; gap:8px; margin-bottom:28px; }}
 input[type=text] {{ flex:1; padding:11px 13px; border-radius:9px; border:1px solid var(--line);
                     background:#11141c; color:var(--fg); font-size:14px; }}
 button {{ padding:11px 18px; border:0; border-radius:9px; background:var(--hi);
           color:#06281a; font-weight:600; cursor:pointer; }}
 .ref {{ color:var(--mut); font-size:13px; margin-bottom:18px; }}
 .group {{ margin-bottom:22px; }}
 .group h2 {{ font-size:14px; color:var(--mut); text-transform:uppercase;
              letter-spacing:.05em; margin:0 0 10px; }}
 .card {{ background:var(--card); border:1px solid var(--line); border-radius:11px;
          padding:13px 15px; margin-bottom:9px; }}
 .card .t {{ font-weight:600; }}
 .badge {{ display:inline-block; font-size:11px; font-weight:700; padding:2px 8px;
           border-radius:999px; margin-right:8px; vertical-align:middle; }}
 .b-high {{ background:rgba(46,192,122,.15); color:var(--hi); }}
 .b-check {{ background:rgba(224,169,59,.15); color:var(--warn); }}
 .b-human {{ background:rgba(123,132,148,.18); color:var(--hum); }}
 .meta {{ color:var(--mut); font-size:13px; margin-top:6px; }}
 .meta code {{ background:#11141c; padding:1px 6px; border-radius:5px; }}
 .empty {{ color:var(--mut); }}
 .err {{ background:rgba(224,59,59,.12); color:#e36; padding:12px 14px; border-radius:9px; }}
</style></head>
<body><div class="wrap">
 <h1>ReviewPilot</h1>
 <p class="sub">核对这个 PR 是否真的做了它声称要做的事 — 并对拿不准的地方诚实。</p>
 <form method="post" action="/review">
   <input type="text" name="pr_url" placeholder="GitHub PR 链接,如 https://github.com/owner/repo/pull/1"
          value="{pr_url}" required>
   <button type="submit">评审</button>
 </form>
 {result}
</div></body></html>"""


def _badge(f: Finding) -> str:
    if f.needs_human:
        return '<span class="badge b-human">需人工确认</span>'
    if f.confidence.value == "high":
        return '<span class="badge b-high">high</span>'
    return '<span class="badge b-check">check manually</span>'


def _card(f: Finding) -> str:
    loc = ""
    if f.file:
        loc = f.file + (f":{f.line_start}" if f.line_start else "")
    meta = []
    if loc:
        meta.append(f"位置 <code>{html.escape(loc)}</code>")
    if f.evidence:
        meta.append("证据:" + html.escape(f.evidence))
    if f.rationale:
        meta.append(html.escape(f.rationale))
    meta_html = f'<div class="meta">{" · ".join(meta)}</div>' if meta else ""
    return (f'<div class="card">{_badge(f)}'
            f'<span class="t">{html.escape(f.title)}</span>{meta_html}</div>')


def render_briefing_html(b: Briefing) -> str:
    blocks = [f'<div class="ref">{html.escape(b.pr_ref)}</div>']
    if b.summary:
        blocks.append(f'<div class="group"><h2>结论</h2>'
                      f'<div class="card">{html.escape(b.summary)}</div></div>')
    any_group = False
    for kind, title in _KIND_TITLE.items():
        group = [f for f in b.findings if f.kind.value == kind]
        if not group:
            continue
        any_group = True
        cards = "".join(_card(f) for f in group)
        blocks.append(f'<div class="group"><h2>{title}</h2>{cards}</div>')
    if b.inspected:
        items = "".join(
            f'<div class="meta">{html.escape(c.dimension)}:{html.escape(c.note)}</div>'
            for c in b.inspected)
        blocks.append(f'<div class="group"><h2>我检查了什么</h2><div class="card">{items}</div></div>')
    if b.limitations:
        items = "".join(f'<div class="meta">{html.escape(x)}</div>' for x in b.limitations)
        blocks.append(f'<div class="group"><h2>限制</h2><div class="card">{items}</div></div>')
    if not any_group and not b.summary and not b.inspected:
        blocks.append('<p class="empty">未发现高置信问题。</p>')
    return "\n".join(blocks)


def render_page(pr_url: str = "", result: str = "") -> str:
    return _PAGE.format(pr_url=html.escape(pr_url), result=result)


def create_app(briefing_fn=None):
    """briefing_fn(url)->Briefing,默认用 CLI 引擎(实时调 LLM)。测试时可注入。"""
    from fastapi import FastAPI, Form
    from fastapi.responses import HTMLResponse

    if briefing_fn is None:
        from reviewpilot.cli import build_briefing as briefing_fn

    app = FastAPI(title="ReviewPilot")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return render_page()

    @app.post("/review", response_class=HTMLResponse)
    def review(pr_url: str = Form("")):
        if not pr_url.strip():
            return render_page("", '<div class="err">请填写 PR 链接。</div>')
        try:
            briefing = briefing_fn(pr_url)
            return render_page(pr_url, render_briefing_html(briefing))
        except Exception as exc:  # 显式失败,不静默
            return render_page(pr_url, f'<div class="err">评审失败:{html.escape(str(exc))}</div>')

    return app


app = create_app()
