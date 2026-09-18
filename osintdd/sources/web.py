"""Webes és sajtóforrások – DuckDuckGo keresés (ddgs) + GDELT DOC API. Ingyenes, kulcs nélkül."""
from __future__ import annotations

import time

from ..core import Finding, Target
from ..http import Http

NEG_HU = ["csalás", "botrány", "felszámolás", "végrehajtás", "ítélet", "bíróság", "NAV", "nyomozás", "adatszivárgás", "per"]
NEG_EN = ["fraud", "lawsuit", "sanction", "investigation", "data breach", "scandal", "bankruptcy", "indictment"]
HU_REGISTRY_SITES = ["nemzeticegtar.hu", "e-cegjegyzek.hu", "ceginformacio.hu", "opten.hu", "cegvilag.hu", "kozbeszerzes.hu", "birosag.hu", "nav.gov.hu"]


def _ddg(http: Http, source: str, query: str, kind: str = "text", region: str = "hu-hu", max_results: int = 10) -> list[dict]:
    started = time.time()
    try:
        from ddgs import DDGS
        with DDGS() as d:
            res = d.text(query, region=region, max_results=max_results) if kind == "text" else d.news(query, region=region, max_results=max_results)
        res = res or []
        http.log.log(source, f"ddg_{kind}", {"q": query, "region": region}, "OK", started, len(res), raw=res)
        return res
    except Exception as e:  # noqa: BLE001
        if "No results" in str(e):
            http.log.log(source, f"ddg_{kind}", {"q": query, "region": region}, "OK", started, 0)
        else:
            http.log.log(source, f"ddg_{kind}", {"q": query, "region": region}, "ERROR", started, 0, str(e))
        return []


def _neg_sev(r: dict, words: list[str]) -> str:
    txt = (r.get("title", "") + " " + r.get("body", "")).lower()
    return "low" if any(w.lower() in txt for w in words) else "info"


def _hint(r: dict, dis: list[str]) -> tuple[str, str]:
    """(prefix, severity-módosító): jelöli, ha a találat tartalmazza valamelyik pontosító adatot."""
    if not dis:
        return "", ""
    txt = (r.get("title", "") + " " + r.get("body", "")).lower()
    hits = [d for d in dis if d.lower() in txt]
    return (f"✓ {', '.join(hits)} · " if hits else "? "), ("match" if hits else "nomatch")


def run(t: Target, http: Http, log, case) -> list[Finding]:
    out: list[Finding] = []
    dis = t.disambiguators()
    subjects = [s for s in [t.company, t.domain] if s]
    if t.company and t.location:
        subjects[0] = f'"{t.company}" {t.location}'
    if case.get("person_checks") and t.person:
        subjects.append(f'"{t.person}" ' + " ".join(x for x in [t.company, t.employer, t.location] if x))
    subjects += t.extra_keywords

    for s in subjects:
        # 1) általános találatok
        for r in _ddg(http, "web", s, "text")[:8]:
            if not (r.get("title") or "").strip():
                continue
            pre, m = _hint(r, dis)
            out.append(Finding("ddg", "web", pre + r.get("title", "")[:150], r.get("body", "")[:400], url=r.get("href", ""), severity="info", data={"query": s, "disambig": m}))
        time.sleep(1.0)
        # 2) negatív hírek
        neg = f'{s} ({" OR ".join(NEG_HU[:6])})'
        for r in _ddg(http, "web_negative", neg, "text")[:8]:
            out.append(Finding("ddg", "web", f"[negatív kulcsszó] {r.get('title','')[:140]}", r.get("body", "")[:400], url=r.get("href", ""), severity=_neg_sev(r, NEG_HU), data={"query": neg}))
        time.sleep(1.0)
        # 3) hírek
        for r in _ddg(http, "news", s, "news")[:8]:
            out.append(Finding("ddg_news", "web", f"[hír {str(r.get('date',''))[:10]}] {r.get('title','')[:140]}", r.get("body", "")[:400], url=r.get("url", ""), severity="info", data={"source": r.get("source"), "query": s}))
        time.sleep(1.0)

    # 4) magyar cégadat-oldalak találatai (snippet szintű, ingyenes)
    if t.company:
        q = f'"{t.company}" (' + " OR ".join(f"site:{d}" for d in HU_REGISTRY_SITES) + ")"
        for r in _ddg(http, "hu_registry_search", q, "text", max_results=10)[:10]:
            out.append(Finding("ddg_registry", "company", f"[cégadat oldal] {r.get('title','')[:140]}", r.get("body", "")[:400], url=r.get("href", ""), severity="info", data={"query": q}))
        time.sleep(1.0)
        # angol negatív
        neg = f'"{t.company}" ({" OR ".join(NEG_EN[:5])})'
        for r in _ddg(http, "web_negative_en", neg, "text", region="us-en")[:6]:
            out.append(Finding("ddg", "web", f"[negatív kulcsszó EN] {r.get('title','')[:140]}", r.get("body", "")[:400], url=r.get("href", ""), severity=_neg_sev(r, NEG_EN), data={"query": neg}))

    # 5) GDELT (globális hírmonitor) – max 1 kérés / 5 s
    for s in [x for x in [t.company] + ([t.person] if case.get("person_checks") else []) if x][:2]:
        time.sleep(5.2)
        params = {"query": f'"{s}"', "mode": "artlist", "format": "json", "maxrecords": 15, "timespan": "3y", "sort": "datedesc"}
        body, r = http.get("gdelt", "https://api.gdeltproject.org/api/v2/doc/doc", params=params, expect_json=True)
        if r is not None and r.status_code == 429:
            time.sleep(8)
            body, r = http.get("gdelt", "https://api.gdeltproject.org/api/v2/doc/doc", params=params, expect_json=True)
        for a in (body or {}).get("articles", []) if isinstance(body, dict) else []:
            out.append(Finding("gdelt", "web", f"[GDELT {a.get('seendate','')[:8]} {a.get('sourcecountry','')}] {a.get('title','')[:140]}",
                               f"forrás: {a.get('domain')} · nyelv: {a.get('language')}", url=a.get("url", ""), severity="info", data={"query": s}))
    return out
