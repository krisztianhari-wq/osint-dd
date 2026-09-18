"""Cégadatok – ingyenes források: EU VIES (HU adószám), GLEIF LEI, cégjegyzék-találatok webkeresésből."""
from __future__ import annotations

import re
import time

from ..core import Finding, Target
from ..http import Http

VIES = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{ms}/vat/{vat}"
GLEIF = "https://api.gleif.org/api/v1/lei-records"


def norm_hu_tax(tax: str) -> str:
    d = re.sub(r"\D", "", tax or "")
    return d[:8] if len(d) >= 8 else d


def run(t: Target, http: Http, log, case) -> list[Finding]:
    out: list[Finding] = []
    ms = (t.country or "HU").upper()

    # --- VIES: adószám érvényesség + hivatalos név/cím -----------------------
    vat = norm_hu_tax(t.tax_id) if ms == "HU" else re.sub(r"\W", "", t.tax_id or "")
    if vat:
        body, r = http.get("vies", VIES.format(ms=ms, vat=vat), expect_json=True)
        if isinstance(body, dict):
            if body.get("isValid"):
                out.append(Finding("vies", "company", f"ÁFA-alany érvényes: {ms}{vat}",
                                   f"{body.get('name','').strip()} – {body.get('address','').strip().replace(chr(10),', ')}",
                                   url=f"https://ec.europa.eu/taxation_customs/vies/#/vat-validation", severity="info",
                                   data={"vat": f"{ms}{vat}", "name": body.get("name"), "address": body.get("address")}))
            else:
                sev = "medium" if body.get("userError") == "INVALID" else "low"
                out.append(Finding("vies", "company", f"VIES: {ms}{vat} nem érvényes közösségi adószám",
                                   f"userError={body.get('userError')} – lehet, hogy nincs közösségi adószáma, "
                                   "vagy az adószám hibás. Ellenőrizd a NAV adóalany-lekérdezésben (kézi link).",
                                   severity=sev, data=body))

    # --- GLEIF LEI --------------------------------------------------------
    name = t.company.strip()
    if name:
        body, r = http.get("gleif", GLEIF, params={"filter[entity.legalName]": name, "page[size]": 5}, expect_json=True)
        if isinstance(body, dict):
            for rec in body.get("data", [])[:5]:
                a = rec.get("attributes", {})
                ent = a.get("entity", {})
                reg = a.get("registration", {})
                addr = ent.get("legalAddress", {})
                out.append(Finding("gleif", "company", f"LEI: {ent.get('legalName', {}).get('name')}",
                                   f"LEI {a.get('lei')} · {addr.get('country')} {addr.get('city')} · státusz {ent.get('status')} · "
                                   f"regisztráció {reg.get('status')} · jogi forma {ent.get('legalForm', {}).get('id')}",
                                   url=f"https://search.gleif.org/#/record/{a.get('lei')}", severity="info",
                                   data={"lei": a.get("lei"), "entity": ent, "registration": reg}))
            if not body.get("data"):
                out.append(Finding("gleif", "company", "Nincs LEI-rekord a névre", "Kis/közepes cégeknek gyakran nincs LEI-je; nem negatív jel.", severity="info"))
        time.sleep(0.5)
    return out
