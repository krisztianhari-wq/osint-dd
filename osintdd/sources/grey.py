"""Szürke zónás források – csak kifejezett engedéllyel (ügyenként pipálva). Jogi egyeztetés megtörtént: 2026-09-18.

breach  : LeakCheck public (kulcs nélkül, csak forrásnevek) · HIBP / DeHashed / IntelX (ha van kulcs)
aleph   : OCCRP Aleph oknyomozó adattár (ingyenes kulcs kell: OSINTDD_ALEPH_KEY)
social  : LinkedIn / Facebook / Instagram / X / TikTok profilok keresőmotoron át (nem scraping)
face    : arcfelismerő keresők – csak kézi link (GDPR 9. cikk, kép feltöltése kézzel)
"""
from __future__ import annotations

import os
import time
from urllib.parse import quote_plus

from ..core import Finding, Target
from ..http import Http
from .web import _ddg

SOCIAL_SITES = ["linkedin.com/in", "facebook.com", "instagram.com", "x.com", "twitter.com", "tiktok.com", "threads.net", "youtube.com"]


def _breach(t: Target, http: Http, out: list[Finding]) -> None:
    subjects = [s for s in [t.email, t.username] if s]
    if not subjects:
        return
    for s in subjects:
        # LeakCheck public – ingyenes, kulcs nélkül; csak forrás nevét és dátumát adja
        body, r = http.get("leakcheck", "https://leakcheck.io/api/public", params={"check": s}, expect_json=True)
        if isinstance(body, dict) and body.get("success"):
            n = body.get("found", 0)
            srcs = body.get("sources", [])
            names = ", ".join(f"{x.get('name')} ({x.get('date') or '?'})" for x in srcs[:12])
            out.append(Finding("leakcheck", "breach", f"Adatszivárgás: {n} találat – {s}",
                               f"források: {names}{' …' if len(srcs) > 12 else ''} · érintett mezők: {', '.join(body.get('fields', []))}" if n else "Nincs ismert szivárgás a LeakCheck nyilvános indexében.",
                               url="https://leakcheck.io/", severity="medium" if n else "info", data=body))
        elif isinstance(body, dict):
            out.append(Finding("leakcheck", "breach", f"LeakCheck: {body.get('error', 'hiba')}", f"lekérdezés: {s}", severity="info", data=body))
        time.sleep(1.2)

    if t.email:
        e = t.email.strip()
        key = os.environ.get("OSINTDD_HIBP_KEY")
        if key:
            body, r = http.get("hibp", f"https://haveibeenpwned.com/api/v3/breachedaccount/{quote_plus(e)}", params={"truncateResponse": "false"},
                               headers={"hibp-api-key": key, "user-agent": "osint-dd"}, expect_json=True)
            if isinstance(body, list):
                for b in body[:25]:
                    out.append(Finding("hibp", "breach", f"HIBP: {b.get('Title')} ({str(b.get('BreachDate',''))[:10]})",
                                       f"{b.get('Domain')} · {', '.join(b.get('DataClasses', [])[:8])}", url="https://haveibeenpwned.com/", severity="medium", data=b))
            elif r is not None and r.status_code == 404:
                out.append(Finding("hibp", "breach", "HIBP: nincs találat", e, severity="info"))
        else:
            out.append(Finding("hibp", "breach", "HIBP API kulcs nincs beállítva (fizetős, ~5 USD/hó)", "OSINTDD_HIBP_KEY a .env-ben aktiválja.", severity="info"))

        key = os.environ.get("OSINTDD_DEHASHED_KEY")
        if key:
            started = time.time()
            try:
                r = http.client.post("https://api.dehashed.com/v2/search", headers={"Dehashed-Api-Key": key, "Content-Type": "application/json"},
                                     json={"query": f'email:"{e}"', "size": 50, "de_dupe": True})
                body = r.json() if r.is_success else None
                http.log.log("dehashed", "POST", {"query": f"email:{e}"}, f"HTTP {r.status_code}", started, len((body or {}).get("entries", [])), raw=body)
                for en in (body or {}).get("entries", [])[:30]:
                    out.append(Finding("dehashed", "breach", f"DeHashed: {en.get('database_name')}",
                                       f"mezők: {', '.join(k for k, v in en.items() if v and k not in ('id', 'database_name', 'raw_record'))}", severity="medium", data={k: v for k, v in en.items() if k != "password"}))
            except Exception as ex:  # noqa: BLE001
                http.log.log("dehashed", "POST", {"query": e}, "ERROR", started, 0, str(ex))
        else:
            out.append(Finding("dehashed", "breach", "DeHashed API kulcs nincs beállítva (fizetős)", "OSINTDD_DEHASHED_KEY aktiválja. Jelszómezőket az eszköz nem tárol.", severity="info"))

    key = os.environ.get("OSINTDD_INTELX_KEY")
    for s in subjects + ([t.person] if t.person else []) + ([t.company] if t.company else []):
        if not key:
            break
        started = time.time()
        try:
            r = http.client.post("https://2.intelx.io/intelligent/search", headers={"x-key": key}, json={"term": s, "maxresults": 20, "media": 0, "sort": 4, "timeout": 10})
            sid = r.json().get("id") if r.is_success else None
            time.sleep(3)
            res = http.client.get("https://2.intelx.io/intelligent/search/result", params={"id": sid, "limit": 20}, headers={"x-key": key}).json() if sid else {}
            recs = res.get("records", [])
            http.log.log("intelx", "search", {"term": s}, f"HTTP {r.status_code}", started, len(recs), raw=res)
            for rec in recs[:20]:
                out.append(Finding("intelx", "breach", f"IntelX: {rec.get('name') or rec.get('bucket')}", f"bucket: {rec.get('bucket')} · dátum: {str(rec.get('date',''))[:10]} · média: {rec.get('mediah')}",
                                   url=f"https://intelx.io/?s={quote_plus(s)}", severity="low", data=rec))
        except Exception as ex:  # noqa: BLE001
            http.log.log("intelx", "search", {"term": s}, "ERROR", started, 0, str(ex))
    if not key:
        out.append(Finding("intelx", "breach", "IntelX kulcs nincs beállítva (ingyenes regisztráció, korlátos)", "OSINTDD_INTELX_KEY aktiválja.", severity="info"))


def _aleph(t: Target, http: Http, out: list[Finding]) -> None:
    key = os.environ.get("OSINTDD_ALEPH_KEY")
    subjects = [s for s in [t.company, t.person] if s]
    if not subjects:
        return
    if not key:
        for s in subjects:
            out.append(Finding("aleph", "aleph", f"OCCRP Aleph – kézi keresés: {s}", "API-hoz ingyenes fiók + kulcs kell (OSINTDD_ALEPH_KEY).",
                               url=f"https://aleph.occrp.org/search?q={quote_plus(s)}", severity="info"))
        return
    for s in subjects:
        body, r = http.get("aleph", "https://aleph.occrp.org/api/2/entities", params={"q": f'"{s}"', "limit": 15}, headers={"Authorization": f"ApiKey {key}"}, expect_json=True)
        for res in (body or {}).get("results", []) if isinstance(body, dict) else []:
            p = res.get("properties", {})
            out.append(Finding("aleph", "aleph", f"Aleph: {(p.get('name') or ['?'])[0]} ({res.get('schema')})",
                               f"gyűjtemény: {res.get('collection', {}).get('label')} · ország: {', '.join(p.get('country', [])[:3])} · lekérdezés: {s}",
                               url=res.get("links", {}).get("ui", ""), severity="low", data={"id": res.get("id"), "schema": res.get("schema"), "collection": res.get("collection", {}).get("label")}))
        time.sleep(1)


def _social(t: Target, http: Http, out: list[Finding]) -> None:
    subjects = [f'"{s}"' for s in [t.person, t.username] if s]
    if not subjects:
        return
    for s in subjects:
        extra = " ".join(x for x in [t.company, t.employer, t.location] if x) if s == f'"{t.person}"' else ""
        q = f"{s} (" + " OR ".join(f"site:{d}" for d in SOCIAL_SITES) + f") {extra}".rstrip()
        for r in _ddg(http, "social", q, "text", region="us-en", max_results=15)[:15]:
            href = r.get("href", "")
            plat = next((d.split("/")[0] for d in SOCIAL_SITES if d.split("/")[0] in href), "social")
            out.append(Finding("social", "social", f"[{plat}] {r.get('title','')[:130]}", r.get("body", "")[:300], url=href, severity="info", data={"query": q}))
        time.sleep(1.2)


def _face(t: Target, out: list[Finding]) -> None:
    if not t.person:
        return
    out += [
        Finding("face", "manual", "PimEyes – arcfelismerő keresés (kézi képfeltöltés, fizetős, GDPR 9. cikk!)", "", url="https://pimeyes.com/", severity="info"),
        Finding("face", "manual", "FaceCheck.ID – arcfelismerő keresés (kézi, kreditalapú)", "", url="https://facecheck.id/", severity="info"),
        Finding("face", "manual", "Yandex képkeresés – fordított képkeresés arcra is", "", url="https://yandex.com/images/", severity="info"),
    ]


def run(t: Target, http: Http, log, case) -> list[Finding]:
    mods = set(case.get("modules") or [])
    out: list[Finding] = []
    if not case.get("person_checks") and not t.company:
        return out
    if "breach" in mods and case.get("person_checks"):
        _breach(t, http, out)
    if "aleph" in mods:
        _aleph(t, http, out)
    if "social" in mods and case.get("person_checks"):
        _social(t, http, out)
    if "face" in mods and case.get("person_checks"):
        _face(t, out)
    return out
