"""Jelentés: Markdown + önálló HTML (nyomtatható) + PDF (reportlab). Letisztult, légies dizájn – sadrobot."""
from __future__ import annotations

import html
import os
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import markdown as md

from .core import REPORT_DIR, Store
from .i18n import LEGAL_LABEL, t
from .llm import summarize

CAT_ORDER = ["identity", "sanctions", "company", "domain", "web", "person", "breach", "aleph", "social", "phone", "manual"]
SEV_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
_WIN = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_HOME_FONTS = os.path.expanduser("~/Library/Fonts")
FONT_CANDIDATES = {
    "body": ["/Library/Fonts/Montserrat-Regular.ttf", f"{_HOME_FONTS}/Montserrat-Regular.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
             "/System/Library/Fonts/Supplemental/Arial.ttf", f"{_WIN}\\segoeui.ttf", f"{_WIN}\\arial.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"],
    "bold": ["/Library/Fonts/Montserrat-SemiBold.ttf", f"{_HOME_FONTS}/Montserrat-SemiBold.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
             "/System/Library/Fonts/Supplemental/Arial Bold.ttf", f"{_WIN}\\segoeuib.ttf", f"{_WIN}\\arialbd.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
    "light": ["/Library/Fonts/Montserrat-Light.ttf", f"{_HOME_FONTS}/Montserrat-Light.ttf", "/Library/Fonts/Montserrat-Regular.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
              "/System/Library/Fonts/Supplemental/Arial.ttf", f"{_WIN}\\segoeuil.ttf", f"{_WIN}\\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"],
}
ACCENT = "#2F6F8F"   # nyugodt kékeszöld
INK = "#1F2933"
MUTED = "#7B8794"
LINE = "#E4E7EB"
SEV_COLOR = {"high": "#B23A48", "medium": "#C97B2A", "low": "#8A8F3C", "info": "#8AA1B1"}


def _grouped(findings: list[dict]) -> "OrderedDict[str, list[dict]]":
    g: OrderedDict[str, list[dict]] = OrderedDict((c, []) for c in CAT_ORDER)
    for f in findings:
        g.setdefault(f["category"], []).append(f)
    for c in g:
        g[c].sort(key=lambda f: SEV_ORDER.get(f.get("severity", "info"), 3))
    return OrderedDict((c, v) for c, v in g.items() if v)


def _target_rows(case: dict, lang: str) -> list[tuple[str, str]]:
    tg = case["target"]
    rows = [(t(lang, "company"), tg.company), (t(lang, "tax_id"), tg.tax_id), (t(lang, "domain"), tg.domain), (t(lang, "keywords"), ", ".join(tg.extra_keywords)),
            (t(lang, "modules_ran"), ", ".join(case.get("modules") or [])),
            (t(lang, "location"), tg.location), (t(lang, "reg_number"), tg.reg_number)]
    if case.get("person_checks"):
        rows += [(t(lang, "person"), tg.person), (t(lang, "email"), tg.email), (t(lang, "username"), tg.username), (t(lang, "phone"), tg.phone),
                 (t(lang, "birth_year"), tg.birth_year), (t(lang, "employer"), tg.employer)]
    return [(k, v) for k, v in rows if v]


def build_report(store: Store, case_id: str, run_id: str) -> Path:
    case = store.get_case(case_id)
    lang = case.get("lang", "hu")
    findings = store.get_findings(case_id, run_id)
    qlog = store.get_query_log(case_id, run_id)
    summary_md, backend = summarize(case, findings, lang)
    store.save_summary(case_id, run_id, summary_md, backend)
    store.audit("summary_generated", case_id, f"backend={backend} run={run_id}")
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    safe = re.sub(r"[^\w-]+", "_", case["title"])[:40]
    base = REPORT_DIR / f"{stamp}_{safe}_{run_id}"
    ctx = dict(case=case, lang=lang, findings=findings, qlog=qlog, summary_md=summary_md, backend=backend, run_id=run_id,
               generated=datetime.now().strftime("%Y-%m-%d %H:%M"))
    (base.with_suffix(".md")).write_text(_markdown(**ctx), encoding="utf-8")
    (base.with_suffix(".html")).write_text(render_html(**ctx), encoding="utf-8")
    try:
        _pdf(base.with_suffix(".pdf"), **ctx)
    except Exception as e:  # noqa: BLE001
        store.audit("pdf_failed", case_id, str(e))
    return base.with_suffix(".pdf") if base.with_suffix(".pdf").exists() else base.with_suffix(".html")


# ---------------------------------------------------------------- Markdown
def _markdown(case, lang, findings, qlog, summary_md, backend, run_id, generated) -> str:
    L = [f"# {t(lang,'report_title')} — {case['title']}", "", f"_{t(lang,'by')} · {t(lang,'generated')}: {generated} · {t(lang,'run_id')}: {run_id}_", ""]
    L += [f"- **{k}:** {v}" for k, v in _target_rows(case, lang)]
    L += [f"- **{t(lang,'purpose')}:** {case['purpose']}", f"- **{t(lang,'legal_basis')}:** {LEGAL_LABEL[lang].get(case['legal_basis'], case['legal_basis'])}", "",
          f"## {t(lang,'summary')}", "", summary_md, ""]
    for cat, fs in _grouped(findings).items():
        L.append(f"## {t(lang,'cat').get(cat, cat)}")
        for f in fs:
            sev = t(lang, "sev")[f.get("severity", "info")]
            L.append(f"- **[{sev}] {f['title']}** — {f.get('summary','')} {'<' + f['url'] + '>' if f.get('url') else ''} _({f['source']})_")
        L.append("")
    L += [f"## {t(lang,'querylog')}", "", f"| {t(lang,'time')} | {t(lang,'source')} | {t(lang,'action')} | {t(lang,'status')} | {t(lang,'ms')} | {t(lang,'count')} |", "|---|---|---|---|---|---|"]
    L += [f"| {q['ts'][11:19]} | {q['source']} | {q['action']} | {q['status']} | {q['duration_ms']} | {q['result_count'] if q['result_count'] is not None else ''} |" for q in qlog]
    L += ["", f"## {t(lang,'disclaimer')}", "", t(lang, "disclaimer_text")]
    return "\n".join(L)


# ---------------------------------------------------------------- HTML
CSS = """
:root{--ink:%(ink)s;--muted:%(muted)s;--accent:%(accent)s;--line:%(line)s;--bg:#FBFBFA}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,'Inter','Segoe UI',Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
.page{max-width:900px;margin:0 auto;padding:56px 40px 80px}
header{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:1px solid var(--line);padding-bottom:22px;margin-bottom:34px}
h1{font-weight:500;font-size:28px;letter-spacing:-.01em;margin:0 0 4px}h2{font-weight:500;font-size:18px;margin:44px 0 14px;color:var(--ink);letter-spacing:.01em}
h3{font-size:15px;font-weight:600;margin:20px 0 6px}.kicker{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:600}
.meta{color:var(--muted);font-size:13px;text-align:right;line-height:1.5}.brand{font-size:12px;color:var(--muted);letter-spacing:.06em}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px 28px;margin:0 0 8px}.grid div{padding:10px 0;border-bottom:1px solid var(--line)}
.grid b{display:block;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600;margin-bottom:2px}
.summary{background:#fff;border:1px solid var(--line);border-radius:14px;padding:26px 30px;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.summary p:first-child{margin-top:0}.summary blockquote{margin:0 0 14px;padding:8px 14px;border-left:3px solid var(--line);color:var(--muted);font-size:13px}
.f{display:grid;grid-template-columns:86px 1fr;gap:14px;padding:12px 0;border-bottom:1px solid var(--line)}.f:last-child{border-bottom:0}
.sev{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;padding:3px 0;text-align:center;border-radius:999px;height:22px;align-self:start;color:#fff}
.f .t{font-weight:600}.f .s{color:#3E4C59;font-size:14px}.f .src{color:var(--muted);font-size:12px}.f a{color:var(--accent);text-decoration:none;word-break:break-all}
table{width:100%%;border-collapse:collapse;font-size:12px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600;letter-spacing:.06em;text-transform:uppercase;font-size:10.5px}
.note{color:var(--muted);font-size:12.5px}footer{margin-top:60px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px;display:flex;justify-content:space-between}
details summary{cursor:pointer;color:var(--accent);font-weight:500}
@media print{body{background:#fff}.page{padding:0;max-width:none}.summary{box-shadow:none}h2{break-after:avoid}.f{break-inside:avoid}a[href]:after{content:''}@page{margin:18mm 16mm}}
""" % dict(ink=INK, muted=MUTED, accent=ACCENT, line=LINE)


def render_html(case, lang, findings, qlog, summary_md, backend, run_id, generated, embed: bool = False) -> str:
    e = html.escape
    H = []
    if not embed:
        H.append(f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                 f"<title>{e(t(lang,'report_title'))} – {e(case['title'])}</title><style>{CSS}</style></head><body><div class='page'>")
    H.append(f"<header><div><div class='kicker'>{e(t(lang,'app'))}</div><h1>{e(t(lang,'report_title'))}</h1><div class='brand'>{e(t(lang,'by'))}</div></div>"
             f"<div class='meta'>{e(case['title'])}<br>{e(t(lang,'generated'))}: {generated}<br>{e(t(lang,'run_id'))}: {run_id}</div></header>")
    H.append("<div class='grid'>" + "".join(f"<div><b>{e(k)}</b>{e(v)}</div>" for k, v in _target_rows(case, lang)) +
             f"<div><b>{e(t(lang,'purpose'))}</b>{e(case['purpose'])}</div><div><b>{e(t(lang,'legal_basis'))}</b>{e(LEGAL_LABEL[lang].get(case['legal_basis'], case['legal_basis']))}</div>"
             f"<div><b>{e(t(lang,'created'))}</b>{e(case['created_at'][:16])}</div><div><b>{e(t(lang,'requester'))}</b>{e(case.get('requester') or '-')}</div></div>")
    H.append(f"<p class='note'>{e(t(lang,'person_on' if case.get('person_checks') else 'person_off'))}</p>")
    H.append(f"<h2>{e(t(lang,'summary'))}</h2><div class='summary'>{md.markdown(summary_md, extensions=['tables'])}</div>")
    grouped = _grouped(findings)
    for cat, fs in grouped.items():
        if cat == "manual":
            continue
        H.append(f"<h2>{e(t(lang,'cat').get(cat, cat))} <span class='note'>({len(fs)})</span></h2>")
        for f in fs:
            sev = f.get("severity", "info")
            link = f"<div><a href='{e(f['url'])}' target='_blank' rel='noopener'>{e(f['url'][:110])}</a></div>" if f.get("url") else ""
            H.append(f"<div class='f'><span class='sev' style='background:{SEV_COLOR[sev]}'>{e(t(lang,'sev')[sev])}</span><div><div class='t'>{e(f['title'])}</div>"
                     f"<div class='s'>{e(f.get('summary',''))}</div>{link}<div class='src'>{e(f['source'])}</div></div></div>")
    if "manual" in grouped:
        H.append(f"<h2>{e(t(lang,'manual'))}</h2><ul>" + "".join(f"<li><a href='{e(f['url'])}' target='_blank' rel='noopener'>{e(f['title'])}</a></li>" for f in grouped["manual"]) + "</ul>")
    H.append(f"<h2>{e(t(lang,'querylog'))} <span class='note'>({len(qlog)})</span></h2><details><summary>{len(qlog)} ▾</summary><table><tr><th>{e(t(lang,'time'))}</th><th>{e(t(lang,'source'))}</th><th>{e(t(lang,'action'))}</th><th>{e(t(lang,'request'))}</th><th>{e(t(lang,'status'))}</th><th>{e(t(lang,'ms'))}</th><th>{e(t(lang,'count'))}</th></tr>")
    H += [f"<tr><td>{q['ts'][11:19]}</td><td>{e(q['source'])}</td><td>{e(q['action'])}</td><td>{e((q['request'] or '')[:120])}</td><td>{e(q['status'] or '')}</td><td>{q['duration_ms']}</td><td>{'' if q['result_count'] is None else q['result_count']}</td></tr>" for q in qlog]
    H.append("</table></details>")
    H.append(f"<h2>{e(t(lang,'disclaimer'))}</h2><p class='note'>{e(t(lang,'disclaimer_text'))}</p>")
    H.append(f"<footer><span>{e(t(lang,'app'))} · {e(t(lang,'by'))}</span><span>summary: {backend}</span></footer>")
    if not embed:
        H.append("</div></body></html>")
    return "".join(H)


# ---------------------------------------------------------------- PDF
def _font(kind: str) -> str | None:
    for p in FONT_CANDIDATES[kind]:
        if os.path.exists(p):
            return p
    return None


def _pdf(path: Path, case, lang, findings, qlog, summary_md, backend, run_id, generated) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    body_f, bold_f, light_f = "Helvetica", "Helvetica-Bold", "Helvetica"
    if _font("body"):
        pdfmetrics.registerFont(TTFont("DDBody", _font("body"))); body_f = "DDBody"
    if _font("bold"):
        pdfmetrics.registerFont(TTFont("DDBold", _font("bold"))); bold_f = "DDBold"
    if _font("light"):
        pdfmetrics.registerFont(TTFont("DDLight", _font("light"))); light_f = "DDLight"

    ink, muted, accent, line = colors.HexColor(INK), colors.HexColor(MUTED), colors.HexColor(ACCENT), colors.HexColor(LINE)
    S = {
        "kicker": ParagraphStyle("k", fontName=bold_f, fontSize=7.5, textColor=accent, leading=10, spaceAfter=3),
        "h1": ParagraphStyle("h1", fontName=light_f, fontSize=22, textColor=ink, leading=27, spaceAfter=2),
        "brand": ParagraphStyle("b", fontName=body_f, fontSize=8, textColor=muted, leading=11),
        "meta": ParagraphStyle("m", fontName=body_f, fontSize=8.5, textColor=muted, leading=12, alignment=TA_RIGHT),
        "h2": ParagraphStyle("h2", fontName=bold_f, fontSize=12.5, textColor=ink, leading=16, spaceBefore=16, spaceAfter=7),
        "h3": ParagraphStyle("h3", fontName=bold_f, fontSize=10.5, textColor=ink, leading=14, spaceBefore=8, spaceAfter=3),
        "body": ParagraphStyle("p", fontName=body_f, fontSize=9.5, textColor=ink, leading=14.5, spaceAfter=5),
        "small": ParagraphStyle("s", fontName=body_f, fontSize=8, textColor=muted, leading=11),
        "label": ParagraphStyle("l", fontName=bold_f, fontSize=6.8, textColor=muted, leading=9),
        "val": ParagraphStyle("v", fontName=body_f, fontSize=9.5, textColor=ink, leading=13),
        "ft": ParagraphStyle("ft", fontName=bold_f, fontSize=9.3, textColor=ink, leading=13),
        "fs": ParagraphStyle("fs", fontName=body_f, fontSize=8.6, textColor=colors.HexColor("#3E4C59"), leading=12.5),
        "fu": ParagraphStyle("fu", fontName=body_f, fontSize=7.6, textColor=accent, leading=10.5),
        "bul": ParagraphStyle("bul", fontName=body_f, fontSize=9.5, textColor=ink, leading=14, leftIndent=12, bulletIndent=2, spaceAfter=2),
        "cell": ParagraphStyle("c", fontName=body_f, fontSize=6.9, textColor=ink, leading=8.8),
        "cellh": ParagraphStyle("ch", fontName=bold_f, fontSize=6.6, textColor=muted, leading=8.5),
    }

    def P(txt, st="body"):
        return Paragraph(html.escape(str(txt)).replace("\n", "<br/>"), S[st])

    def sev_chip(sev):
        col = colors.HexColor(SEV_COLOR[sev])
        tb = Table([[Paragraph(html.escape(t(lang, "sev")[sev]).upper(), ParagraphStyle("chip", fontName=bold_f, fontSize=6.3, textColor=colors.white, leading=8, alignment=1))]],
                   colWidths=[19 * mm], rowHeights=[5.2 * mm])
        tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), col), ("ROUNDEDCORNERS", [2.6 * mm]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        return tb

    def md_flow(text):
        """Egyszerű Markdown -> flowables (címsorok, felsorolás, bekezdés, idézet, félkövér)."""
        out = []
        for raw in text.splitlines():
            ln = raw.rstrip()
            if not ln.strip():
                continue
            def inl(s):
                s = html.escape(s)
                s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
                s = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<i>\1</i>", s)
                s = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", s)
                return s
            if ln.startswith("### "):
                out.append(Paragraph(inl(ln[4:]), S["h3"]))
            elif ln.startswith("## "):
                out.append(Paragraph(inl(ln[3:]), S["h3"]))
            elif ln.startswith("# "):
                out.append(Paragraph(inl(ln[2:]), S["h3"]))
            elif ln.startswith("> "):
                out.append(Paragraph(inl(ln[2:]), S["small"]))
            elif re.match(r"^\s*[-*•] ", ln):
                out.append(Paragraph(inl(re.sub(r"^\s*[-*•] ", "", ln)), S["bul"], bulletText="•"))
            elif re.match(r"^\s*\d+[.)] ", ln):
                num = re.match(r"^\s*(\d+)[.)] ", ln).group(1)
                out.append(Paragraph(inl(re.sub(r"^\s*\d+[.)] ", "", ln)), S["bul"], bulletText=f"{num}."))
            elif ln.startswith("|"):
                cells = [c.strip() for c in ln.strip("|").split("|")]
                if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    continue
                out.append(Paragraph(" · ".join(inl(c) for c in cells if c), S["fs"]))
            else:
                out.append(Paragraph(inl(ln), S["body"]))
        return out

    W = A4[0] - 32 * mm
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=f"{t(lang,'report_title')} – {case['title']}", author="sadrobot · osint-dd", subject=case["purpose"])
    story = []
    head = Table([[[P(t(lang, "app"), "kicker"), P(t(lang, "report_title"), "h1"), P(t(lang, "by"), "brand")],
                   [P(f"{case['title']}\n{t(lang,'generated')}: {generated}\n{t(lang,'run_id')}: {run_id}", "meta")]]], colWidths=[W * 0.62, W * 0.38])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [head, Spacer(1, 4), HRFlowable(width="100%", thickness=0.6, color=line), Spacer(1, 8)]

    rows = _target_rows(case, lang) + [(t(lang, "purpose"), case["purpose"]), (t(lang, "legal_basis"), LEGAL_LABEL[lang].get(case["legal_basis"], case["legal_basis"])),
                                        (t(lang, "created"), case["created_at"][:16]), (t(lang, "requester"), case.get("requester") or "-")]
    cells = [[P(k.upper(), "label"), P(v, "val")] for k, v in rows]
    grid = [[*cells[i], *(cells[i + 1] if i + 1 < len(cells) else [Spacer(0, 0), Spacer(0, 0)])] for i in range(0, len(cells), 2)]
    gt = Table(grid, colWidths=[W * 0.14, W * 0.36, W * 0.14, W * 0.36])
    gt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, line), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [gt, Spacer(1, 6), P(t(lang, "person_on" if case.get("person_checks") else "person_off"), "small")]

    story.append(P(t(lang, "summary"), "h2"))
    story += [HRFlowable(width="100%", thickness=0.5, color=line), Spacer(1, 6), *md_flow(summary_md), Spacer(1, 6), HRFlowable(width="100%", thickness=0.5, color=line)]

    grouped = _grouped(findings)
    for cat, fs in grouped.items():
        if cat == "manual":
            continue
        story.append(P(f"{t(lang,'cat').get(cat, cat)}  ({len(fs)})", "h2"))
        for f in fs:
            right = [P(f["title"], "ft"), P(f.get("summary", "") or " ", "fs")]
            if f.get("url"):
                right.append(Paragraph(f"<a href='{html.escape(f['url'])}'>{html.escape(f['url'][:100])}</a>", S["fu"]))
            right.append(P(f["source"], "small"))
            row = Table([[sev_chip(f.get("severity", "info")), right]], colWidths=[24 * mm, W - 24 * mm])
            row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, line), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            story.append(KeepTogether(row))
    if "manual" in grouped:
        story.append(P(t(lang, "manual"), "h2"))
        for f in grouped["manual"]:
            story.append(Paragraph(f"<a href='{html.escape(f['url'])}'>{html.escape(f['title'])}</a>", S["bul"], bulletText="→"))

    story.append(P(f"{t(lang,'querylog')}  ({len(qlog)})", "h2"))
    hdr = [Paragraph(html.escape(t(lang, k)), S["cellh"]) for k in ("time", "source", "action", "request", "status", "ms", "count")]
    data = [hdr] + [[Paragraph(html.escape(str(x)), S["cell"]) for x in (q["ts"][11:19], q["source"], q["action"], (q["request"] or "")[:95], q["status"] or "", q["duration_ms"],
                                                                     "" if q["result_count"] is None else q["result_count"])] for q in qlog]
    qt = Table(data, colWidths=[W * 0.08, W * 0.14, W * 0.09, W * 0.45, W * 0.1, W * 0.07, W * 0.07], repeatRows=1)
    qt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, line), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    story += [qt, P(t(lang, "disclaimer"), "h2"), P(t(lang, "disclaimer_text"), "small")]

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont(body_f, 7.2)
        canvas.setFillColor(muted)
        canvas.drawString(16 * mm, 10 * mm, f"{t(lang,'app')} · {t(lang,'by')} · {case['title']}")
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, f"{t(lang,'page')} {d.page}")
        canvas.setStrokeColor(line)
        canvas.line(16 * mm, 13.5 * mm, A4[0] - 16 * mm, 13.5 * mm)
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
