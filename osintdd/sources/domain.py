"""Domain / infrastruktúra lábnyom – DNS, SPF/DMARC, crt.sh, RDAP/whois, Wayback, Shodan InternetDB (kulcs nélkül)."""
from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
import time

import dns.resolver

from ..core import Finding, Target
from ..http import Http


def _dns(name: str, rtype: str) -> list[str]:
    try:
        return [r.to_text() for r in dns.resolver.resolve(name, rtype, lifetime=6)]
    except Exception:  # noqa: BLE001
        return []


def run(t: Target, http: Http, log, case) -> list[Finding]:
    dom = (t.domain or "").strip().lower()
    dom = re.sub(r"^https?://", "", dom).split("/")[0]
    if not dom:
        return []
    out: list[Finding] = []
    started = time.time()
    rec = {rt: _dns(dom, rt) for rt in ("A", "AAAA", "MX", "NS", "TXT")}
    http.log.log("dns", "resolve", {"domain": dom}, "OK", started, sum(len(v) for v in rec.values()), raw=rec)
    out.append(Finding("dns", "domain", f"DNS rekordok: {dom}",
                       " · ".join(f"{k}: {', '.join(v)[:200]}" for k, v in rec.items() if v) or "Nincs feloldható rekord", severity="info", data=rec))

    # e-mail biztonság
    spf = [x for x in rec["TXT"] if "v=spf1" in x.lower()]
    dmarc = _dns(f"_dmarc.{dom}", "TXT")
    sev = "info"
    msg = []
    if rec["MX"] and not spf:
        sev, msg = "medium", ["nincs SPF rekord"]
    if rec["MX"] and not dmarc:
        sev = "medium"
        msg.append("nincs DMARC rekord")
    elif dmarc and "p=none" in dmarc[0].lower():
        sev = "low" if sev == "info" else sev
        msg.append("DMARC p=none (csak monitorozás)")
    out.append(Finding("dns", "domain", "E-mail hitelesítés (SPF/DMARC)",
                       (", ".join(msg) if msg else "SPF és DMARC jelen van") + f" · SPF: {spf[0] if spf else '-'} · DMARC: {dmarc[0] if dmarc else '-'}",
                       severity=sev, data={"spf": spf, "dmarc": dmarc}))

    # crt.sh – tanúsítványok, aldomainek
    body, r = http.get("crtsh", "https://crt.sh/", params={"q": f"%.{dom}", "output": "json"}, expect_json=True)
    if isinstance(body, list) and body:
        subs = sorted({n.strip().lower() for e in body for n in (e.get("name_value") or "").split("\n") if n and "*" not in n})
        newest = max(body, key=lambda e: e.get("not_before", ""))
        out.append(Finding("crtsh", "domain", f"Tanúsítványnapló: {len(body)} tanúsítvány, {len(subs)} egyedi hostnév",
                           f"Legújabb: {newest.get('issuer_name','')[:80]} ({newest.get('not_before','')[:10]}) · aldomainek: {', '.join(subs[:25])}{' …' if len(subs) > 25 else ''}",
                           url=f"https://crt.sh/?q=%25.{dom}", severity="info", data={"subdomains": subs[:300], "count": len(body)}))

    # RDAP (gTLD) / whois CLI fallback (.hu-nak nincs RDAP)
    body, r = http.get("rdap", f"https://rdap.org/domain/{dom}", expect_json=True)
    if isinstance(body, dict) and body.get("events"):
        ev = {e.get("eventAction"): e.get("eventDate", "")[:10] for e in body.get("events", [])}
        out.append(Finding("rdap", "domain", f"Regisztráció: {dom}",
                           f"regisztrálva {ev.get('registration','?')} · lejár {ev.get('expiration','?')} · státusz {', '.join(body.get('status', [])[:3])}",
                           severity="info", data={"events": ev, "status": body.get("status")}))
    elif shutil.which("whois"):
        started = time.time()
        try:
            w = subprocess.run(["whois", dom], capture_output=True, text=True, timeout=20).stdout
            http.log.log("whois", "cli", {"domain": dom}, "OK", started, 1, raw=w[:20000])
            keep = [l for l in w.splitlines() if not l.lstrip().startswith(("%", "#", ">>>")) and
                    re.search(r"record created|registered:|creation date|expir|registrar:|registrant|hun-id|domain status|^status|org:|organisation:", l, re.I)][:12]
            out.append(Finding("whois", "domain", f"WHOIS: {dom}", " · ".join(l.strip() for l in keep)[:600] or "nincs kiemelhető mező", severity="info", data={"lines": keep}))
        except Exception as e:  # noqa: BLE001
            http.log.log("whois", "cli", {"domain": dom}, "ERROR", started, 0, str(e))

    # Wayback – mióta létezik a webhely
    body, r = http.get("wayback", "https://web.archive.org/cdx/search/cdx",
                       params={"url": dom, "output": "json", "limit": 1, "fl": "timestamp", "filter": "statuscode:200"}, expect_json=True)
    body2, r2 = http.get("wayback", "https://web.archive.org/cdx/search/cdx",
                         params={"url": dom, "output": "json", "limit": -1, "fl": "timestamp", "filter": "statuscode:200"}, expect_json=True)
    first = body[1][0] if isinstance(body, list) and len(body) > 1 else None
    last = body2[1][0] if isinstance(body2, list) and len(body2) > 1 else None
    if first:
        out.append(Finding("wayback", "domain", f"Webarchívum: első mentés {first[:4]}-{first[4:6]}-{first[6:8]}",
                           f"utolsó mentés: {last[:4]}-{last[4:6]}-{last[6:8]}" if last else "", url=f"https://web.archive.org/web/*/{dom}", severity="info"))
    else:
        out.append(Finding("wayback", "domain", "Webarchívum: nincs mentés", "Nagyon új vagy alig látogatott webhely – fokozott figyelem.", severity="low"))

    # Shodan InternetDB – nyitott portok, ismert sérülékenységek IP-nként (kulcs nélkül)
    ips = [ip for ip in rec["A"] if not ipaddress.ip_address(ip).is_private][:5]
    for ip in ips:
        body, r = http.get("internetdb", f"https://internetdb.shodan.io/{ip}", expect_json=True)
        if isinstance(body, dict) and body.get("ip"):
            vulns = body.get("vulns", [])
            sev = "high" if vulns else "info"
            out.append(Finding("internetdb", "domain", f"Kitettség {ip}: portok {body.get('ports')}",
                               f"hostnevek: {', '.join(body.get('hostnames', [])[:5])} · CPE: {', '.join(body.get('cpes', [])[:5])} · CVE: {', '.join(vulns[:10])}{' …' if len(vulns) > 10 else ''}",
                               url=f"https://www.shodan.io/host/{ip}", severity=sev, data=body))
    return out
