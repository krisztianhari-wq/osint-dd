"""Kétnyelvű szövegek (hu / en)."""
from __future__ import annotations

STR = {
    "hu": {
        "app": "osint-dd · Átvilágító",
        "tagline": "Helyi due diligence asszisztens nyílt forrásokból",
        "by": "készítette: sadrobot",
        "report_title": "Átvilágítási jelentés",
        "case": "Ügy", "target": "Vizsgált alany", "purpose": "Cél", "legal_basis": "Jogalap", "created": "Létrehozva",
        "generated": "Jelentés kelte", "run_id": "Futás azonosító", "requester": "Kérelmező",
        "summary": "Összefoglaló", "risk": "Kockázati értékelés", "findings": "Megállapítások", "sources": "Források",
        "manual": "Kézi ellenőrző linkek", "querylog": "Lekérdezési napló", "disclaimer": "Jogi megjegyzés",
        "disclaimer_text": ("Ez a jelentés kizárólag nyilvánosan hozzáférhető, ingyenes forrásokból automatikusan gyűjtött adatokon alapul. "
                            "A névegyezések nem igazolnak személyazonosságot; minden megállapítást kézzel ellenőrizni kell döntés előtt. "
                            "A személyes adatok kezelése a fent rögzített GDPR-jogalap alapján, célhoz kötötten történik; a jelentést az "
                            "adatkezelési szabályzat szerinti ideig kell megőrizni, majd törölni."),
        "sev": {"high": "Magas", "medium": "Közepes", "low": "Alacsony", "info": "Információ"},
        "cat": {"company": "Cégadatok", "sanctions": "Szankciós és figyelőlisták", "web": "Web és sajtó", "domain": "Domain és infrastruktúra",
                "person": "Személyi ellenőrzés", "phone": "Telefonszám", "manual": "Kézi ellenőrző linkek",
                "breach": "Adatszivárgás-keresők (szürke zóna)", "aleph": "OCCRP Aleph (szürke zóna)", "social": "Közösségi profilok (szürke zóna)", "identity": "Azonosítás"},
        "modules": {"company": "Cégadatok", "sanctions": "Szankciós listák", "domain": "Domain", "web": "Web és sajtó", "manual": "Kézi linkek",
                    "person": "Személy (felhasználónév, e-mail, maigret, holehe)", "phone": "Telefonszám",
                    "breach": "Adatszivárgás-keresők (LeakCheck; HIBP/DeHashed/IntelX kulccsal)", "aleph": "OCCRP Aleph oknyomozó adattár",
                    "social": "Közösségi profilok keresőmotoron át", "face": "Arcfelismerő keresők (csak kézi link)"},
        "modules_title": "Modulok", "grey_title": "Szürke zóna – jogi egyeztetés után, ügyenként engedélyezve",
        "grey_hint": "Ezek a források kiszivárgott adatbázisokat, oknyomozó gyűjteményeket vagy közösségi profilokat érintenek. Csak személyi modullal és dokumentált jogalappal futnak.",
        "modules_ran": "Futtatott modulok",
        "birth_year": "Születési év", "location": "Lakhely / székhely (város)", "employer": "Munkahely / pozíció", "reg_number": "Cégjegyzékszám",
        "refine_title": "Pontosítás szükséges", "refine_hint": "Az alany a név alapján nem azonosítható egyértelműen. Add meg a szűrő adatokat, és futtasd újra.",
        "refine_btn": "Pontosítás és újrafuttatás", "refine_block": "Pontosító adatok (ha a név nem egyértelmű)",
        "split_btn": "Nem tudom pontosítani – külön jelentés minden jelöltre", "children": "Al-ügyek (azonos nevű jelöltek)", "parent": "Szülő ügy",
        "no_llm": "AI-összefoglaló nem készült (nincs API-kulcs, claude CLI vagy Ollama). Az alábbi szabályalapú összegzés a talált adatokból áll.",
        "counts": "Összesen {n} megállapítás · {h} magas · {m} közepes · {l} alacsony",
        "paid_note": "Fizetős / nem beépített források",
        "company": "Cég", "tax_id": "Adószám", "person": "Személy", "email": "E-mail", "username": "Felhasználónév", "phone": "Telefon", "domain": "Domain", "keywords": "Kulcsszavak",
        "page": "oldal", "of": "/",
        "time": "Idő", "source": "Forrás", "action": "Művelet", "request": "Kérés", "status": "Státusz", "ms": "ms", "count": "Találat",
        "person_off": "Személyi modul: KIKAPCSOLVA (nincs rögzített jogalap személyes adatra)",
        "person_on": "Személyi modul: BEKAPCSOLVA",
    },
    "en": {
        "app": "osint-dd · Due Diligence",
        "tagline": "Local due-diligence assistant built on open sources",
        "by": "crafted by sadrobot",
        "report_title": "Due Diligence Report",
        "case": "Case", "target": "Subject", "purpose": "Purpose", "legal_basis": "Legal basis", "created": "Created",
        "generated": "Report date", "run_id": "Run ID", "requester": "Requester",
        "summary": "Executive summary", "risk": "Risk assessment", "findings": "Findings", "sources": "Sources",
        "manual": "Manual verification links", "querylog": "Query log", "disclaimer": "Legal notice",
        "disclaimer_text": ("This report is based solely on data collected automatically from publicly available, free sources. "
                            "Name matches do not establish identity; every finding must be verified manually before any decision. "
                            "Personal data is processed under the GDPR legal basis recorded above, strictly for the stated purpose; the report "
                            "must be retained only for the period defined in the data-protection policy and then deleted."),
        "sev": {"high": "High", "medium": "Medium", "low": "Low", "info": "Info"},
        "cat": {"company": "Company data", "sanctions": "Sanctions & watchlists", "web": "Web & press", "domain": "Domain & infrastructure",
                "person": "Person checks", "phone": "Phone number", "manual": "Manual verification links",
                "breach": "Breach search engines (grey zone)", "aleph": "OCCRP Aleph (grey zone)", "social": "Social profiles (grey zone)", "identity": "Identification"},
        "modules": {"company": "Company data", "sanctions": "Sanctions lists", "domain": "Domain", "web": "Web & press", "manual": "Manual links",
                    "person": "Person (username, e-mail, maigret, holehe)", "phone": "Phone number",
                    "breach": "Breach search engines (LeakCheck; HIBP/DeHashed/IntelX with keys)", "aleph": "OCCRP Aleph investigative archive",
                    "social": "Social profiles via search engines", "face": "Face search engines (manual link only)"},
        "modules_title": "Modules", "grey_title": "Grey zone – enabled per case after legal sign-off",
        "grey_hint": "These sources touch leaked databases, investigative archives or social profiles. They run only with the person module and a documented legal basis.",
        "modules_ran": "Modules run",
        "birth_year": "Birth year", "location": "Location / seat (city)", "employer": "Employer / position", "reg_number": "Company registration no.",
        "refine_title": "Refinement needed", "refine_hint": "The subject cannot be identified unambiguously by name. Add filter data and re-run.",
        "refine_btn": "Refine and re-run", "refine_block": "Disambiguation data (if the name is ambiguous)",
        "split_btn": "Cannot refine – separate report per candidate", "children": "Sub-cases (same-name candidates)", "parent": "Parent case",
        "no_llm": "No AI summary was produced (no API key, claude CLI or Ollama available). The rule-based summary below is compiled from the collected data.",
        "counts": "{n} findings in total · {h} high · {m} medium · {l} low",
        "paid_note": "Paid / not integrated sources",
        "company": "Company", "tax_id": "Tax ID", "person": "Person", "email": "E-mail", "username": "Username", "phone": "Phone", "domain": "Domain", "keywords": "Keywords",
        "page": "page", "of": "of",
        "time": "Time", "source": "Source", "action": "Action", "request": "Request", "status": "Status", "ms": "ms", "count": "Results",
        "person_off": "Person module: OFF (no legal basis recorded for personal data)",
        "person_on": "Person module: ON",
    },
}

LEGAL_LABEL = {
    "hu": {"jogos_erdek": "Jogos érdek – GDPR 6(1)(f)", "szerzodes": "Szerződés – GDPR 6(1)(b)", "jogi_kotelezettseg": "Jogi kötelezettség – GDPR 6(1)(c)",
           "hozzajarulas": "Hozzájárulás – GDPR 6(1)(a)", "nem_szemelyes": "Nem személyes adat"},
    "en": {"jogos_erdek": "Legitimate interest – GDPR 6(1)(f)", "szerzodes": "Contract – GDPR 6(1)(b)", "jogi_kotelezettseg": "Legal obligation – GDPR 6(1)(c)",
           "hozzajarulas": "Consent – GDPR 6(1)(a)", "nem_szemelyes": "No personal data"},
}


def t(lang: str, key: str, **kw) -> str:
    s = STR.get(lang, STR["hu"]).get(key, STR["hu"].get(key, key))
    return s.format(**kw) if kw and isinstance(s, str) else s
