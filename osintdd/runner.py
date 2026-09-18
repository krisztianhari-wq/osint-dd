"""Egy ügy futtatása: minden forrásmodul, naplózás, jelentés."""
from __future__ import annotations

import re
import traceback
import uuid
from typing import Callable

from .core import Finding, QueryLogger, Store
from .http import Http
from .sources import company, domain, grey, manual, person, phone, sanctions, web

MODULES: list[tuple[str, Callable]] = [
    ("company", company.run), ("sanctions", sanctions.run), ("domain", domain.run),
    ("web", web.run), ("person", person.run), ("phone", phone.run), ("grey", grey.run), ("manual", manual.run),
]
GREY = {"breach", "aleph", "social", "face"}


def run_case(store: Store, case_id: str, progress: Callable[[str], None] | None = None,
             modules: list[str] | None = None) -> str:
    case = store.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    run_id = uuid.uuid4().hex[:8]
    store.set_status(case_id, "running")
    store.audit("run_started", case_id, f"run={run_id}")
    log = QueryLogger(store, case_id, run_id)
    http = Http(log)
    say = progress or (lambda s: None)
    total = 0
    try:
        enabled = set(modules or case.get("modules") or [])
        for name, fn in MODULES:
            if name == "grey":
                if not (enabled & GREY):
                    continue
            elif name not in enabled:
                continue
            say(f"▸ {name}")
            try:
                fs = fn(case["target"], http, log, case)
            except Exception as e:  # noqa: BLE001
                fs = [Finding(name, name if name in ("company", "sanctions", "web", "domain", "person", "phone", "manual") else "web",
                              f"Modulhiba: {name}", f"{e}", severity="low", data={"trace": traceback.format_exc()[-1500:]})]
                log.log(name, "module", {}, "ERROR", 0, 0, str(e))
            n = store.add_findings(case_id, run_id, fs)
            total += n
            say(f"  {name}: {n}")
    finally:
        http.close()
    say("▸ identity")
    amb = detect_ambiguity(store, case, run_id)
    if amb:
        store.add_findings(case_id, run_id, amb)
        store.audit("identity_ambiguous", case_id, "; ".join(f.title for f in amb))
    say("▸ report")
    from .report import build_report
    path = build_report(store, case_id, run_id)
    store.set_status(case_id, "done", report_path=str(path))
    store.audit("run_finished", case_id, f"run={run_id} findings={total} report={path}")
    say(f"✓ {path}")
    return run_id


TAX_RE = re.compile(r"\b(\d{8})(?:-\d-\d{2})?\b")
REG_RE = re.compile(r"\b(\d{2}-\d{2}-\d{6})\b")


def detect_ambiguity(store: Store, case: dict, run_id: str) -> list[Finding]:
    """Ha a név önmagában nem azonosít egyértelműen, 'identity' megállapítást ad, amiből a GUI pontosító kérdéseket tesz fel."""
    t = case["target"]
    fs = store.get_findings(case["id"], run_id)
    out: list[Finding] = []
    lang = case.get("lang", "hu")

    # --- cég: nincs adószám/cégjegyzékszám, és a cégadat-oldalak több különböző céget hoznak
    if t.company and not t.tax_id and not t.reg_number:
        vies_ok = any(f["source"] == "vies" and f["severity"] == "info" and "érvényes" in f["title"] for f in fs)
        reg_hits = [f for f in fs if f["source"] == "ddg_registry"]
        ids = set()
        for f in reg_hits:
            txt = f["title"] + " " + f.get("summary", "") + " " + f.get("url", "")
            ids |= set(REG_RE.findall(txt)) | {m for m in TAX_RE.findall(txt) if m[:1] in "12" }
        gleif_n = sum(1 for f in fs if f["source"] == "gleif" and f["title"].startswith("LEI:"))
        if not vies_ok and (len(ids) >= 2 or gleif_n >= 2 or (not reg_hits and not t.location)):
            q = ("Több hasonló nevű cég lehetséges. Add meg az adószámot vagy cégjegyzékszámot, illetve a székhely városát a szűréshez."
                 if lang == "hu" else "Several similarly named companies are possible. Provide the tax ID or company registration number and the seat city to filter.")
            out.append(Finding("identity", "identity", "Cég azonosítása bizonytalan" if lang == "hu" else "Company identity uncertain", q, severity="medium",
                               data={"ask": ["tax_id", "reg_number", "location"], "candidates": sorted(ids)[:10]}))

    # --- személy: nincs pontosító adat, és sok/egymásnak ellentmondó találat
    if case.get("person_checks") and t.person and not t.disambiguators():
        web_n = sum(1 for f in fs if f["source"] in ("ddg", "social") and f.get("data", {}).get("disambig") != "match")
        sanc_n = sum(1 for f in fs if f["category"] == "sanctions" and f["severity"] in ("medium", "high"))
        user_n = sum(1 for f in fs if f["source"] == "username" and f["title"].startswith("Felhasználónév létezik"))
        if web_n >= 5 or sanc_n or user_n >= 4:
            q = ("A név alapján több személy is szóba jöhet ({w} webes találat, {s} szankciós névegyezés, {u} fiók). Add meg a születési évet, lakhelyet és munkahelyet/pozíciót a szűréshez."
                 if lang == "hu" else "Several people may match this name ({w} web hits, {s} sanctions name matches, {u} accounts). Provide birth year, location and employer/position to filter.")
            out.append(Finding("identity", "identity", "Személy azonosítása bizonytalan" if lang == "hu" else "Person identity uncertain",
                               q.format(w=web_n, s=sanc_n, u=user_n), severity="medium", data={"ask": ["birth_year", "location", "employer"]}))
    return out
