"""Helyi webes felület – stdlib http.server, csak 127.0.0.1. Kétnyelvű (hu/en), letisztult, légies. sadrobot."""
from __future__ import annotations

import html
import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import DEFAULT_MODULES, LEGAL_BASES, MODULES_META, Store, Target
from .i18n import LEGAL_LABEL, t
from .graph import Graph
from .report import render_html
from .runner import run_case

from .core import BASE_DIR as _DATA_DIR

import secrets as _secrets

AUTH_MODE = os.environ.get("OSINTDD_AUTH", "local")          # local (127.0.0.1, nincs belépés) | proxy (oauth2-proxy / passkey a Caddy mögött)
PROXY_EMAIL_HEADER = "X-Auth-Request-Email"
PROXY_SECRET_HEADER = "X-Osintdd-Proxy"


# böngészőfül-ikon: a sadrobot robot nagyító-jelvénnyel (sadrobot-infra/tools/make_favicons.py)
FAVICON = "data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%2212 8 196 196%22 width=%22200%22 height=%22200%22%3E%3Cg%3E%0A  %3Crect x=%2296%22 y=%2234%22 width=%228%22 height=%2230%22 rx=%222%22 fill=%22%230b1f4d%22/%3E%0A  %3Ccircle cx=%22100%22 cy=%2226%22 r=%2212%22 fill=%22%23ff6048%22/%3E%0A  %3Cellipse cx=%22100%22 cy=%2266%22 rx=%2224%22 ry=%2211%22 fill=%22%230b1f4d%22/%3E%0A  %3Crect x=%2224%22 y=%2292%22 width=%2230%22 height=%2244%22 rx=%2215%22 fill=%22%230b1f4d%22/%3E%0A  %3Crect x=%22146%22 y=%2292%22 width=%2230%22 height=%2244%22 rx=%2215%22 fill=%22%230b1f4d%22/%3E%0A  %3Crect x=%2232%22 y=%2297%22 width=%224.5%22 height=%2234%22 rx=%222.2%22 fill=%22%2312e6f5%22/%3E%0A  %3Crect x=%22163.5%22 y=%2297%22 width=%224.5%22 height=%2234%22 rx=%222.2%22 fill=%22%2312e6f5%22/%3E%0A  %3Crect x=%2242%22 y=%2262%22 width=%22116%22 height=%2292%22 rx=%2240%22 fill=%22%230b1f4d%22/%3E%0A  %3Crect x=%2258%22 y=%2280%22 width=%2284%22 height=%2256%22 rx=%2222%22 fill=%22%230b1f4d%22 stroke=%22%23fff%22 stroke-width=%223.2%22/%3E%0A  %3Cpath d=%22M120 96c-6 8-9 12-9 17a9 9 0 0 0 18 0c0-5-3-9-9-17z%22 fill=%22%2312e6f5%22/%3E%0A  %3Crect x=%2272%22 y=%22158%22 width=%2256%22 height=%2224%22 rx=%2212%22 fill=%22%230b1f4d%22/%3E%0A  %3Crect x=%2291%22 y=%22163%22 width=%225%22 height=%2213%22 rx=%222.5%22 fill=%22%2312e6f5%22/%3E%0A  %3Crect x=%22104%22 y=%22163%22 width=%225%22 height=%2213%22 rx=%222.5%22 fill=%22%2312e6f5%22/%3E%3C/g%3E%3Cg transform=%22translate(150 150) scale(1.18) translate(-150 -150)%22%3E%3Ccircle cx=%22150%22 cy=%22150%22 r=%2247%22 fill=%22%23fff%22/%3E%3Ccircle cx=%22150%22 cy=%22150%22 r=%2241%22 fill=%22%235b3fd0%22/%3E%3Ccircle cx=%22145%22 cy=%22145%22 r=%2215%22 fill=%22none%22 stroke=%22%23fff%22 stroke-width=%227%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22/%3E%3Cpath d=%22M156 156 L170 170%22 fill=%22none%22 stroke=%22%23fff%22 stroke-width=%227%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22/%3E%3C/g%3E%3C/svg%3E"

def _read_secret(env: str, default_file: str) -> str:
    v = os.environ.get(env, "")
    if v:
        return v.strip()
    for cand in [os.environ.get(env + "_FILE"), default_file]:
        if cand and os.path.exists(cand):
            return Path(cand).read_text().strip()
    return ""


PROXY_SECRET = _read_secret("OSINTDD_PROXY_SECRET", "/run/secrets/osintdd_proxy_secret")


def _allowed_emails() -> set[str]:
    out = {e.strip().lower() for e in os.environ.get("OSINTDD_ALLOWED_EMAILS", "").split(",") if e.strip()}
    f = os.environ.get("OSINTDD_ALLOWED_EMAILS_FILE", "/etc/osintdd/emails.txt")
    if os.path.exists(f):
        out |= {l.strip().lower() for l in Path(f).read_text().splitlines() if l.strip() and not l.startswith("#")}
    return out


ALLOWED_EMAILS = _allowed_emails()
_BUILD_FILE = Path(__file__).parent / "BUILD"
if not os.environ.get("OSINTDD_BUILD") and _BUILD_FILE.exists():
    os.environ["OSINTDD_BUILD"] = _BUILD_FILE.read_text().strip()

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

FONT_CSS = "".join(
    f"@font-face{{font-family:Figtree;font-weight:{w};font-display:swap;src:url(/static/fonts/figtree-{sub}-{w}-normal.woff2) format('woff2')}}"
    for sub in ("latin", "latin-ext") for w in (400, 600, 800))

CSS = FONT_CSS + """
:root{--bg:#f5f8fc;--bg2:#eaf1f9;--card:#fff;--ink:#0b1f4d;--ink2:#46587a;--muted:#7686a2;--line:#dde6f1;--accent:#0a8aa4;--accent-soft:#e2f5f9;
--warn:#c2412c;--warn-soft:#fdebe7;--blue:#2451b8;--blue-soft:#e6eefc;--cyan:#12c8e6;--amber:#b7791f;--amber-soft:#fff4e0;
--shadow:0 1px 2px rgba(11,31,77,.05),0 10px 30px -18px rgba(11,31,77,.25);--font:Figtree,"Avenir Next","Segoe UI",system-ui,-apple-system,sans-serif;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#07122b;--bg2:#0c1a38;--card:#0e1c3d;--ink:#eaf2fb;--ink2:#aebcd3;--muted:#8193ae;--line:#1c2e55;--accent:#5ad1e8;--accent-soft:#0f3345;
--warn:#ff8a73;--warn-soft:#3a1d1a;--blue:#8fb0ff;--blue-soft:#17264a;--amber:#f0b25a;--amber-soft:#3a2a10;--shadow:0 1px 2px rgba(0,0,0,.3),0 12px 32px -18px rgba(0,0,0,.7);color-scheme:dark}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15.5px/1.6 var(--font);-webkit-font-smoothing:antialiased;padding:0 24px}
a{color:var(--accent);text-decoration:none}.wrap{max-width:1100px;margin:0 auto;padding:0 0 72px}
nav{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-block:18px;border-bottom:1px solid var(--line);margin-bottom:36px}
.logo{display:inline-flex;align-items:center;gap:10px;color:var(--ink);text-decoration:none}.logo img{width:34px;height:34px;border-radius:9px;background:#fff;padding:2px}
.logo b{font-weight:800;font-size:19px;letter-spacing:-.01em}.logo span span{font-size:12.5px;color:var(--muted);font-weight:400}
.langs{display:flex;align-items:center;gap:8px}.langs a{font:600 13px var(--font);color:var(--ink2);padding:5px 10px;border-radius:8px;text-decoration:none}
.langs a:hover{background:var(--bg2);color:var(--ink)}.langs a.on{background:var(--ink);color:var(--bg)}
h2{font-size:22px;font-weight:800;letter-spacing:-.02em;margin:36px 0 14px}h3{font-weight:700;font-size:15px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:26px 28px;box-shadow:var(--shadow)}
label{display:block;font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600;margin:0 0 5px}
input[type=text],select,textarea{width:100%;border:1px solid var(--line);border-radius:10px;padding:10px 12px;font:inherit;font-size:14.5px;background:var(--card);color:var(--ink);outline:none;transition:border .15s,box-shadow .15s}
input:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px 20px;margin-bottom:16px}
.person{border-top:1px dashed var(--line);margin-top:8px;padding-top:18px}.person .row{opacity:.55;transition:opacity .2s}.person.on .row{opacity:1}
.chk{display:flex;align-items:center;gap:10px;font-size:14px;margin:6px 0 14px}.chk input{width:16px;height:16px;accent-color:var(--accent)}
.btn{display:inline-block;border:1px solid var(--ink);background:var(--ink);color:var(--bg);border-radius:999px;padding:9px 20px;font:600 14px var(--font);cursor:pointer;transition:opacity .15s,transform .1s}
.btn:hover{opacity:.9}.btn:active{transform:translateY(1px)}.btn.ghost{background:transparent;color:var(--ink)}.btn.sm{padding:5px 12px;font-size:12.5px}
.btn.danger{border-color:var(--warn);color:var(--warn);background:transparent}
.hint{font-size:12.5px;color:var(--muted);margin:6px 0 0}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:middle}
th{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}
.st{font-size:11px;letter-spacing:.06em;text-transform:uppercase;font-weight:700;padding:3px 10px;border-radius:999px;background:var(--bg2);color:var(--ink2)}
.st.done{background:var(--accent-soft);color:var(--accent)}.st.running{background:var(--amber-soft);color:var(--amber)}.st.error{background:var(--warn-soft);color:var(--warn)}
.muted{color:var(--muted);font-size:13px}footer{margin-top:60px;color:var(--muted);font-size:12.5px;text-align:center;letter-spacing:.02em;border-top:1px solid var(--line);padding-top:22px}
pre{background:var(--bg2);border-radius:10px;padding:14px;font-size:12.5px;overflow:auto;max-height:280px;color:var(--ink)}.actions a{margin-right:8px}
.err{background:var(--warn-soft);color:var(--warn);border-radius:10px;padding:10px 14px;margin-bottom:14px;font-size:13.5px}
.mods{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:8px 18px;margin:6px 0 4px}.mods label{display:flex;align-items:center;gap:9px;font-size:13.5px;text-transform:none;letter-spacing:0;color:var(--ink);font-weight:400;margin:0}.mods input{accent-color:var(--accent);width:15px;height:15px}
.grey{border:1px dashed var(--amber);background:var(--amber-soft);border-radius:12px;padding:14px 16px;margin-top:14px}.grey .gt{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--amber);font-weight:700;margin-bottom:4px}.grey .gh{font-size:12.5px;color:var(--ink2);margin:0 0 8px}
details summary{cursor:pointer}
@media (max-width:640px){body{padding:0 16px}.card{padding:18px}nav{flex-wrap:wrap}}
"""


def page(lang: str, body: str, title: str = "") -> str:
    u = UI[lang]
    other = "en" if lang == "hu" else "hu"
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title or t(lang,'app'))}</title><link rel="icon" type="image/svg+xml" href="{FAVICON}"><style>{CSS}</style></head><body><div class="wrap">
<nav><a class="logo" href="/?lang={lang}"><img src="/static/sadrobot.png" alt="sadrobot"><span style="display:flex;flex-direction:column;line-height:1.2"><b>{html.escape(t(lang,'app'))}</b><span>{html.escape(t(lang,'tagline'))}</span></span></a>
<div class="langs"><a href="/audit?lang={lang}">{u['audit']}</a><a class="{'on' if lang=='hu' else ''}" href="?lang=hu">HU</a><a class="{'on' if lang=='en' else ''}" href="?lang=en">EN</a></div></nav>
{body}
<footer><img src="/static/sadrobot.png" alt="sadrobot" width="28" height="28" style="border-radius:7px;vertical-align:middle;margin-right:8px;background:#fff">{html.escape(t(lang,'app'))} · {html.escape(t(lang,'by'))} · © 2026 sadrobot<br><span style="opacity:.8">{html.escape(u['notes'])}</span><br><span style="opacity:.6">data: {html.escape(str(_DATA_DIR))}{(' · build ' + html.escape(os.environ.get('OSINTDD_BUILD',''))) if os.environ.get('OSINTDD_BUILD') else ''}</span></footer></div></body></html>"""


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
                    f"<td><span class='st {st}'>{e(st)}</span><br><span class='muted'>{n} {u['findings']}</span></td><td class='actions'>{run_btn} {links} <a class='btn sm ghost' href='/log/{c['id']}?lang={lang}'>{u['log']}</a> <a class='btn sm ghost' href='/graph/{c['id']}?lang={lang}'>{t(lang,'graph_link')}</a></td></tr>")
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
.scene svg.ic{width:48px;height:48px;fill:none;stroke:var(--line);stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;transition:stroke .4s}
.scene .ic{animation:glow 6s infinite}.scene .ic:nth-child(2){animation-delay:1s}.scene .ic:nth-child(3){animation-delay:2s}.scene .ic:nth-child(4){animation-delay:3s}.scene .ic:nth-child(5){animation-delay:4s}.scene .ic:nth-child(6){animation-delay:5s}
@keyframes glow{0%,14%{stroke:var(--line)}6%{stroke:var(--accent)}}
.lens{position:absolute;top:22px;left:calc(8.333% - 43px);width:86px;height:86px;animation:sweep 6s ease-in-out infinite;filter:drop-shadow(0 6px 10px rgba(11,31,77,.18))}
@keyframes sweep{0%,100%{left:calc(8.333% - 43px);transform:rotate(0)}16%{left:calc(25% - 43px);transform:rotate(-4deg)}33%{left:calc(41.667% - 43px);transform:rotate(3deg)}50%{left:calc(58.333% - 43px);transform:rotate(-3deg)}66%{left:calc(75% - 43px);transform:rotate(4deg)}83%{left:calc(91.667% - 43px);transform:rotate(-2deg)}}
.lens circle.g{fill:rgba(255,255,255,.55);stroke:var(--accent);stroke-width:3}.lens path{stroke:var(--accent);stroke-width:5;stroke-linecap:round}.lens .sh{fill:none;stroke:#fff;stroke-width:2.5;opacity:.8}
.working{text-align:center}.working h3{font-weight:800;font-size:22px;letter-spacing:-.02em;margin:6px 0 4px;letter-spacing:-.01em}.working p{color:var(--muted);margin:0 0 14px;font-size:13.5px}
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
    body = f"<p><a href='/?lang={lang}'>{u['back']}</a> &nbsp; <a class='btn sm' href='{pdf}' target='_blank'>{u['pdf']}</a> <a class='btn sm ghost' href='/run/{cid}?lang={lang}'>{u['rerun']}</a> <a class='btn sm ghost' href='/graph/{cid}?lang={lang}'>{t(lang,'graph_link')}</a> <a class='btn sm danger' href='/delete/{cid}?lang={lang}' onclick=\"return confirm('{u['confirm_del']}')\">{u['delete']}</a></p>{refine}<style>{RCSS}</style><div class='page' style='padding:0'>{inner}</div>"
    return page(lang, body, c["title"])


def log_page(lang: str, cid: str) -> str:
    u = UI[lang]
    c = STORE.get_case(cid)
    rows = "".join(f"<tr><td class='muted'>{q['ts'][11:19]}</td><td>{html.escape(q['source'])}</td><td>{html.escape(q['action'])}</td><td class='muted' style='font-size:12px;word-break:break-all'>{html.escape((q['request'] or '')[:160])}</td><td>{html.escape(q['status'] or '')}</td><td>{q['duration_ms']}</td><td>{'' if q['result_count'] is None else q['result_count']}</td><td class='muted'>{html.escape((q['error'] or '')[:80])}</td></tr>" for q in STORE.get_query_log(cid))
    body = f"<p><a href='/?lang={lang}'>{u['back']}</a></p><h2>{html.escape(c['title'])} — {u['log']}</h2><div class='card'><table><tr><th>{t(lang,'time')}</th><th>{t(lang,'source')}</th><th>{t(lang,'action')}</th><th>{t(lang,'request')}</th><th>{t(lang,'status')}</th><th>ms</th><th>{t(lang,'count')}</th><th>error</th></tr>{rows}</table></div>"
    return page(lang, body)


def graph_page(lang: str, cid: str) -> str:
    u = UI[lang]
    c = STORE.get_case(cid)
    g = Graph(STORE)
    e = html.escape
    queue = g.review_queue(cid)
    decided = g.review_queue(cid, "accepted") + g.review_queue(cid, "rejected")
    rows = ""
    for q in queue:
        rows += (f"<tr><td><b>{q['score']:.0f}%</b></td><td>{e(q['a_schema'])}: {e(q['a_caption'])}</td><td>{e(q['b_schema'])}: {e(q['b_caption'])}</td><td class='muted'>{e(q['reason'] or '')}</td>"
                 f"<td><a class='btn sm' href='/graph/{cid}/decide/{q['id']}/1?lang={lang}'>{t(lang,'accept')}</a> <a class='btn sm ghost' href='/graph/{cid}/decide/{q['id']}/0?lang={lang}'>{t(lang,'reject')}</a></td></tr>")
    review = f"<table><tr><th>score</th><th>A</th><th>B</th><th></th><th></th></tr>{rows}</table>" if rows else f"<p class='muted'>{t(lang,'no_review')}</p>"
    dec = "".join(f"<li class='muted'>{e(q['a_caption'])} ≟ {e(q['b_caption'])} → <b>{e(q['status'])}</b> ({e(q['decided_by'] or '')}, {e((q['decided_at'] or '')[:16])})</li>" for q in decided)
    ents = ""
    for en in g.entities(cid):
        props = "".join(f"<div class='f' style='grid-template-columns:150px 1fr'><span class='muted' style='font-size:12px'>{e(k)}</span><div>" +
                        "".join(f"<div style='font-size:13.5px'>{e(st['value'][:160])} <span class='muted' style='font-size:11px'>[{e(st['source'])}]</span>" +
                                (f" <a href='{e(st['url'])}' target='_blank' style='font-size:11px'>↗</a>" if st.get('url') else "") + "</div>" for st in v[:12]) +
                        (f"<div class='muted' style='font-size:11px'>… +{len(v)-12}</div>" if len(v) > 12 else "") + "</div></div>" for k, v in en["properties"].items())
        links = ", ".join(l["b"] if l["a"] == en["id"] else l["a"] for l in en["links"])
        ents += (f"<details {'open' if en['is_subject'] else ''} style='margin:10px 0'><summary><b>{'★ ' if en['is_subject'] else ''}{e(en['schema'])}</b> · {e(en['caption'])} "
                 f"<span class='muted' style='font-size:12px'>{sum(len(v) for v in en['properties'].values())} állítás{(' · sameAs: ' + e(links)) if links else ''}</span></summary>{props}</details>")
    cross = g.cross_case(cid)
    cross_html = f"<h2>{t(lang,'cross')}</h2><div class='card'><ul>" + "".join(f"<li>{e(x['schema'])} {e(x['caption'])} → <a href='/graph/{x['other_case']}?lang={lang}'>{e(x['other_title'])}</a></li>" for x in cross) + "</ul></div>" if cross else ""
    body = (f"<p><a href='/report/{cid}?lang={lang}'>← {e(c['title'])}</a> &nbsp; <a class='btn sm ghost' href='/graph/{cid}/export/ftm'>{t(lang,'export_ftm')}</a> "
            f"<a class='btn sm ghost' href='/graph/{cid}/export/csv'>{t(lang,'export_csv')}</a></p><h2>{t(lang,'graph')} — {e(c['title'])}</h2><p class='muted'>{t(lang,'graph_hint')}</p>"
            f"<h2>{t(lang,'review')} <span class='muted'>({len(queue)})</span></h2><div class='card'>{review}{('<h3 class=muted style=font-size:12px>' + t(lang,'decided') + '</h3><ul>' + dec + '</ul>') if dec else ''}</div>"
            f"{cross_html}<h2>{t(lang,'graph')}</h2><div class='card'>{ents or '<p class=muted>–</p>'}</div>")
    return page(lang, body, c["title"])


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

    def _user(self) -> str | None:
        """proxy módban: az e-mail csak akkor érvényes, ha a Caddy közös titka egyezik ÉS a cím engedélyezett (fail-closed)."""
        if AUTH_MODE != "proxy":
            return os.environ.get("USER", "local")
        if not _secrets.compare_digest((self.headers.get(PROXY_SECRET_HEADER) or "").encode(), PROXY_SECRET.encode()):
            return None
        e = (self.headers.get(PROXY_EMAIL_HEADER) or "").strip().lower()
        return e if e and e in ALLOWED_EMAILS else None

    def _gate(self) -> str | None:
        user = self._user()
        if user is None:
            self._send("forbidden", "text/plain", 403)
        return user

    def do_static(self, p: str):
        fp = (Path(__file__).parent / "static" / p[8:]).resolve()
        if (Path(__file__).parent / "static").resolve() in fp.parents and fp.is_file():
            ct = {"png": "image/png", "woff2": "font/woff2", "css": "text/css"}.get(fp.suffix[1:], "application/octet-stream")
            b = fp.read_bytes()
            self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "public, max-age=604800"); self.end_headers(); self.wfile.write(b)
            return None
        return self._send("not found", "text/plain", 404)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/healthz":
            return self._send(json.dumps({"ok": True, "auth": AUTH_MODE, "encrypted": STORE.encrypted}), "application/json")
        if u.path.startswith("/static/"):
            return self.do_static(u.path)
        user = self._gate()
        if user is None:
            return None
        qs = urllib.parse.parse_qs(u.query)
        lang = qs.get("lang", ["hu"])[0]
        lang = lang if lang in ("hu", "en") else "hu"
        p = u.path
        try:
            if p == "/":
                return self._send(index(lang, qs.get("err", [""])[0]))
            if p == "/audit":
                return self._send(audit_page(lang))
            if p.startswith("/static/"):
                fp = (Path(__file__).parent / "static" / p[8:]).resolve()
                if (Path(__file__).parent / "static").resolve() in fp.parents and fp.is_file():
                    ct = {"png": "image/png", "woff2": "font/woff2", "css": "text/css"}.get(fp.suffix[1:], "application/octet-stream")
                    b = fp.read_bytes()
                    self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "public, max-age=604800"); self.end_headers(); self.wfile.write(b)
                    return None
                return self._send("not found", "text/plain", 404)
            if p.startswith("/graph/"):
                parts = p[7:].split("/")
                cid = parts[0]
                if not STORE.get_case(cid):
                    return self._send("not found", "text/plain", 404)
                if len(parts) == 4 and parts[1] == "decide":
                    Graph(STORE).decide(int(parts[2]), parts[3] == "1", "gui")
                    STORE.audit("same_as_decided", cid, f"id={parts[2]} accept={parts[3]=='1'} by=gui")
                    return self._redir(f"/graph/{cid}?lang={lang}")
                if len(parts) == 3 and parts[1] == "export":
                    g = Graph(STORE)
                    if parts[2] == "ftm":
                        b = g.export_ftm(cid).encode("utf-8")
                        self.send_response(200); self.send_header("Content-Type", "application/x-ndjson; charset=utf-8"); self.send_header("Content-Disposition", f"attachment; filename=osintdd_{cid}.ftm")
                    else:
                        b = g.export_csv(cid).encode("utf-8")
                        self.send_response(200); self.send_header("Content-Type", "text/csv; charset=utf-8"); self.send_header("Content-Disposition", f"attachment; filename=osintdd_{cid}_statements.csv")
                    self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
                    return None
                return self._send(graph_page(lang, cid))
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
        user = self._gate()
        if user is None:
            return None
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
                    mods = [m for m in mods if m not in ("person", "phone", "breach", "social", "face")]  # paste cégre is futhat
                requester = form.get("requester", "").strip() or (user if AUTH_MODE == "proxy" else "")
                cid = STORE.create_case(form["title"].strip(), form["purpose"].strip(), form.get("legal_basis", "nem_szemelyes"), tg, pc,
                                        requester, form.get("lang", lang), mods)
                STORE.audit("case_created_by", cid, requester or "-", actor=user)
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


def serve(port: int = 8765, host: str | None = None) -> None:
    host = host or os.environ.get("OSINTDD_BIND", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1") and AUTH_MODE != "proxy":
        raise SystemExit("Nem-loopback címre csak OSINTDD_AUTH=proxy módban lehet kötni (passkey-proxy mögött).")
    if AUTH_MODE == "proxy":
        if len(PROXY_SECRET) < 32:
            raise SystemExit("OSINTDD_AUTH=proxy módban kötelező az OSINTDD_PROXY_SECRET (≥32 karakter; fájl: /run/secrets/osintdd_proxy_secret).")
        if not ALLOWED_EMAILS:
            raise SystemExit("OSINTDD_AUTH=proxy módban kötelező az engedélyezett e-mail-lista (OSINTDD_ALLOWED_EMAILS vagy /etc/osintdd/emails.txt).")
    srv = ThreadingHTTPServer((host, port), H)
    print(f"osint-dd GUI: http://{host}:{port}  auth={AUTH_MODE} encrypted={STORE.encrypted}  (Ctrl+C = leállítás)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
