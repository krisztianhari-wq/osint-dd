"""Kézi ellenőrző linkek – előre kitöltött keresések olyan magyar/EU forrásokhoz, amelyeknek nincs ingyenes API-ja."""
from __future__ import annotations

from urllib.parse import quote_plus

from ..core import Finding, Target


def _g(q: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(q)


def dorks(t: Target, case) -> list[Finding]:
    """12+ célzott Google-dork link – hálózat nélkül, kézi futtatásra."""
    out: list[Finding] = []
    subj = []
    if t.company:
        c = t.company.strip()
        subj += [
            (f'"{c}" filetype:pdf OR filetype:docx OR filetype:xlsx', "dokumentumok a cégről"),
            (f'"{c}" (adatszivárgás OR "data breach" OR incidens OR hack)', "incidensek"),
            (f'"{c}" (felszámolás OR végelszámolás OR kényszertörlés OR csődeljárás)', "eljárások"),
            (f'"{c}" (per OR ítélet OR bíróság OR "GVH" OR "NAIH" OR bírság)', "jogi / hatósági"),
            (f'site:linkedin.com/company "{c}"', "LinkedIn cégoldal"),
            (f'"{c}" (állás OR karrier OR "we are hiring")', "toborzás – technológiai stack"),
        ]
    if t.domain:
        d = t.domain.strip().lower()
        subj += [
            (f'site:{d} filetype:pdf OR filetype:xls OR filetype:xlsx OR filetype:doc OR filetype:docx', "kitett dokumentumok a domainen"),
            (f'site:{d} (inurl:login OR inurl:admin OR inurl:wp-login OR intitle:"index of")', "adminfelületek, könyvtárlisták"),
            (f'"{d}" (site:pastebin.com OR site:github.com OR site:gitlab.com)', "kódban / paste-ben említett domain"),
            (f'"@{d}" (site:linkedin.com OR site:facebook.com OR site:x.com)', "e-mail-címek a domainről"),
            (f'site:{d} -www', "aldomainek a keresőben"),
        ]
    if case.get("person_checks"):
        if t.person:
            p = t.person.strip()
            ctx = " ".join(x for x in [t.company, t.employer, t.location] if x)
            subj += [
                (f'"{p}" {ctx}'.strip(), "név + kontextus"),
                (f'site:linkedin.com/in "{p}"', "LinkedIn profil"),
                (f'"{p}" (site:facebook.com OR site:instagram.com OR site:x.com OR site:tiktok.com)', "közösségi profilok"),
                (f'"{p}" filetype:pdf', "dokumentumokban szereplő név"),
                (f'"{p}" (interjú OR előadás OR konferencia OR podcast)', "nyilvános szereplések"),
            ]
        if t.email:
            subj += [(f'"{t.email.strip()}"', "e-mail-cím pontos egyezés"), (f'"{t.email.strip()}" (site:pastebin.com OR site:github.com)', "e-mail paste-ben / kódban")]
        if t.username:
            subj += [(f'"{t.username.strip().lstrip("@")}"', "felhasználónév pontos egyezés")]
        if t.phone:
            subj += [(f'"{t.phone.strip()}"', "telefonszám pontos egyezés")]
    for q, label in subj:
        out.append(Finding("dork", "manual", f"[dork] {label}: {q}", "", url=_g(q), severity="info", data={"q": q}))
    return out


def run(t: Target, http, log, case) -> list[Finding]:
    out: list[Finding] = []
    if "dorks" in set(case.get("modules") or []):
        out += dorks(t, case)
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
