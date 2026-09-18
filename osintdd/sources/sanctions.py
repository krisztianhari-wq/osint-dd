"""Szankciós és figyelőlisták – hivatalos, ingyenes források lokálisan gyorsítótárazva.

EU konszolidált szankciós lista (CSV), OFAC SDN (CSV), ENSZ konszolidált lista (XML), UK OFSI (CSV).
Fuzzy névillesztés rapidfuzz-zal. OpenSanctions/yente: kereskedelmi célra licencköteles -> csak opcionális URL-lel.
"""
from __future__ import annotations

import csv
import io
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from rapidfuzz import fuzz, process

from ..core import CACHE_DIR, Finding, Target
from ..http import Http

LISTS = {
    "eu_fsf": ("https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList_1_1/content", {"token": "dG9rZW4tMjAxNw"}),
    "ofac_sdn": ("https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV", None),
    "un_consolidated": ("https://scsanctions.un.org/resources/xml/en/consolidated.xml", None),
    "uk_ofsi": ("https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv", None),
}
MAX_AGE_H = 24
THRESHOLD = 88


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"sanctions_{key}.txt"


def _fetch(key: str, http: Http) -> str | None:
    p = _cache_path(key)
    if p.exists() and time.time() - p.stat().st_mtime < MAX_AGE_H * 3600:
        return p.read_text(encoding="utf-8", errors="replace")
    url, params = LISTS[key]
    body, r = http.get(f"sanctions:{key}", url, params=params, save_raw=False)
    if isinstance(body, str) and r is not None and r.is_success and len(body) > 1000:
        p.write_text(body, encoding="utf-8")
        return body
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None


def _names_eu(text: str):
    rd = csv.DictReader(io.StringIO(text), delimiter=";")
    for row in rd:
        n = (row.get("NameAlias_WholeName") or "").strip()
        if n:
            yield n, {"program": row.get("Entity_Regulation_Programme"), "type": row.get("Entity_SubjectType"),
                      "logical_id": row.get("Entity_LogicalId"), "remark": (row.get("Entity_Remark") or "")[:200]}


def _names_ofac(text: str):
    for row in csv.reader(io.StringIO(text)):
        if len(row) > 3 and row[1].strip() and row[1] != "name":
            yield row[1].strip(), {"uid": row[0], "type": row[2], "program": row[3], "remarks": (row[11] if len(row) > 11 else "")[:200]}


def _names_un(text: str):
    try:
        root = ET.fromstring(text.encode("utf-8", errors="replace"))
    except ET.ParseError:
        return
    for ind in root.iter("INDIVIDUAL"):
        parts = [ind.findtext(f"{k}_NAME") or "" for k in ("FIRST", "SECOND", "THIRD", "FOURTH")]
        n = " ".join(p for p in parts if p).strip()
        if n:
            yield n, {"type": "individual", "program": ind.findtext("UN_LIST_TYPE"), "ref": ind.findtext("REFERENCE_NUMBER")}
    for ent in root.iter("ENTITY"):
        n = (ent.findtext("FIRST_NAME") or "").strip()
        if n:
            yield n, {"type": "entity", "program": ent.findtext("UN_LIST_TYPE"), "ref": ent.findtext("REFERENCE_NUMBER")}


def _names_uk(text: str):
    lines = text.splitlines()
    # az OFSI CSV első sora a dátum, a második a fejléc
    start = 1 if lines and not lines[0].startswith("Name 6") else 0
    rd = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    for row in rd:
        parts = [row.get(f"Name {i}") or "" for i in (1, 2, 3, 4, 5, 6)]
        n = " ".join(p.strip() for p in parts if p and p.strip())
        if n:
            yield n, {"type": row.get("Group Type"), "program": row.get("Regime"), "group_id": row.get("Group ID")}


PARSERS = {"eu_fsf": _names_eu, "ofac_sdn": _names_ofac, "un_consolidated": _names_un, "uk_ofsi": _names_uk}
LABELS = {"eu_fsf": "EU konszolidált szankciós lista", "ofac_sdn": "US OFAC SDN", "un_consolidated": "ENSZ BT konszolidált lista", "uk_ofsi": "UK OFSI"}


def _norm(s: str) -> str:
    s = re.sub(r"\b(kft|zrt|nyrt|bt|kkt|ltd|llc|inc|gmbh|ag|sa|s\.a\.|plc|co|corp|limited|zártkörűen működő részvénytársaság|korlátolt felelősségű társaság)\b\.?", " ", s.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def run(t: Target, http: Http, log, case) -> list[Finding]:
    queries = [q for q in [t.company, t.person if case.get("person_checks") else ""] if q and q.strip()]
    queries += [k for k in t.extra_keywords if k]
    if not queries:
        return []
    out: list[Finding] = []
    for key in LISTS:
        started = time.time()
        text = _fetch(key, http)
        if not text:
            out.append(Finding(f"sanctions:{key}", "sanctions", f"{LABELS[key]}: nem letölthető", "A lista most nem érhető el, később futtasd újra.", severity="low"))
            continue
        entries = list(PARSERS[key](text))
        names = [_norm(n) for n, _ in entries]
        for q in queries:
            qn = _norm(q)
            matches = process.extract(qn, names, scorer=fuzz.token_set_ratio, limit=5, score_cutoff=THRESHOLD)
            log.log(f"sanctions:{key}", "match", {"query": q, "entries": len(entries)}, "OK", started, len(matches))
            if not matches:
                continue
            for _, score, idx in matches:
                orig, meta = entries[idx]
                sev = "high" if score >= 95 else "medium"
                out.append(Finding(f"sanctions:{key}", "sanctions", f"Lehetséges szankciós találat ({int(score)}%): {orig}",
                                   f"Lekérdezett: „{q}” · {LABELS[key]} · program: {meta.get('program')} · típus: {meta.get('type')}. "
                                   "Fuzzy egyezés – kézi ellenőrzés kötelező (névazonosság ≠ személyazonosság).",
                                   severity=sev, data={"query": q, "score": score, "list": key, **meta}))
    if not any(f.severity in ("high", "medium") for f in out):
        out.append(Finding("sanctions", "sanctions", "Nincs szankciós találat",
                           f"Ellenőrzött listák: {', '.join(LABELS[k] for k in LISTS)}; lekérdezett nevek: {', '.join(queries)}. Küszöb {THRESHOLD}%.", severity="info"))
    yente = os.environ.get("OSINTDD_YENTE_URL")
    if yente:
        for q in queries:
            body, r = http.get("yente", f"{yente.rstrip('/')}/search/default", params={"q": q, "limit": 5}, expect_json=True)
            for res in (body or {}).get("results", []) if isinstance(body, dict) else []:
                props = res.get("properties", {})
                out.append(Finding("yente", "sanctions", f"OpenSanctions/yente: {res.get('caption')} ({res.get('schema')})",
                                   f"témák: {', '.join(props.get('topics', []))} · datasets: {', '.join(res.get('datasets', [])[:5])}",
                                   url=f"https://www.opensanctions.org/entities/{res.get('id')}/", severity="medium", data=res))
    return out
