"""Ha a pontosítás nem lehetséges: az azonos nevű jelöltekre külön al-ügy és külön jelentés készül."""
from __future__ import annotations

import copy
import json
import re
from typing import Callable

from .core import Store, Target
from .runner import REG_RE, TAX_RE, run_case

MAX_CHILDREN = 6


def _company_candidates(store: Store, case: dict) -> list[dict]:
    """Cégjelöltek a cégadat-oldalak találataiból: {label, tax_id, reg_number, location}."""
    fs = [f for f in store.get_findings(case["id"]) if f["source"] in ("ddg_registry", "ddg")]
    cands: dict[str, dict] = {}
    for f in fs:
        txt = f["title"] + " " + f.get("summary", "") + " " + f.get("url", "")
        for rn in REG_RE.findall(txt):
            cands.setdefault(rn, {"reg_number": rn, "tax_id": "", "label": rn, "location": "", "src": f["url"]})
        for tx in TAX_RE.findall(txt):
            if tx[:1] in "12" and tx not in cands:
                cands[tx] = {"reg_number": "", "tax_id": tx, "label": tx, "location": "", "src": f["url"]}
        m = re.search(r"\b(\d{4})\s+([A-ZÁÉÍÓÖŐÚÜŰ][\wáéíóöőúüű]+)", f.get("summary", ""))
        if m and cands:
            list(cands.values())[-1].setdefault("location", m.group(2))
    if len(cands) < 2:
        # célzott utánkeresés: adószám / cégjegyzékszám a cégadat-oldalakon
        from .core import QueryLogger
        from .http import Http
        from .sources.web import HU_REGISTRY_SITES, _ddg
        http = Http(QueryLogger(store, case["id"], "split"))
        try:
            for q in [f'"{case["target"].company}" adószám (' + " OR ".join(f"site:{d}" for d in HU_REGISTRY_SITES[:5]) + ")",
                      f'"{case["target"].company}" cégjegyzékszám székhely']:
                for r in _ddg(http, "split_registry", q, "text", max_results=15):
                    txt = r.get("title", "") + " " + r.get("body", "") + " " + r.get("href", "")
                    for rn in REG_RE.findall(txt):
                        cands.setdefault(rn, {"reg_number": rn, "tax_id": "", "label": rn, "location": "", "src": r.get("href", "")})
                    for tx in TAX_RE.findall(txt):
                        if tx[:1] in "12" and tx not in cands:
                            cands[tx] = {"reg_number": "", "tax_id": tx, "label": tx, "location": "", "src": r.get("href", "")}
        finally:
            http.close()
    return list(cands.values())[:MAX_CHILDREN]


def _person_candidates(case: dict, findings: list[dict], lang: str) -> list[dict]:
    """Személyjelöltek: Claude csoportosítja a találatokat különböző személyekre; LLM nélkül domain-alapú csoportok."""
    from . import llm
    real = [f for f in findings if f["source"] in ("ddg", "ddg_news", "social", "username", "maigret", "gdelt")]
    slim = [{"title": f["title"], "summary": f.get("summary", "")[:200], "url": f.get("url", "")} for f in real][:80]
    if [b for b in llm.backends() if b != "rules"]:
        prompt = (("Az alábbi webes találatok egy „{n}” nevű személyre vonatkoznak, de valószínűleg több különböző személyt fednek le. "
                   "Csoportosítsd őket különböző személyekre. Válaszolj CSAK JSON-tömbbel, elemei: "
                   '{{"label": "rövid megkülönböztető címke", "employer": "munkahely/pozíció vagy üres", "location": "város vagy üres", "birth_year": "vagy üres", "keywords": ["1-3 szűrő kulcsszó"]}}. '
                   "Legfeljebb {m} csoport.\n\n") if lang == "hu" else
                  ("The web hits below refer to a person named \"{n}\" but probably cover several different people. Group them into distinct persons. "
                   "Answer ONLY with a JSON array of {{\"label\": \"short distinguishing label\", \"employer\": \"\", \"location\": \"\", \"birth_year\": \"\", \"keywords\": [\"1-3 filter keywords\"]}}. "
                   "At most {m} groups.\n\n")).format(n=case["target"].person, m=MAX_CHILDREN) + json.dumps(slim, ensure_ascii=False)
        try:
            txt = llm.raw_completion(prompt, lang)
            arr = json.loads(re.search(r"\[.*\]", txt, re.S).group(0))
            return [c for c in arr if isinstance(c, dict)][:MAX_CHILDREN]
        except Exception:  # noqa: BLE001
            pass
    groups: dict[str, dict] = {}
    for f in real:
        dom = re.sub(r"^www\.", "", re.sub(r"^https?://", "", f.get("url", "")).split("/")[0]) or "egyéb"
        g = groups.setdefault(dom, {"label": dom, "employer": "", "location": "", "birth_year": "", "keywords": [dom]})
    return list(groups.values())[:MAX_CHILDREN]


def split_case(store: Store, case_id: str, progress: Callable[[str], None] | None = None, run: bool = True) -> list[str]:
    case = store.get_case(case_id)
    lang = case.get("lang", "hu")
    say = progress or (lambda s: None)
    findings = store.get_findings(case_id)
    kinds = {a for f in findings if f["category"] == "identity" for a in f.get("data", {}).get("ask", [])}
    cands: list[dict] = []
    kind = ""
    if {"tax_id", "reg_number"} & kinds and case["target"].company:
        cands, kind = _company_candidates(store, case), "company"
    elif case.get("person_checks") and case["target"].person:
        cands, kind = _person_candidates(case, findings, lang), "person"
    if not cands:
        say("✗ nincs szétválasztható jelölt / no separable candidates")
        store.audit("split_none", case_id, kind)
        return []
    ids = []
    for c in cands:
        tg: Target = copy.deepcopy(case["target"])
        if kind == "company":
            tg.tax_id = c.get("tax_id", "") or tg.tax_id
            tg.reg_number = c.get("reg_number", "") or tg.reg_number
            tg.location = c.get("location", "") or tg.location
        else:
            tg.employer = c.get("employer", "") or ""
            tg.location = c.get("location", "") or ""
            tg.birth_year = str(c.get("birth_year", "") or "")
            tg.extra_keywords = list(dict.fromkeys(tg.extra_keywords + [k for k in c.get("keywords", []) if k]))
        title = f"{case['title']} · {c.get('label', '?')}"
        cid = store.create_case(title, case["purpose"], case["legal_basis"], tg, case.get("person_checks", False), case.get("requester", ""), lang,
                                case.get("modules"), parent_id=case_id)
        ids.append(cid)
        say(f"+ {title} ({cid})")
    store.audit("split", case_id, f"{kind} → {len(ids)} al-ügy: {','.join(ids)}")
    if run:
        for cid in ids:
            say(f"▶ {cid}")
            run_case(store, cid, say)
    return ids
