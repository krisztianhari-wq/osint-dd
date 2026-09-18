"""Személyi modul – CSAK rögzített jogalappal fut. Felhasználónév-ellenőrzés, e-mail nyomok, Gravatar.
Opcionális külső eszközök, ha telepítve: maigret, holehe (pip). Fizetős (nem beépített): HIBP, DeHashed, IntelX."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time

from ..core import Finding, Target
from ..http import Http

# egyszerű Sherlock-jellegű ellenőrzés: url minta, "nem létezik" jelző
SITES = {
    "GitHub": ("https://github.com/{u}", 404),
    "GitLab": ("https://gitlab.com/{u}", 404),
    "Reddit": ("https://www.reddit.com/user/{u}/about.json", 404),
    "X/Twitter": ("https://x.com/{u}", None),
    "Instagram": ("https://www.instagram.com/{u}/", None),
    "TikTok": ("https://www.tiktok.com/@{u}", 404),
    "YouTube": ("https://www.youtube.com/@{u}", 404),
    "Medium": ("https://medium.com/@{u}", 404),
    "Keybase": ("https://keybase.io/{u}", 404),
    "HackerNews": ("https://hacker-news.firebaseio.com/v0/user/{u}.json", "null"),
    "Pinterest": ("https://www.pinterest.com/{u}/", 404),
    "Telegram": ("https://t.me/{u}", None),
    "Steam": ("https://steamcommunity.com/id/{u}", None),
    "Docker Hub": ("https://hub.docker.com/v2/users/{u}/", 404),
    "PyPI": ("https://pypi.org/user/{u}/", 404),
    "npm": ("https://www.npmjs.com/~{u}", 404),
    "Behance": ("https://www.behance.net/{u}", 404),
    "SoundCloud": ("https://soundcloud.com/{u}", 404),
    "Twitch": ("https://m.twitch.tv/{u}", None),
    "Mastodon.social": ("https://mastodon.social/@{u}", 404),
}


def _which(name: str) -> str | None:
    import sys
    from pathlib import Path
    cand = Path(sys.prefix) / "bin" / name
    return str(cand) if cand.exists() else shutil.which(name)


def _tool(name: str, args: list[str], http: Http, source: str) -> str | None:
    exe = _which(name)
    if not exe:
        return None
    name = exe
    started = time.time()
    try:
        p = subprocess.run([name, *args], capture_output=True, text=True, timeout=240)
        http.log.log(source, "cli", {"cmd": [name, *args]}, f"rc={p.returncode}", started, None, None if p.returncode == 0 else p.stderr[-500:], raw=p.stdout[-30000:])
        return p.stdout
    except Exception as e:  # noqa: BLE001
        http.log.log(source, "cli", {"cmd": [name, *args]}, "ERROR", started, 0, str(e))
        return None


def run(t: Target, http: Http, log, case) -> list[Finding]:
    if not case.get("person_checks"):
        return []
    out: list[Finding] = []
    out.append(Finding("policy", "person", "Személyi modul aktív", f"Jogalap: {case.get('legal_basis')} · cél: {case.get('purpose')}", severity="info"))

    if t.username:
        u = t.username.strip().lstrip("@")
        found = []
        for site, (pat, nf) in SITES.items():
            body, r = http.get("username", pat.format(u=u), save_raw=False)
            if r is None:
                continue
            exists = False
            if nf == 404:
                exists = r.status_code == 200
            elif nf == "null":
                exists = r.status_code == 200 and (body or "").strip() != "null"
            else:
                exists = r.status_code == 200 and u.lower() in (body or "").lower()[:200000]
            if exists:
                found.append((site, pat.format(u=u)))
            time.sleep(0.3)
        for site, url in found:
            out.append(Finding("username", "person", f"Felhasználónév létezik: {site}", f"@{u}", url=url, severity="info", data={"site": site}))
        out.append(Finding("username", "person", f"Felhasználónév-ellenőrzés: {len(found)}/{len(SITES)} találat", "Egyező név ≠ azonos személy; kézi ellenőrzés kell.", severity="info"))
        import tempfile, pathlib as _pl
        tmpd = tempfile.mkdtemp(prefix="maigret_")
        mg = _tool("maigret", ["--json", "simple", "--no-progressbar", "--no-color", "--timeout", "15", "--folderoutput", tmpd, "--top-sites", "500", u], http, "maigret")
        if mg is not None:
            found_mg = []
            for jf in _pl.Path(tmpd).glob("*.json"):
                try:
                    for site, info in json.loads(jf.read_text()).items():
                        if info.get("status", {}).get("status") == "Claimed":
                            found_mg.append((site, info.get("url_user", "")))
                except Exception:  # noqa: BLE001
                    pass
            for site, url in found_mg[:60]:
                out.append(Finding("maigret", "person", f"maigret: fiók létezik – {site}", f"@{u}", url=url, severity="info"))
            out.append(Finding("maigret", "person", f"maigret: {len(found_mg)} fiók (top 500 oldal)", "Egyező név ≠ azonos személy.", severity="info"))
        if mg is None:
            out.append(Finding("maigret", "person", "maigret nincs telepítve (opcionális, ingyenes)", "Telepítés: .venv/bin/pip install maigret – 3000+ oldal ellenőrzése.", severity="info"))

    if t.email:
        e = t.email.strip().lower()
        h = hashlib.md5(e.encode()).hexdigest()  # noqa: S324 – Gravatar protokoll
        body, r = http.get("gravatar", f"https://www.gravatar.com/{h}.json", expect_json=True)
        if isinstance(body, dict) and body.get("entry"):
            en = body["entry"][0]
            out.append(Finding("gravatar", "person", f"Gravatar-profil: {en.get('displayName') or en.get('preferredUsername')}",
                               f"helyszín: {en.get('currentLocation','-')} · fiókok: {', '.join(a.get('shortname','') for a in en.get('accounts', []))}",
                               url=en.get("profileUrl", ""), severity="info", data=en))
        dom = e.split("@")[-1]
        if dom not in ("gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "freemail.hu", "citromail.hu", "protonmail.com", "proton.me"):
            out.append(Finding("email", "person", f"E-mail domain: {dom}", "Céges domain – a domain-modul futtatásához add meg a domaint a célnál.", severity="info"))

        def _parse(txt: str) -> tuple[set, set, set]:
            used, unused, rl = set(), set(), set()
            for l in txt.splitlines():
                l = l.strip()
                if "Email used" in l or "websites checked" in l or not l[:3] in ("[+]", "[-]", "[x]"):
                    continue
                site = l[3:].strip().split(" ")[0]
                (used if l.startswith("[+]") else unused if l.startswith("[-]") else rl).add(site)
            return used, unused, rl

        hh = _tool("holehe", ["--no-color", "--no-clear", e], http, "holehe")
        if hh:
            used, unused, rl = _parse(hh)
            if rl:
                time.sleep(25)  # rate-limitelt oldalak második kör
                hh2 = _tool("holehe", ["--no-color", "--no-clear", e], http, "holehe_retry")
                if hh2:
                    u2, n2, r2 = _parse(hh2)
                    used |= u2
                    unused |= n2 - used
                    rl = (rl & r2) - used - unused
            for site in sorted(used):
                out.append(Finding("holehe", "person", f"E-mail regisztrálva: {site}", "", url=f"https://{site}", severity="info"))
            out.append(Finding("holehe", "person", f"holehe: {len(used)} regisztráció · {len(unused)} nincs · {len(rl)} nem ellenőrizhető (rate limit)",
                               ("Nem ellenőrizhető: " + ", ".join(sorted(rl)[:30])) if rl else "Minden ellenőrzött szolgáltatás válaszolt.", severity="info",
                               data={"used": sorted(used), "rate_limited": sorted(rl)}))
        else:
            out.append(Finding("holehe", "person", "holehe nincs telepítve (opcionális, ingyenes)", "Telepítés: .venv/bin/pip install holehe – 120 szolgáltatásnál ellenőrzi az e-mail regisztrációját.", severity="info"))
        out.append(Finding("hibp", "person", "Adatszivárgás-ellenőrzés (HIBP) – FIZETŐS, nincs beépítve",
                           "Have I Been Pwned API ~5 USD/hó; DeHashed, IntelX, LeakCheck szintén fizetős/szürke zóna. Kézi link a jelentésben.",
                           url=f"https://haveibeenpwned.com/", severity="info"))
    return out
