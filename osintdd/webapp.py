"""Helyi webes felület – stdlib http.server, csak 127.0.0.1. Kétnyelvű (hu/en), letisztult, légies. sadrobot."""
from __future__ import annotations

import html
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import DEFAULT_MODULES, LEGAL_BASES, MODULES_META, Store, Target
from .i18n import LEGAL_LABEL, t
from .report import render_html
from .runner import run_case

from .core import BASE_DIR as _DATA_DIR

STORE = Store()
PROGRESS: dict[str, list[str]] = {}
RUNNING: set[str] = set()

UI = {
    "hu": dict(cases="Ügyek", new="Új ügy", title="Ügy címe", purpose="Vizsgálat célja", legal="Jogalap", lang="Jelentés nyelve",
               company="Cégnév", tax="Adószám (8 vagy 11 jegy / EU VAT)", country="Ország", domain="Domain", keywords="További kulcsszavak (vesszővel)",
               person_block="Személyi modul (GDPR-jogalap kötelező)", person_on="Személyi ellenőrzés engedélyezése", person="Személy neve", email="E-mail", username="Felhasználónév", phone="Telefon",
               requester="Kérelmező", create="Ügy létrehozása és futtatása", create_only="Csak létrehozás", run="Futtatás", rerun="Újrafuttatás", open="Megnyitás", pdf="PDF", html="HTML", md="MD",
               status="Státusz", created="Létrehozva", findings="megállapítás", log="Lekérdezési napló", delete="Törlés", empty="Még nincs ügy. Hozz létre egyet fent.",
               running="Futás…", done="kész", notes="Csak ingyenes, nyilvános források. Minden lekérés naplózva. Fizetős források: lásd README.",
               hint_legal="Cégre/domainre a „Nem személyes adat” elég. Személyhez GDPR-jogalapot kell választani és a személyi modult bekapcsolni.",
               confirm_del="Biztosan törlöd az ügyet és a naplóit?", back="← Ügyek", audit="Rendszernapló", progress="Folyamat",
               grey_title="Szürke zóna – jogi egyeztetés után, ügyenként engedélyezve",
               grey_hint="Kiszivárgott adatbázisok, oknyomozó gyűjtemények, közösségi profilok. Csak személyi modullal és dokumentált jogalappal futnak; a választás a rendszernaplóba kerül."),
    "en": dict(cases="Cases", new="New case", title="Case title", purpose="Purpose of the check", legal="Legal basis", lang="Report language",
               company="Company name", tax="Tax ID (HU 8/11 digits or EU VAT)", country="Country", domain="Domain", keywords="Extra keywords (comma-separated)",
               person_block="Person module (GDPR legal basis required)", person_on="Enable person checks", person="Person name", email="E-mail", username="Username", phone="Phone",
               requester="Requester", create="Create and run", create_only="Create only", run="Run", rerun="Re-run", open="Open", pdf="PDF", html="HTML", md="MD",
               status="Status", created="Created", findings="findings", log="Query log", delete="Delete", empty="No cases yet. Create one above.",
               running="Running…", done="done", notes="Free, public sources only. Every query is logged. Paid sources: see README.",
               hint_legal="For a company/domain, “No personal data” is enough. For a person, pick a GDPR basis and enable the person module.",
               confirm_del="Delete this case and its logs?", back="← Cases", audit="Audit log", progress="Progress",
               grey_title="Grey zone – enabled per case after legal sign-off",
               grey_hint="Leaked databases, investigative archives, social profiles. They run only with the person module and a documented legal basis; the selection is written to the audit log."),
}

CSS = """
:root{--ink:#1F2933;--muted:#7B8794;--accent:#2F6F8F;--line:#E4E7EB;--bg:#FBFBFA;--card:#fff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,'Inter','Segoe UI',Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}.wrap{max-width:1040px;margin:0 auto;padding:40px 28px 80px}
nav{display:flex;justify-content:space-between;align-items:center;margin-bottom:38px}.logo{display:flex;flex-direction:column;gap:2px}.logo b{font-weight:500;font-size:20px;letter-spacing:-.01em}
.logo span{font-size:12px;color:var(--muted)}.langs a{font-size:12px;letter-spacing:.1em;text-transform:uppercase;margin-left:14px;color:var(--muted)}.langs a.on{color:var(--accent);font-weight:600}
h2{font-weight:500;font-size:17px;margin:34px 0 14px;letter-spacing:.01em}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:26px 28px;box-shadow:0 1px 2px rgba(0,0,0,.03)}
label{display:block;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600;margin:0 0 5px}
input[type=text],select,textarea{width:100%;border:1px solid var(--line);border-radius:10px;padding:10px 12px;font:inherit;font-size:14px;background:#fff;color:var(--ink);outline:none;transition:border .15s}
input:focus,select:focus{border-color:var(--accent)}.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px 20px;margin-bottom:16px}
.person{border-top:1px dashed var(--line);margin-top:8px;padding-top:18px}.person .row{opacity:.55;transition:opacity .2s}.person.on .row{opacity:1}
.chk{display:flex;align-items:center;gap:10px;font-size:14px;margin:6px 0 14px}.chk input{width:16px;height:16px;accent-color:var(--accent)}
.btn{display:inline-block;border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:999px;padding:9px 20px;font:inherit;font-size:14px;cursor:pointer;transition:opacity .15s}
.btn:hover{opacity:.9}.btn.ghost{background:transparent;color:var(--accent)}.btn.sm{padding:5px 12px;font-size:12.5px}.btn.danger{border-color:#B23A48;color:#B23A48;background:transparent}
.hint{font-size:12.5px;color:var(--muted);margin:6px 0 0}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:middle}
th{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:600}.st{font-size:11px;letter-spacing:.08em;text-transform:uppercase;font-weight:600;padding:3px 10px;border-radius:999px;background:#EEF2F5;color:#52606D}
.st.done{background:#E3F1EA;color:#2E6B44}.st.running{background:#FFF1DC;color:#9C5B10}.muted{color:var(--muted);font-size:13px}footer{margin-top:60px;color:var(--muted);font-size:12px;text-align:center;letter-spacing:.04em}
pre{background:#F5F7F8;border-radius:10px;padding:14px;font-size:12.5px;overflow:auto;max-height:280px}.actions a{margin-right:10px}
.mods{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:8px 18px;margin:6px 0 4px}.mods label{display:flex;align-items:center;gap:9px;font-size:13.5px;text-transform:none;letter-spacing:0;color:var(--ink);font-weight:400;margin:0}.mods input{accent-color:var(--accent);width:15px;height:15px}
.grey{border:1px dashed #D9B98A;background:#FFFBF3;border-radius:12px;padding:14px 16px;margin-top:14px}.grey .gt{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#9C5B10;font-weight:600;margin-bottom:4px}.grey .gh{font-size:12.5px;color:#7B6A4B;margin:0 0 8px}
.err{background:#FBECEE;color:#8B2C38;border-radius:10px;padding:10px 14px;margin-bottom:14px;font-size:13.5px}
"""


def page(lang: str, body: str, title: str = "") -> str:
    u = UI[lang]
    other = "en" if lang == "hu" else "hu"
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title or t(lang,'app'))}</title><style>{CSS}</style></head><body><div class="wrap">
<nav><a class="logo" href="/?lang={lang}"><b>{html.escape(t(lang,'app'))}</b><span>{html.escape(t(lang,'tagline'))} · {html.escape(t(lang,'by'))}</span></a>
<div class="langs"><a href="/audit?lang={lang}">{u['audit']}</a><a class="{'on' if lang=='hu' else ''}" href="?lang=hu">HU</a><a class="{'on' if lang=='en' else ''}" href="?lang=en">EN</a></div></nav>
{body}
<footer>{html.escape(t(lang,'app'))} · {html.escape(t(lang,'by'))} · {html.escape(u['notes'])}<br><span style="opacity:.7">data: {html.escape(str(_DATA_DIR))}</span></footer></div></body></html>"""


def index(lang: str, error: str = "", vals: dict | None = None) -> str:
    u = UI[lang]
    e = html.escape
    v = vals or {}

    def val(k: str) -> str:
        return f" value='{e(v.get(k, ''))}'" if v.get(k) else ""

    def chk(k: str, default: bool = False) -> str:
        on = (v.get(k) == "on") if v else default
        return " checked" if on else ""
    sel_lb = v.get("legal_basis") or "nem_szemelyes"
    sel_lang = v.get("lang") or lang
    opts = "".join(f"<option value='{k}' {'selected' if k==sel_lb else ''}>{e(LEGAL_LABEL[lang][k])}</option>" for k in LEGAL_BASES)
    form = f"""<h2>{u['new']}</h2><div class="card"><form method="post" action="/new">{f"<div class='err'>{e(error)}</div>" if error else ''}
<input type="hidden" name="ui_lang" value="{lang}">
<div class="row"><div><label>{u['title']}</label><input type="text" name="title" required placeholder="pl. Beszállító X átvilágítás"{val("title")}></div>
<div><label>{u['purpose']}</label><input type="text" name="purpose" required placeholder="NIS2 beszállítói kockázatértékelés"{val("purpose")}></div>
<div><label>{u['legal']}</label><select name="legal_basis">{opts}</select><p class="hint">{u['hint_legal']}</p></div>
<div><label>{u['lang']}</label><select name="lang"><option value="hu" {'selected' if sel_lang=='hu' else ''}>Magyar</option><option value="en" {'selected' if sel_lang=='en' else ''}>English</option></select></div></div>
<div class="row"><div><label>{u['company']}</label><input type="text" name="company"{val("company")}></div><div><label>{u['tax']}</label><input type="text" name="tax_id"{val("tax_id")}></div>
<div><label>{u['country']}</label><input type="text" name="country" value="{e(v.get('country') or 'HU')}"></div><div><label>{u['domain']}</label><input type="text" name="domain" placeholder="example.hu"{val("domain")}></div>
<div><label>{u['keywords']}</label><input type="text" name="keywords"{val("keywords")}></div><div><label>{u['requester']}</label><input type="text" name="requester"{val("requester")}></div></div>
<div class="person{' on' if v.get('person_checks')=='on' else ''}" id="pb"><label class="chk"><input type="checkbox" name="person_checks" id="pc"{chk('person_checks')} onchange="document.getElementById('pb').classList.toggle('on',this.checked)"> {u['person_on']} <span class="muted">— {u['person_block']}</span></label>
<div class="row"><div><label>{u['person']}</label><input type="text" name="person"{val("person")}></div><div><label>{u['email']}</label><input type="text" name="email"{val("email")}></div>
<div><label>{u['username']}</label><input type="text" name="username"{val("username")}></div><div><label>{u['phone']}</label><input type="text" name="phone" placeholder="+36 …"{val("phone")}></div></div></div>
<div class="person" style="border-top:1px dashed var(--line);margin-top:8px;padding-top:16px"><label>{t(lang,'refine_block')}</label>
<div class="row"><div><label>{t(lang,'reg_number')}</label><input type="text" name="reg_number" placeholder="01-10-041234"{val("reg_number")}></div><div><label>{t(lang,'location')}</label><input type="text" name="location"{val("location")}></div>
<div><label>{t(lang,'birth_year')}</label><input type="text" name="birth_year" placeholder="1985"{val("birth_year")}></div><div><label>{t(lang,'employer')}</label><input type="text" name="employer"{val("employer")}></div></div></div>
<div class="person" style="border-top:1px dashed var(--line);margin-top:8px;padding-top:16px"><label>{t(lang,'modules_title')}</label>
<div class="mods">{''.join(f"<label><input type='checkbox' name='mod_{m}'{chk('mod_'+m, m in DEFAULT_MODULES)}> {e(t(lang,'modules')[m])}</label>" for m, g in MODULES_META if g != 'grey')}</div>
<div class="grey"><div class="gt">{u['grey_title']}</div><p class="gh">{u['grey_hint']}</p>
<div class="mods">{''.join(f"<label><input type='checkbox' name='mod_{m}'{chk('mod_'+m)}> {e(t(lang,'modules')[m])}</label>" for m, g in MODULES_META if g == 'grey')}</div></div></div>
<p style="margin-top:18px"><button class="btn" name="action" value="run">{u['create']}</button> &nbsp; <button class="btn ghost" name="action" value="create">{u['create_only']}</button></p></form></div>"""
    rows = []
    allc = STORE.list_cases()
    ordered = []
    for c in allc:
        if not c.get("parent_id"):
            ordered.append(c)
            ordered += [k for k in allc if k.get("parent_id") == c["id"]]
    ordered += [c for c in allc if c.get("parent_id") and c not in ordered]
    for c in ordered:
        tg = c["target"]
        subj = tg.get("company") or tg.get("domain") or tg.get("person") or "-"
        n = len(STORE.get_findings(c["id"]))
        st = "running" if c["id"] in RUNNING else c["status"]
        rp = c.get("report_path") or ""
        links = ""
        if rp and st == "done":
            stem = Path(rp).with_suffix("")
            links = f"<a class='btn sm ghost' href='/report/{c['id']}?lang={lang}'>{u['open']}</a> <a class='btn sm ghost' href='/file?p={urllib.parse.quote(str(stem.with_suffix('.pdf')))}' target='_blank'>{u['pdf']}</a> <a class='btn sm ghost' href='/file?p={urllib.parse.quote(str(stem.with_suffix('.md')))}' target='_blank'>{u['md']}</a>"
        run_btn = f"<a class='btn sm' href='/run/{c['id']}?lang={lang}'>{u['rerun'] if st=='done' else u['run']}</a>" if st != "running" else f"<a class='btn sm ghost' href='/run/{c['id']}?lang={lang}'>{u['running']}</a>"
        indent = "<span style='color:var(--muted)'>└ </span>" if c.get("parent_id") else ""
        rows.append(f"<tr><td>{indent}<b>{e(c['title'])}</b><br><span class='muted'>{e(subj)} · {e(c['purpose'][:60])}</span><br><span class='muted' style='font-size:11.5px'>{e(', '.join(json.loads(c.get('modules_json') or 'null') or DEFAULT_MODULES))}</span></td><td class='muted'>{c['created_at'][:16]}</td>"
                    f"<td><span class='st {st}'>{e(st)}</span><br><span class='muted'>{n} {u['findings']}</span></td><td class='actions'>{run_btn} {links} <a class='btn sm ghost' href='/log/{c['id']}?lang={lang}'>{u['log']}</a></td></tr>")
    table = f"<table><tr><th>{u['title']}</th><th>{u['created']}</th><th>{u['status']}</th><th></th></tr>{''.join(rows)}</table>" if rows else f"<p class='muted'>{u['empty']}</p>"
    return page(lang, form + f"<h2>{u['cases']}</h2><div class='card'>{table}</div>")


SCENE_ICONS = [
    # épület
    "<path d='M8 44V14l14-6 14 6v30M14 22h4M14 30h4M22 22h4M22 30h4M30 22h4M30 30h4M18 44v-8h8v8'/>",
    # dokumentum
    "<path d='M12 6h18l8 8v30H12zM30 6v8h8M18 24h14M18 32h14M18 40h8'/>",
    # földgömb
    "<circle cx='24' cy='26' r='16'/><path d='M8 26h32M24 10c6 6 6 26 0 32M24 10c-6 6-6 26 0 32M12 16c8 3 16 3 24 0M12 36c8-3 16-3 24 0'/>",
    # személy
    "<circle cx='24' cy='16' r='8'/><path d='M8 44c0-9 7-14 16-14s16 5 16 14'/>",
    # pajzs
    "<path d='M24 6l14 5v12c0 9-6 16-14 21-8-5-14-12-14-21V11z'/><path d='M17 25l5 5 9-10'/>",
    # háló
    "<circle cx='12' cy='14' r='4'/><circle cx='36' cy='14' r='4'/><circle cx='24' cy='38' r='4'/><path d='M15 16l7 19M33 16l-7 19M16 14h16'/>",
]
WORKING = {"hu": ("Már dolgozunk rajta…", "Nyilvános forrásokat kérdezünk le, majd Claude rendszerezi és összefoglalja. Ez 1–3 perc."),
           "en": ("We're working on it…", "Querying public sources, then Claude organises and summarises them. This takes 1–3 minutes.")}
SCENE_CSS = """
.scene{position:relative;height:150px;margin:18px auto 8px;max-width:640px;display:grid;grid-template-columns:repeat(6,1fr);align-items:center;justify-items:center}
.scene svg.ic{width:48px;height:48px;fill:none;stroke:#C5CDD4;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;transition:stroke .4s}
.scene .ic{animation:glow 6s infinite}.scene .ic:nth-child(2){animation-delay:1s}.scene .ic:nth-child(3){animation-delay:2s}.scene .ic:nth-child(4){animation-delay:3s}.scene .ic:nth-child(5){animation-delay:4s}.scene .ic:nth-child(6){animation-delay:5s}
@keyframes glow{0%,14%{stroke:#C5CDD4}6%{stroke:#2F6F8F}}
.lens{position:absolute;top:22px;left:calc(8.333% - 43px);width:86px;height:86px;animation:sweep 6s ease-in-out infinite;filter:drop-shadow(0 6px 10px rgba(47,111,143,.18))}
@keyframes sweep{0%,100%{left:calc(8.333% - 43px);transform:rotate(0)}16%{left:calc(25% - 43px);transform:rotate(-4deg)}33%{left:calc(41.667% - 43px);transform:rotate(3deg)}50%{left:calc(58.333% - 43px);transform:rotate(-3deg)}66%{left:calc(75% - 43px);transform:rotate(4deg)}83%{left:calc(91.667% - 43px);transform:rotate(-2deg)}}
.lens circle.g{fill:rgba(255,255,255,.55);stroke:#2F6F8F;stroke-width:3}.lens path{stroke:#2F6F8F;stroke-width:5;stroke-linecap:round}.lens .sh{fill:none;stroke:#fff;stroke-width:2.5;opacity:.8}
.working{text-align:center}.working h3{font-weight:500;font-size:20px;margin:6px 0 4px;letter-spacing:-.01em}.working p{color:var(--muted);margin:0 0 14px;font-size:13.5px}
.dots span{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--accent);margin:0 3px;animation:b 1.4s infinite}.dots span:nth-child(2){animation-delay:.2s}.dots span:nth-child(3){animation-delay:.4s}
@keyframes b{0%,80%,100%{opacity:.25;transform:translateY(0)}40%{opacity:1;transform:translateY(-4px)}}
@media (max-width:700px){.scene{max-width:100%}.scene svg.ic{width:36px;height:36px}.lens{width:64px;height:64px;top:32px}}
"""


def run_page(lang: str, cid: str) -> str:
    u = UI[lang]
    c = STORE.get_case(cid)
    lines = "\n".join(PROGRESS.get(cid, []))
    done = cid not in RUNNING
    refresh = "" if done else f"""<script>
(function poll(){{fetch('/api/status/{cid}').then(r=>r.json()).then(d=>{{
  var pre=document.getElementById('plog'); if(pre) pre.textContent=d.log.join('\\n')||'…';
  if(!d.running){{location.replace(d.report?'/report/{cid}?lang={lang}':'/progress/{cid}?lang={lang}');return;}}
  setTimeout(poll,3000);}}).catch(()=>setTimeout(poll,4000));}})();
</script>"""
    icons = "".join(f"<svg class='ic' viewBox='0 0 48 48'>{ic}</svg>" for ic in SCENE_ICONS)
    lens = ("<svg class='lens' viewBox='0 0 100 100'><circle class='g' cx='40' cy='40' r='27'/><path class='sh' d='M26 32c3-6 8-10 15-11'/>"
            "<path d='M60 60l26 26'/></svg>")
    title, sub = WORKING[lang]
    if done:
        scene = f"<div class='working'><h3>{'Kész' if lang == 'hu' else 'Done'} ✓</h3><p>{html.escape(c['title'])}</p>" + \
                (f"<p><a class='btn' href='/report/{cid}?lang={lang}'>{u['open']}</a></p>" if c.get("report_path") else "") + "</div>"
    else:
        scene = f"<div class='working'><div class='scene'>{icons}{lens}</div><h3>{title}</h3><p>{sub}</p><div class='dots'><span></span><span></span><span></span></div></div>"
    body = f"""{refresh}<style>{SCENE_CSS}</style><p><a href="/?lang={lang}">{u['back']}</a></p><h2>{html.escape(c['title'])}</h2><div class="card">{scene}
<details style="margin-top:18px"><summary class="muted" style="cursor:pointer;font-size:12.5px">{'technikai napló' if lang == 'hu' else 'technical log'}</summary><pre id="plog">{html.escape(lines) or '…'}</pre></details></div>"""
    return page(lang, body)


def report_page(lang: str, cid: str) -> str:
    c = STORE.get_case(cid)
    fs = STORE.get_findings(cid)
    run_id = fs[-1]["run_id"] if fs else "-"
    fs = [f for f in fs if f["run_id"] == run_id]
    ql = STORE.get_query_log(cid, run_id)
    rp = c.get("report_path")
    sm = STORE.get_summary(cid, run_id) or STORE.get_summary(cid) or {}
    summary, backend = sm.get("summary_md") or "_–_", sm.get("backend") or "-"
    from .report import CSS as RCSS
    inner = render_html(c, c["lang"], fs, ql, summary, backend, run_id, c["updated_at"][:16], embed=True)
    u = UI[lang]
    pdf = f"/file?p={urllib.parse.quote(str(Path(rp).with_suffix('.pdf')))}" if rp else "#"
    refine = ""
    idf = [f for f in fs if f["category"] == "identity"]
    if idf:
        ask = sorted({a for f in idf for a in f.get("data", {}).get("ask", [])}, key=["tax_id", "reg_number", "location", "birth_year", "employer"].index)
        tg = c["target"]
        fields = "".join(f"<div><label>{html.escape(t(lang, k) if k != 'tax_id' else UI[lang]['tax'])}</label><input type='text' name='{k}' value='{html.escape(getattr(tg, k, ''))}'></div>" for k in ask)
        cands = ", ".join(x for f in idf for x in f.get("data", {}).get("candidates", []))
        refine = f"""<div class='grey' style='margin:0 0 22px'><div class='gt'>{t(lang,'refine_title')}</div><p class='gh'>{t(lang,'refine_hint')} {html.escape(' · '.join(f['summary'] for f in idf))}</p>
        {f"<p class='gh'>{html.escape(cands)}</p>" if cands else ''}<form method='post' action='/refine/{cid}'><input type='hidden' name='ui_lang' value='{lang}'><div class='row'>{fields}</div>
        <button class='btn sm'>{t(lang,'refine_btn')}</button> &nbsp; <a class='btn sm ghost' href='/split/{cid}?lang={lang}'>{t(lang,'split_btn')}</a></form></div>"""
    kids = STORE.children(cid)
    if kids:
        refine += f"<div class='card' style='margin-bottom:22px'><h2 style='margin-top:0'>{t(lang,'children')}</h2><ul>" + "".join(
            f"<li><a href='/report/{k['id']}?lang={lang}'>{html.escape(k['title'])}</a> <span class='st {k['status']}'>{html.escape('running' if k['id'] in RUNNING else k['status'])}</span></li>" for k in kids) + "</ul></div>"
    if c.get("parent_id"):
        refine = f"<p class='muted'>{t(lang,'parent')}: <a href='/report/{c['parent_id']}?lang={lang}'>{c['parent_id']}</a></p>" + refine
    body = f"<p><a href='/?lang={lang}'>{u['back']}</a> &nbsp; <a class='btn sm' href='{pdf}' target='_blank'>{u['pdf']}</a> <a class='btn sm ghost' href='/run/{cid}?lang={lang}'>{u['rerun']}</a> <a class='btn sm danger' href='/delete/{cid}?lang={lang}' onclick=\"return confirm('{u['confirm_del']}')\">{u['delete']}</a></p>{refine}<style>{RCSS}</style><div class='page' style='padding:0'>{inner}</div>"
    return page(lang, body, c["title"])


def log_page(lang: str, cid: str) -> str:
    u = UI[lang]
    c = STORE.get_case(cid)
    rows = "".join(f"<tr><td class='muted'>{q['ts'][11:19]}</td><td>{html.escape(q['source'])}</td><td>{html.escape(q['action'])}</td><td class='muted' style='font-size:12px;word-break:break-all'>{html.escape((q['request'] or '')[:160])}</td><td>{html.escape(q['status'] or '')}</td><td>{q['duration_ms']}</td><td>{'' if q['result_count'] is None else q['result_count']}</td><td class='muted'>{html.escape((q['error'] or '')[:80])}</td></tr>" for q in STORE.get_query_log(cid))
    body = f"<p><a href='/?lang={lang}'>{u['back']}</a></p><h2>{html.escape(c['title'])} — {u['log']}</h2><div class='card'><table><tr><th>{t(lang,'time')}</th><th>{t(lang,'source')}</th><th>{t(lang,'action')}</th><th>{t(lang,'request')}</th><th>{t(lang,'status')}</th><th>ms</th><th>{t(lang,'count')}</th><th>error</th></tr>{rows}</table></div>"
    return page(lang, body)


def audit_page(lang: str) -> str:
    u = UI[lang]
    rows = "".join(f"<tr><td class='muted'>{e['ts'][:19]}</td><td>{html.escape(e['actor'] or '')}</td><td>{html.escape(e['event'])}</td><td>{html.escape(e['case_id'] or '')}</td><td class='muted'>{html.escape(e['detail'] or '')}</td></tr>" for e in STORE.get_audit())
    return page(lang, f"<p><a href='/?lang={lang}'>{u['back']}</a></p><h2>{u['audit']}</h2><div class='card'><table>{rows}</table></div>")


def _start(cid: str) -> None:
    if cid in RUNNING:
        return
    RUNNING.add(cid)
    PROGRESS[cid] = []

    def work():
        try:
            run_case(STORE, cid, lambda s: PROGRESS[cid].append(s))
        except Exception as e:  # noqa: BLE001
            PROGRESS[cid].append(f"ERROR: {e}")
            STORE.set_status(cid, "error")
        finally:
            RUNNING.discard(cid)
    threading.Thread(target=work, daemon=True).start()


class H(BaseHTTPRequestHandler):
    def _send(self, body: str | bytes, ctype: str = "text/html; charset=utf-8", code: int = 200) -> None:
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(b)

    def _redir(self, loc: str) -> None:
        self.send_response(303)
        self.send_header("Location", loc)
        self.end_headers()

    def log_message(self, *a):  # csendes
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        lang = qs.get("lang", ["hu"])[0]
        lang = lang if lang in ("hu", "en") else "hu"
        p = u.path
        try:
            if p == "/":
                return self._send(index(lang, qs.get("err", [""])[0]))
            if p == "/audit":
                return self._send(audit_page(lang))
            if p.startswith("/run/"):
                cid = p[5:]
                if STORE.get_case(cid):
                    _start(cid)
                return self._redir(f"/progress/{cid}?lang={lang}")
            if p.startswith("/split/"):
                cid = p[7:]
                if STORE.get_case(cid) and cid not in RUNNING:
                    RUNNING.add(cid)
                    PROGRESS[cid] = []

                    def work(cid=cid):
                        try:
                            from .splitter import split_case
                            split_case(STORE, cid, lambda s: PROGRESS[cid].append(s))
                        except Exception as e:  # noqa: BLE001
                            PROGRESS[cid].append(f"ERROR: {e}")
                        finally:
                            RUNNING.discard(cid)
                    threading.Thread(target=work, daemon=True).start()
                return self._redir(f"/progress/{cid}?lang={lang}")
            if p.startswith("/progress/"):
                return self._send(run_page(lang, p[10:]))
            if p.startswith("/report/"):
                return self._send(report_page(lang, p[8:]))
            if p.startswith("/log/"):
                return self._send(log_page(lang, p[5:]))
            if p.startswith("/delete/"):
                STORE.delete_case(p[8:])
                return self._redir(f"/?lang={lang}")
            if p == "/file":
                fp = Path(qs.get("p", [""])[0]).resolve()
                from .core import REPORT_DIR
                if REPORT_DIR.resolve() in fp.parents and fp.exists():
                    ct = {"pdf": "application/pdf", "html": "text/html; charset=utf-8", "md": "text/plain; charset=utf-8"}.get(fp.suffix[1:], "application/octet-stream")
                    return self._send(fp.read_bytes(), ct)
                return self._send("not found", "text/plain", 404)
            if p.startswith("/api/status/"):
                cid = p[12:]
                c = STORE.get_case(cid) or {}
                return self._send(json.dumps({"running": cid in RUNNING, "report": bool(c.get("report_path")), "log": PROGRESS.get(cid, [])[-40:]}, ensure_ascii=False), "application/json")
            if p == "/api/cases":
                return self._send(json.dumps(STORE.list_cases(), ensure_ascii=False, default=str), "application/json")
            return self._send("not found", "text/plain", 404)
        except Exception as e:  # noqa: BLE001
            return self._send(f"error: {html.escape(str(e))}", "text/plain", 500)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8")).items()}
        lang = form.get("ui_lang", "hu")
        if u.path == "/new":
            try:
                tg = Target(company=form.get("company", "").strip(), tax_id=form.get("tax_id", "").strip(), country=form.get("country", "HU").strip() or "HU",
                            domain=form.get("domain", "").strip(), person=form.get("person", "").strip(), email=form.get("email", "").strip(),
                            username=form.get("username", "").strip(), phone=form.get("phone", "").strip(),
                            extra_keywords=[k.strip() for k in form.get("keywords", "").split(",") if k.strip()],
                            birth_year=form.get("birth_year", "").strip(), location=form.get("location", "").strip(),
                            employer=form.get("employer", "").strip(), reg_number=form.get("reg_number", "").strip())
                pc = form.get("person_checks") == "on"
                if not pc:
                    tg.person = tg.email = tg.username = tg.phone = ""
                mods = [m for m, _ in MODULES_META if form.get(f"mod_{m}") == "on"]
                if not pc:
                    mods = [m for m in mods if m not in ("person", "phone", "breach", "social", "face")]
                cid = STORE.create_case(form["title"].strip(), form["purpose"].strip(), form.get("legal_basis", "nem_szemelyes"), tg, pc,
                                        form.get("requester", "").strip(), form.get("lang", lang), mods)
            except Exception as e:  # noqa: BLE001
                return self._send(index(lang, str(e), form))
            if form.get("action") == "run":
                _start(cid)
                return self._redir(f"/progress/{cid}?lang={lang}")
            return self._redir(f"/?lang={lang}")
        if u.path.startswith("/refine/"):
            cid = u.path[8:]
            c = STORE.get_case(cid)
            if not c:
                return self._send("not found", "text/plain", 404)
            tg = c["target"]
            for k in ("tax_id", "reg_number", "location", "birth_year", "employer"):
                if k in form:
                    setattr(tg, k, form[k].strip())
            STORE.update_target(cid, tg)
            _start(cid)
            return self._redir(f"/progress/{cid}?lang={lang}")
        return self._send("not found", "text/plain", 404)


def serve(port: int = 8765) -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"osint-dd GUI: http://127.0.0.1:{port}  (Ctrl+C = leállítás)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
