"""GitHub – nyilvános profil, repók, szervezet, commit-e-mailek (személyi modullal), domain-említések kódban (tokennel).
Kulcs nélkül is működik (60 kérés/óra); OSINTDD_GITHUB_TOKEN emeli a limitet és engedi a kódkeresést."""
from __future__ import annotations

import os
import re
import time

from ..core import Finding, Target
from ..http import Http

API = "https://api.github.com"


def _h() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    tok = os.environ.get("OSINTDD_GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def run(t: Target, http: Http, log, case) -> list[Finding]:
    out: list[Finding] = []
    person = case.get("person_checks")
    token = bool(os.environ.get("OSINTDD_GITHUB_TOKEN"))

    # --- felhasználónév -> profil, repók, commit-e-mailek --------------------
    if person and t.username:
        u = t.username.strip().lstrip("@")
        body, r = http.get("github", f"{API}/users/{u}", headers=_h(), expect_json=True)
        if isinstance(body, dict) and body.get("login"):
            out.append(Finding("github", "person", f"GitHub-profil: {body.get('login')} ({body.get('name') or '-'})",
                               f"{body.get('bio') or ''} · cég: {body.get('company') or '-'} · hely: {body.get('location') or '-'} · "
                               f"repók: {body.get('public_repos')} · követők: {body.get('followers')} · létrehozva {str(body.get('created_at',''))[:10]}",
                               url=body.get("html_url", ""), severity="info", data={k: body.get(k) for k in ("login", "name", "company", "location", "blog", "email", "twitter_username", "created_at")}))
            if body.get("email"):
                out.append(Finding("github", "person", f"GitHub nyilvános e-mail: {body['email']}", "", url=body.get("html_url", ""), severity="info"))
            repos, r2 = http.get("github", f"{API}/users/{u}/repos", params={"per_page": 30, "sort": "updated"}, headers=_h(), expect_json=True)
            if isinstance(repos, list) and repos:
                top = sorted(repos, key=lambda x: x.get("stargazers_count", 0), reverse=True)[:8]
                out.append(Finding("github", "person", f"GitHub repók: {len(repos)} (legfrissebb 30)",
                                   " · ".join(f"{x['name']} ★{x.get('stargazers_count',0)} {x.get('language') or ''}" for x in top), url=body.get("html_url", ""), severity="info"))
            events, r3 = http.get("github", f"{API}/users/{u}/events/public", params={"per_page": 100}, headers=_h(), expect_json=True)
            emails: dict[str, int] = {}
            names: set[str] = set()
            for ev in events if isinstance(events, list) else []:
                for c in (ev.get("payload") or {}).get("commits") or []:
                    a = c.get("author") or {}
                    if a.get("email") and "noreply" not in a["email"]:
                        emails[a["email"]] = emails.get(a["email"], 0) + 1
                    if a.get("name"):
                        names.add(a["name"])
            if emails:
                out.append(Finding("github", "person", f"Commit-e-mailek a nyilvános eseményekből: {len(emails)}",
                                   ", ".join(f"{e} ({n})" for e, n in sorted(emails.items(), key=lambda x: -x[1])[:8]) + (f" · szerzőnevek: {', '.join(sorted(names)[:4])}" if names else ""),
                                   url=body.get("html_url", ""), severity="low", data={"emails": emails, "names": sorted(names)}))
        elif r is not None and r.status_code == 404:
            out.append(Finding("github", "person", f"GitHub: nincs '{u}' felhasználó", "", severity="info"))
        time.sleep(1)

    # --- e-mail -> commit-keresés -------------------------------------------
    if person and t.email:
        body, r = http.get("github", f"{API}/search/commits", params={"q": f"author-email:{t.email.strip()}", "per_page": 10}, headers=_h(), expect_json=True)
        if isinstance(body, dict) and body.get("total_count"):
            items = body.get("items", [])
            repos = sorted({i.get("repository", {}).get("full_name", "") for i in items})
            out.append(Finding("github", "person", f"Commitok ezzel az e-mail-címmel: {body['total_count']}",
                               f"repók: {', '.join(repos[:8])} · szerzőnév: {items[0].get('commit', {}).get('author', {}).get('name', '-') if items else '-'}",
                               url=f"https://github.com/search?q=author-email%3A{t.email.strip()}&type=commits", severity="low", data={"repos": repos}))
        elif isinstance(body, dict) and body.get("total_count") == 0:
            out.append(Finding("github", "person", "GitHub: nincs commit ezzel az e-mail-címmel", "", severity="info"))
        time.sleep(1)

    # --- cég -> szervezetek, repók -------------------------------------------
    if t.company:
        name = re.sub(r"\b(kft|zrt|nyrt|bt|ltd|llc|inc|gmbh|plc)\b\.?", "", t.company, flags=re.I).strip()
        body, r = http.get("github", f"{API}/search/users", params={"q": f"{name} type:org", "per_page": 5}, headers=_h(), expect_json=True)
        for org in (body or {}).get("items", [])[:3] if isinstance(body, dict) else []:
            o, r2 = http.get("github", f"{API}/orgs/{org['login']}", headers=_h(), expect_json=True)
            if isinstance(o, dict) and o.get("login"):
                out.append(Finding("github", "company", f"GitHub-szervezet: {o.get('login')} ({o.get('name') or '-'})",
                                   f"{o.get('description') or ''} · nyilvános repók: {o.get('public_repos')} · hely: {o.get('location') or '-'} · web: {o.get('blog') or '-'} · "
                                   f"e-mail: {o.get('email') or '-'} · létrehozva {str(o.get('created_at',''))[:10]}", url=o.get("html_url", ""), severity="info",
                                   data={k: o.get(k) for k in ("login", "name", "blog", "location", "email", "public_repos", "created_at")}))
            time.sleep(0.8)
        if not (isinstance(body, dict) and body.get("items")):
            out.append(Finding("github", "company", f"GitHub: nincs '{name}' nevű szervezet", "", severity="info"))
        time.sleep(1)

    # --- domain -> kód-említések (csak tokennel) -------------------------------
    if t.domain:
        d = t.domain.strip().lower()
        if token:
            body, r = http.get("github", f"{API}/search/code", params={"q": f'"{d}"', "per_page": 10}, headers=_h(), expect_json=True)
            if isinstance(body, dict) and body.get("total_count") is not None:
                items = body.get("items", [])
                sev = "low" if body["total_count"] else "info"
                out.append(Finding("github", "domain", f"Kód-említések GitHubon: {body['total_count']} ({d})",
                                   " · ".join(f"{i.get('repository', {}).get('full_name')}/{i.get('path')}" for i in items[:6]) or "nincs",
                                   url=f"https://github.com/search?q=%22{d}%22&type=code", severity=sev, data={"total": body["total_count"]}))
        else:
            out.append(Finding("github", "manual", f"GitHub kódkeresés a domainre (bejelentkezve): {d}", "Automatikus keresés OSINTDD_GITHUB_TOKEN-nel.",
                               url=f"https://github.com/search?q=%22{d}%22&type=code", severity="info"))
    return out
