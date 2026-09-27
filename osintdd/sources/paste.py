"""Paste-oldalak – szürke zóna. A psbdmp.ws index 2026-ban megszűnt („That's all folks"), ezért keresőmotoron át
keresünk a nagy paste-oldalakon (pastebin, paste.ee, justpaste.it, rentry, controlc, pastes.io, ghostbin, dpaste, hastebin).
Kulcs nélkül. IntelX kulccsal (breach modul) a paste-archívumok is bejönnek."""
from __future__ import annotations

import time

from ..core import Finding, Target
from ..http import Http
from .web import _ddg

PASTE_SITES = ["pastebin.com", "paste.ee", "justpaste.it", "rentry.co", "controlc.com", "pastes.io", "ghostbin.co", "dpaste.org", "dpaste.com", "hastebin.com", "pastelink.net", "throwbin.io"]


def run(t: Target, http: Http, log, case) -> list[Finding]:
    out: list[Finding] = []
    subjects = [s for s in [t.company, t.domain] if s]
    if case.get("person_checks"):
        subjects += [s for s in [t.email, t.username, t.person] if s]
    sites = " OR ".join(f"site:{d}" for d in PASTE_SITES)
    for s in subjects[:5]:
        q = f'"{s}" ({sites})'
        res = _ddg(http, "paste_search", q, "text", region="us-en", max_results=15)
        if res:
            for r in res[:10]:
                out.append(Finding("paste_search", "paste", f"Paste-találat ({s}): {r.get('title','')[:120]}", r.get("body", "")[:300], url=r.get("href", ""), severity="medium", data={"query": s}))
        else:
            out.append(Finding("paste_search", "paste", f"Nincs paste-találat: {s}", f"{len(PASTE_SITES)} paste-oldal keresőmotoron át", severity="info", data={"query": s}))
        time.sleep(1.2)
    return out
