"""Kézi ellenőrző linkek – előre kitöltött keresések olyan magyar/EU forrásokhoz, amelyeknek nincs ingyenes API-ja."""
from __future__ import annotations

from urllib.parse import quote_plus

from ..core import Finding, Target


def run(t: Target, http, log, case) -> list[Finding]:
    out: list[Finding] = []
    c = t.company.strip()
    q = quote_plus(c)
    if c:
        links = [
            ("e-cégjegyzék (IM Céginformációs Szolgálat) – hiteles cégadatok, ingyenes", f"https://www.e-cegjegyzek.hu/?cegkereses"),
            ("Nemzeti Cégtár – alapadatok, tulajdonosok, ingyenes", f"https://www.nemzeticegtar.hu/kereses?q={q}"),
            ("NAV adóalany-lekérdezés (adószám, ÁFA-státusz, köztartozásmentes)", "https://nav.gov.hu/adatbazisok/adoalany"),
            ("NAV végrehajtás alatt álló adózók", "https://nav.gov.hu/adatbazisok/adoslista/vegrehajtas_alattiak"),
            ("NAV nagy összegű adóhiányosok / hátralékosok", "https://nav.gov.hu/adatbazisok/adoslista"),
            ("NAV be nem jelentett alkalmazottat foglalkoztatók", "https://nav.gov.hu/adatbazisok/adoslista/bejelentes_nelkul"),
            ("Bírósági anonimizált határozatok (ÜIR) – perek", "https://eakta.birosag.hu/anonimizalt-hatarozatok"),
            ("Közbeszerzési Hatóság – EKR / hirdetmények", f"https://ekr.gov.hu/portal/kozbeszerzes/eljarasok/lista?q={q}"),
            ("EU TED – európai közbeszerzés", f"https://ted.europa.eu/hu/search/result?FT={q}"),
            ("Cégközlöny – felszámolás, végelszámolás, kényszertörlés", "https://www.cegkozlony.hu/"),
            ("OpenCorporates (nemzetközi, weben ingyenes, API fizetős)", f"https://opencorporates.com/companies?q={q}"),
            ("OpenSanctions (weben ingyenes, API/kereskedelmi licenc fizetős)", f"https://www.opensanctions.org/search/?q={q}"),
            ("OCCRP Aleph – oknyomozó adatbázisok, kiszivárgott dokumentumok", f"https://aleph.occrp.org/search?q={q}"),
            ("EU Transparency Register – lobbi", f"https://transparency-register.europa.eu/searchregister-or-update/search-register_hu?keyword={q}"),
            ("Google News", f"https://news.google.com/search?q={q}&hl=hu&gl=HU"),
        ]
        for title, url in links:
            out.append(Finding("manual", "manual", title, "", url=url, severity="info"))
    if t.domain:
        d = t.domain
        for title, url in [
            ("VirusTotal domain (ingyenes web, API korlátos)", f"https://www.virustotal.com/gui/domain/{d}"),
            ("urlscan.io", f"https://urlscan.io/search/#{d}"),
            ("SecurityHeaders.com", f"https://securityheaders.com/?q={d}&followRedirects=on"),
            ("SSL Labs", f"https://www.ssllabs.com/ssltest/analyze.html?d={d}"),
            ("DNSDumpster", "https://dnsdumpster.com/"),
            ("BuiltWith – technológiai stack", f"https://builtwith.com/{d}"),
        ]:
            out.append(Finding("manual", "manual", title, "", url=url, severity="info"))
    if case.get("person_checks") and t.person:
        p = quote_plus(t.person)
        for title, url in [
            ("LinkedIn keresés (bejelentkezve, kézzel – ToS miatt nem automatizált)", f"https://www.linkedin.com/search/results/all/?keywords={p}"),
            ("Google – név + cég", f"https://www.google.com/search?q=%22{p}%22+{q}"),
            ("Nemzeti Cégtár – személy cégkapcsolatai", f"https://www.nemzeticegtar.hu/kereses?q={p}"),
            ("Bírósági határozatok – név", "https://eakta.birosag.hu/anonimizalt-hatarozatok"),
            ("Have I Been Pwned (kézi, ingyenes weben)", "https://haveibeenpwned.com/"),
        ]:
            out.append(Finding("manual", "manual", title, "", url=url, severity="info"))
    return out
