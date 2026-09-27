"""Entitásgráf – FollowTheMoney-szerű, állítás-szintű eredetjelöléssel, csak hozzáfűzéssel bővülő tár.

Entitás: {id, schema, properties}. Minden property-érték egy 'statement', amely rögzíti a forrást (modul), az URL-t,
a futást és a megállapítást, amelyből származik. A 'same_as' jelöltek pontszámmal a felülvizsgálati sorba kerülnek;
elfogadás/elutasítás nem töröl semmit, csak egy kapcsolatot rögzít. Export: .ftm (JSON Lines, FtM-kompatibilis szerkezet) + CSV.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from urllib.parse import urlparse

from rapidfuzz import fuzz

from .core import Store, now_iso

SCHEMAS = {  # saját séma -> FtM séma az exportban
    "Person": "Person", "Company": "Company", "LegalEntity": "LegalEntity", "Domain": "Thing", "Email": "Thing",
    "Phone": "Thing", "UserAccount": "UserAccount", "Sanction": "Sanction", "DataBreach": "Thing", "Address": "Address", "Repository": "Thing",
}
PLATFORMS = ["linkedin", "facebook", "instagram", "x.com", "twitter", "tiktok", "youtube", "github", "gitlab", "reddit", "medium", "keybase", "pinterest", "telegram", "t.me", "threads", "mastodon"]


def _norm(s: str) -> str:
    s = re.sub(r"\b(kft|zrt|nyrt|bt|kkt|ltd|llc|inc|gmbh|ag|sa|plc|co|corp|limited|zártkörűen működő részvénytársaság|korlátolt felelősségű társaság)\b\.?", " ", (s or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s@.]", " ", s)).strip()


def entity_id(schema: str, key: str) -> str:
    return schema.lower()[:4] + "-" + hashlib.sha1(f"{schema}|{_norm(key)}".encode()).hexdigest()[:14]


def _platform(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    for p in PLATFORMS:
        if p in host:
            return {"t.me": "telegram", "x.com": "x", "twitter": "x"}.get(p, p)
    return host or "web"


class Graph:
    def __init__(self, store: Store):
        self.store = store
        self.conn = store.conn
        self._init()

    def _init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY, case_id TEXT NOT NULL, schema TEXT NOT NULL, caption TEXT NOT NULL,
                key TEXT NOT NULL, created_at TEXT NOT NULL, is_subject INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS statements (
                id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL, entity_id TEXT NOT NULL, prop TEXT NOT NULL, value TEXT NOT NULL,
                source TEXT NOT NULL, url TEXT, run_id TEXT, finding_id INTEGER, ts TEXT NOT NULL,
                UNIQUE(entity_id, prop, value, source)
            );
            CREATE TABLE IF NOT EXISTS same_as (
                id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL, a TEXT NOT NULL, b TEXT NOT NULL, score REAL NOT NULL,
                reason TEXT, status TEXT NOT NULL DEFAULT 'pending', decided_by TEXT, decided_at TEXT, ts TEXT NOT NULL,
                UNIQUE(a, b)
            );
            CREATE INDEX IF NOT EXISTS idx_ent_case ON entities(case_id);
            CREATE INDEX IF NOT EXISTS idx_ent_key ON entities(schema, key);
            CREATE INDEX IF NOT EXISTS idx_stmt_ent ON statements(entity_id);
            """
        )
        self.conn.commit()

    # ---- írás (csak hozzáfűzés) ------------------------------------------
    def entity(self, case_id: str, schema: str, key: str, caption: str | None = None, subject: bool = False) -> str:
        eid = entity_id(schema, key) + "-" + case_id[:4]
        self.conn.execute("INSERT OR IGNORE INTO entities (id, case_id, schema, caption, key, created_at, is_subject) VALUES (?,?,?,?,?,?,?)",
                          (eid, case_id, schema, caption or key, _norm(key), now_iso(), int(subject)))
        if subject:
            self.conn.execute("UPDATE entities SET is_subject=1 WHERE id=?", (eid,))
        return eid

    def stmt(self, case_id: str, eid: str, prop: str, value, source: str, url: str = "", run_id: str = "", finding_id: int | None = None) -> None:
        if value in (None, "", [], {}):
            return
        vals = value if isinstance(value, (list, tuple, set)) else [value]
        for v in vals:
            self.conn.execute("INSERT OR IGNORE INTO statements (case_id, entity_id, prop, value, source, url, run_id, finding_id, ts) VALUES (?,?,?,?,?,?,?,?,?)",
                              (case_id, eid, prop, str(v)[:2000], source, url or "", run_id, finding_id, now_iso()))

    def same_as(self, case_id: str, a: str, b: str, score: float, reason: str) -> None:
        if a == b:
            return
        a, b = sorted([a, b])
        self.conn.execute("INSERT OR IGNORE INTO same_as (case_id, a, b, score, reason, ts) VALUES (?,?,?,?,?,?)", (case_id, a, b, round(score, 1), reason, now_iso()))

    def decide(self, sid: int, accept: bool, by: str = "") -> None:
        self.conn.execute("UPDATE same_as SET status=?, decided_by=?, decided_at=? WHERE id=?", ("accepted" if accept else "rejected", by, now_iso(), sid))
        self.conn.commit()

    # ---- olvasás -----------------------------------------------------------
    def entities(self, case_id: str | None = None) -> list[dict]:
        q = "SELECT * FROM entities" + (" WHERE case_id=?" if case_id else "") + " ORDER BY is_subject DESC, schema, caption"
        rows = [dict(r) for r in self.conn.execute(q, (case_id,) if case_id else ()).fetchall()]
        for e in rows:
            props: dict[str, list[dict]] = defaultdict(list)
            for s in self.conn.execute("SELECT prop, value, source, url, run_id, finding_id FROM statements WHERE entity_id=? ORDER BY id", (e["id"],)):
                props[s["prop"]].append(dict(s))
            e["properties"] = dict(props)
            e["links"] = [dict(r) for r in self.conn.execute("SELECT * FROM same_as WHERE (a=? OR b=?) AND status='accepted'", (e["id"], e["id"]))]
        return rows

    def review_queue(self, case_id: str | None = None, status: str = "pending") -> list[dict]:
        q = "SELECT s.*, ea.caption AS a_caption, ea.schema AS a_schema, eb.caption AS b_caption, eb.schema AS b_schema FROM same_as s JOIN entities ea ON ea.id=s.a JOIN entities eb ON eb.id=s.b WHERE s.status=?"
        args: list = [status]
        if case_id:
            q += " AND s.case_id=?"
            args.append(case_id)
        return [dict(r) for r in self.conn.execute(q + " ORDER BY s.score DESC, s.id", args).fetchall()]

    def cross_case(self, case_id: str) -> list[dict]:
        """Ugyanaz az entitás (séma + kulcs) más ügyekben is előfordul-e."""
        return [dict(r) for r in self.conn.execute(
            "SELECT e1.caption, e1.schema, e2.case_id AS other_case, c.title AS other_title FROM entities e1 JOIN entities e2 ON e1.schema=e2.schema AND e1.key=e2.key AND e1.case_id<>e2.case_id "
            "JOIN cases c ON c.id=e2.case_id WHERE e1.case_id=? ORDER BY e1.caption", (case_id,)).fetchall()]

    # ---- export ------------------------------------------------------------
    def export_ftm(self, case_id: str) -> str:
        lines = []
        for e in self.entities(case_id):
            props = {k: sorted({s["value"] for s in v}) for k, v in e["properties"].items()}
            props.setdefault("name", [e["caption"]])
            for l in e["links"]:
                props.setdefault("sameAs", []).append(l["b"] if l["a"] == e["id"] else l["a"])
            lines.append(json.dumps({"id": e["id"], "schema": SCHEMAS.get(e["schema"], "Thing"), "properties": props,
                                     "provenance": {"case": case_id, "x_schema": e["schema"]}}, ensure_ascii=False))
        return "\n".join(lines) + "\n"

    def export_csv(self, case_id: str) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["entity_id", "schema", "caption", "prop", "value", "source", "url", "run_id", "finding_id"])
        for e in self.entities(case_id):
            for prop, sts in e["properties"].items():
                for s in sts:
                    w.writerow([e["id"], e["schema"], e["caption"], prop, s["value"], s["source"], s["url"], s["run_id"], s["finding_id"]])
        return buf.getvalue()


# ---------------------------------------------------------------- építés a megállapításokból
def build_graph(store: Store, case: dict, run_id: str) -> dict:
    g = Graph(store)
    cid = case["id"]
    t = case["target"]
    person = case.get("person_checks")
    fs = store.get_findings(cid, run_id)
    subjects: list[str] = []

    def S(eid, prop, val, f):
        g.stmt(cid, eid, prop, val, f["source"], f.get("url", ""), run_id, f.get("id"))

    # --- alanyok
    comp = g.entity(cid, "Company", t.tax_id or t.company, t.company or t.tax_id, subject=True) if (t.company or t.tax_id) else None
    if comp:
        g.stmt(cid, comp, "name", t.company, "target", run_id=run_id)
        g.stmt(cid, comp, "vatCode", t.tax_id, "target", run_id=run_id)
        g.stmt(cid, comp, "registrationNumber", t.reg_number, "target", run_id=run_id)
        g.stmt(cid, comp, "website", t.domain, "target", run_id=run_id)
        subjects.append(comp)
    dom = g.entity(cid, "Domain", t.domain, t.domain, subject=True) if t.domain else None
    if dom:
        g.stmt(cid, dom, "name", t.domain, "target", run_id=run_id)
        subjects.append(dom)
    per = None
    if person and t.person:
        per = g.entity(cid, "Person", t.person + "|" + cid, t.person, subject=True)
        for prop, v in (("name", t.person), ("email", t.email), ("phone", t.phone), ("birthDate", t.birth_year), ("address", t.location), ("position", t.employer)):
            g.stmt(cid, per, prop, v, "target", run_id=run_id)
        if t.username:
            acc = g.entity(cid, "UserAccount", "self|" + t.username, "@" + t.username.lstrip("@"))
            g.stmt(cid, acc, "username", t.username, "target", run_id=run_id)
            g.stmt(cid, acc, "holder", per, "target", run_id=run_id)
        subjects.append(per)

    for f in fs:
        src, d = f["source"], f.get("data") or {}
        # --- cégadatok
        if src == "vies" and comp and d.get("name"):
            S(comp, "name", d["name"].strip(), f); S(comp, "address", (d.get("address") or "").replace("\n", ", ").strip(), f); S(comp, "vatCode", d.get("vat"), f)
        elif src == "gleif" and d.get("lei"):
            ent = d.get("entity", {})
            name = ent.get("legalName", {}).get("name", "")
            le = g.entity(cid, "LegalEntity", d["lei"], name)
            S(le, "leiCode", d["lei"], f); S(le, "name", name, f); S(le, "jurisdiction", ent.get("jurisdiction"), f)
            S(le, "address", ", ".join(x for x in [ent.get("legalAddress", {}).get("city"), ent.get("legalAddress", {}).get("country")] if x), f)
            if comp:
                g.same_as(cid, comp, le, fuzz.token_set_ratio(_norm(t.company), _norm(name)), "GLEIF névillesztés")
        elif src == "ddg_registry" and comp:
            S(comp, "registrySnippet", f["title"], f)
        # --- domain
        elif src == "dns" and dom and "A" in d:
            for ip in d.get("A", []): S(dom, "ipAddress", ip, f)
            for mx in d.get("MX", []): S(dom, "mx", mx, f)
            for ns in d.get("NS", []): S(dom, "nameserver", ns, f)
        elif src == "crtsh" and dom:
            S(dom, "subdomain", d.get("subdomains", [])[:100], f)
        elif src == "internetdb" and dom and d.get("ip"):
            S(dom, "openPort", [str(p) for p in d.get("ports", [])], f); S(dom, "cve", d.get("vulns", []), f)
        elif src in ("rdap", "whois") and dom:
            S(dom, "registration", f["summary"][:300], f)
        elif src == "wayback" and dom:
            S(dom, "firstSeen", f["title"].split("mentés", 1)[-1].strip(), f)
        # --- szankció
        elif f["category"] == "sanctions" and f["severity"] in ("high", "medium") and d.get("list"):
            listed = g.entity(cid, "Person" if str(d.get("type", "")).lower().startswith(("p", "i")) else "LegalEntity", f"{d['list']}|{f['title']}", f["title"].split(": ", 1)[-1])
            S(listed, "sanctionList", d["list"], f); S(listed, "program", d.get("program"), f)
            sanc = g.entity(cid, "Sanction", f"{d['list']}|{d.get('query')}", f"{d['list']} – {d.get('query')}")
            S(sanc, "authority", d["list"], f); S(sanc, "entity", listed, f); S(sanc, "program", d.get("program"), f)
            subj = comp if d.get("query") == t.company else per
            if subj:
                g.same_as(cid, subj, listed, float(d.get("score", 0)), f"szankciós fuzzy névegyezés ({d['list']})")
        # --- személy
        elif src in ("username", "maigret") and per and f.get("url"):
            acc = g.entity(cid, "UserAccount", f"{_platform(f['url'])}|{t.username}", f"{_platform(f['url'])}: @{t.username.lstrip('@')}")
            S(acc, "service", _platform(f["url"]), f); S(acc, "username", t.username, f); S(acc, "url", f["url"], f)
            g.same_as(cid, per, acc, 60.0, "azonos felhasználónév – személyazonosság nem igazolt")
        elif src == "holehe" and per and f["title"].startswith("E-mail regisztrálva"):
            svc = f["title"].split(": ", 1)[-1]
            acc = g.entity(cid, "UserAccount", f"{svc}|{t.email}", f"{svc}: {t.email}")
            S(acc, "service", svc, f); S(acc, "email", t.email, f); S(acc, "holder", per, f)
        elif src == "gravatar" and per:
            S(per, "alias", d.get("displayName"), f); S(per, "website", d.get("profileUrl"), f)
        elif src == "github" and f["category"] == "person" and per and d.get("login"):
            acc = g.entity(cid, "UserAccount", f"github|{d['login']}", f"github: @{d['login']}")
            S(acc, "service", "github", f); S(acc, "username", d["login"], f); S(acc, "url", f["url"], f); S(acc, "name", d.get("name"), f)
            S(acc, "company", d.get("company"), f); S(acc, "location", d.get("location"), f); S(acc, "email", d.get("email"), f)
            g.same_as(cid, per, acc, 60.0, "azonos felhasználónév (GitHub)")
        elif src == "github" and d.get("emails") and per:
            for e in d["emails"]: S(per, "emailCandidate", e, f)
        elif src == "github" and f["category"] == "company" and comp and d.get("login"):
            org = g.entity(cid, "Repository", f"github-org|{d['login']}", f"github org: {d['login']}")
            S(org, "url", f["url"], f); S(org, "name", d.get("name"), f); S(org, "website", d.get("blog"), f)
            g.same_as(cid, comp, org, fuzz.token_set_ratio(_norm(t.company), _norm(d.get("name") or d["login"])), "GitHub-szervezet névegyezés")
        elif src == "social" and per and f.get("url"):
            plat = _platform(f["url"])
            acc = g.entity(cid, "UserAccount", f"{plat}|{f['url']}", f"{plat}: {f['title'][:60]}")
            S(acc, "service", plat, f); S(acc, "url", f["url"], f); S(acc, "title", f["title"], f)
            g.same_as(cid, per, acc, 75.0 if f["title"].startswith("✓") else 50.0, "keresőmotoros profiltalálat" + (" (pontosító adat egyezik)" if f["title"].startswith("✓") else ""))
        elif src in ("leakcheck", "hibp", "dehashed") and f["severity"] == "medium":
            br = g.entity(cid, "DataBreach", f"{src}|{f['title']}", f["title"])
            S(br, "summary", f["summary"][:500], f); S(br, "subject", t.email or t.username, f)
            if per: S(per, "breach", br, f)
        elif src == "paste_search" and f["severity"] == "medium":
            pe = g.entity(cid, "DataBreach", f"paste|{f.get('url')}", f["title"])
            S(pe, "url", f["url"], f); S(pe, "query", d.get("query"), f)
            for sj in subjects: S(sj, "paste", pe, f)
        elif src == "phone" and per and d.get("e164"):
            ph = g.entity(cid, "Phone", d["e164"], d["e164"])
            S(ph, "number", d["e164"], f); S(ph, "summary", f["summary"], f); S(per, "phone", d["e164"], f)
        elif src == "gdelt_geo" and d.get("points"):
            for sj in subjects[:1]:
                S(sj, "newsLocation", [f"{p['name']} ({p['count']})" for p in d["points"][:10]], f)
        elif src == "aleph" and d.get("id"):
            al = g.entity(cid, "LegalEntity" if d.get("schema") != "Person" else "Person", f"aleph|{d['id']}", f["title"].split(": ", 1)[-1])
            S(al, "alephId", d["id"], f); S(al, "collection", d.get("collection"), f); S(al, "url", f["url"], f)
            subj = comp if comp else per
            if subj: g.same_as(cid, subj, al, 65.0, "OCCRP Aleph találat")
    g.conn.commit()
    pending = len(g.review_queue(cid))
    store.audit("graph_built", cid, f"run={run_id} entities={len(g.entities(cid))} pending_same_as={pending}")
    return {"entities": len(g.entities(cid)), "pending": pending}
