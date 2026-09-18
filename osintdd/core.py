"""Ügykezelés, SQLite tárolás, teljes lekérés-naplózás."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import sys


def _default_home() -> Path:
    repo = Path(__file__).resolve().parent.parent
    if not getattr(sys, "frozen", False) and (repo / "pyproject.toml").exists() and (repo / ".git").exists():
        return repo / "data"  # fejlesztői futtatás a repóból
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "osint-dd"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home())) / "osint-dd"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "osint-dd"


BASE_DIR = Path(os.environ.get("OSINTDD_HOME") or _default_home())
BASE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = BASE_DIR / "osintdd.sqlite"
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
REPORT_DIR = BASE_DIR / "reports"
REPORT_DIR.mkdir(exist_ok=True)

LEGAL_BASES = {
    "jogos_erdek": "GDPR 6. cikk (1) f) – jogos érdek (érdekmérlegelési teszt dokumentálva)",
    "szerzodes": "GDPR 6. cikk (1) b) – szerződés teljesítése / előkészítése",
    "jogi_kotelezettseg": "GDPR 6. cikk (1) c) – jogi kötelezettség (pl. Pmt., NIS2, kiberbiztonsági tv.)",
    "hozzajarulas": "GDPR 6. cikk (1) a) – az érintett hozzájárulása",
    "nem_szemelyes": "Nem személyes adat (csak cég / szolgáltatás / domain)",
}


# Modulok: (kulcs, csoport). Csoport: core | person | grey
MODULES_META = [
    ("company", "core"), ("sanctions", "core"), ("domain", "core"), ("web", "core"), ("manual", "core"),
    ("person", "person"), ("phone", "person"),
    ("breach", "grey"), ("aleph", "grey"), ("social", "grey"), ("face", "grey"),
]
DEFAULT_MODULES = [m for m, g in MODULES_META if g != "grey"]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class Target:
    """Mit vizsgálunk. Bármelyik mező üres lehet."""
    company: str = ""          # cégnév
    tax_id: str = ""           # magyar adószám (8 / 11 jegy) vagy EU VAT
    country: str = "HU"
    person: str = ""           # természetes személy neve
    email: str = ""
    username: str = ""
    phone: str = ""
    domain: str = ""
    extra_keywords: list[str] = field(default_factory=list)
    # pontosító (szűrő) adatok – ha a név nem egyértelmű
    birth_year: str = ""       # személy születési éve
    location: str = ""         # személy lakhelye / cég székhelye (város)
    employer: str = ""         # személy munkahelye / pozíciója
    reg_number: str = ""       # cégjegyzékszám (pl. 01-10-041234)

    def disambiguators(self) -> list[str]:
        return [x for x in [self.birth_year, self.location, self.employer, self.reg_number] if x]

    def has_person_data(self) -> bool:
        return any([self.person, self.email, self.username, self.phone])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Target":
        d = dict(d)
        d["extra_keywords"] = list(d.get("extra_keywords") or [])
        return cls(**{k: d.get(k, "") for k in cls.__dataclass_fields__} | {"extra_keywords": d["extra_keywords"]})


@dataclass
class Finding:
    """Egy forrásból származó, strukturált megállapítás."""
    source: str
    category: str             # company / sanctions / web / domain / person / phone / manual
    title: str
    summary: str = ""
    url: str = ""
    severity: str = "info"    # info / low / medium / high
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Store:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        c = self.conn
        c.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT NOT NULL,
                purpose TEXT NOT NULL,
                legal_basis TEXT NOT NULL,
                person_checks INTEGER NOT NULL DEFAULT 0,
                requester TEXT,
                target_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                report_path TEXT,
                lang TEXT NOT NULL DEFAULT 'hu'
            );
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT,
                url TEXT,
                severity TEXT,
                data_json TEXT
            );
            CREATE TABLE IF NOT EXISTS query_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT,
                run_id TEXT,
                ts TEXT NOT NULL,
                source TEXT NOT NULL,
                action TEXT NOT NULL,
                request TEXT,
                status TEXT,
                duration_ms INTEGER,
                result_count INTEGER,
                error TEXT,
                raw_path TEXT
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                actor TEXT,
                event TEXT NOT NULL,
                case_id TEXT,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                summary_md TEXT,
                backend TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_findings_case ON findings(case_id);
            CREATE INDEX IF NOT EXISTS idx_qlog_case ON query_log(case_id);
            """
        )
        c.commit()
        cols = {r[1] for r in c.execute("PRAGMA table_info(cases)")}
        if "lang" not in cols:
            c.execute("ALTER TABLE cases ADD COLUMN lang TEXT NOT NULL DEFAULT 'hu'")
            c.commit()
        if "modules_json" not in cols:
            c.execute("ALTER TABLE cases ADD COLUMN modules_json TEXT")
            c.commit()
        if "parent_id" not in cols:
            c.execute("ALTER TABLE cases ADD COLUMN parent_id TEXT")
            c.commit()

    # ---- cases -------------------------------------------------------------
    def create_case(self, title: str, purpose: str, legal_basis: str, target: Target,
                    person_checks: bool = False, requester: str = "", lang: str = "hu",
                    modules: list[str] | None = None, parent_id: str | None = None) -> str:
        if legal_basis not in LEGAL_BASES:
            raise ValueError(f"Ismeretlen jogalap: {legal_basis}. Választható: {', '.join(LEGAL_BASES)}")
        if person_checks and legal_basis == "nem_szemelyes":
            raise ValueError("Személyes ellenőrzéshez tényleges GDPR-jogalapot kell megadni.")
        if not (target.company or target.domain or target.tax_id or (person_checks and target.has_person_data())):
            raise ValueError("Adj meg legalább cégnevet, adószámot vagy domaint (személyi modulhoz személyt).")
        cid = uuid.uuid4().hex[:12]
        ts = now_iso()
        self.conn.execute(
            "INSERT INTO cases (id, created_at, updated_at, title, purpose, legal_basis, person_checks, requester, target_json, status, report_path, lang, modules_json, parent_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, ts, ts, title, purpose, legal_basis, int(person_checks), requester,
             json.dumps(target.to_dict(), ensure_ascii=False), "new", None, lang if lang in ("hu", "en") else "hu",
             json.dumps(modules or DEFAULT_MODULES), parent_id),
        )
        self.conn.commit()
        self.audit("case_created", cid, f"jogalap={legal_basis} szemely={person_checks} modulok={','.join(modules or DEFAULT_MODULES)} cel={purpose}")
        return cid

    def get_case(self, cid: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["target"] = Target.from_dict(json.loads(d.pop("target_json")))
        d["person_checks"] = bool(d["person_checks"])
        d["modules"] = json.loads(d.pop("modules_json") or "null") or DEFAULT_MODULES
        return d

    def list_cases(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["target"] = json.loads(d.pop("target_json"))
            out.append(d)
        return out

    def set_status(self, cid: str, status: str, report_path: str | None = None) -> None:
        self.conn.execute("UPDATE cases SET status=?, updated_at=?, report_path=COALESCE(?, report_path) WHERE id=?",
                          (status, now_iso(), report_path, cid))
        self.conn.commit()

    def save_summary(self, cid: str, run_id: str, summary_md: str, backend: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO runs (run_id, case_id, created_at, summary_md, backend) VALUES (?,?,?,?,?)",
                          (run_id, cid, now_iso(), summary_md, backend))
        self.conn.commit()

    def get_summary(self, cid: str, run_id: str | None = None) -> dict | None:
        q = "SELECT * FROM runs WHERE case_id=?" + (" AND run_id=?" if run_id else "") + " ORDER BY created_at DESC LIMIT 1"
        r = self.conn.execute(q, (cid, run_id) if run_id else (cid,)).fetchone()
        return dict(r) if r else None

    def children(self, cid: str) -> list[dict]:
        return [c for c in self.list_cases() if c.get("parent_id") == cid]

    def update_target(self, cid: str, target: Target, note: str = "") -> None:
        self.conn.execute("UPDATE cases SET target_json=?, updated_at=? WHERE id=?",
                          (json.dumps(target.to_dict(), ensure_ascii=False), now_iso(), cid))
        self.conn.commit()
        self.audit("target_refined", cid, note or ",".join(target.disambiguators()))

    def delete_case(self, cid: str) -> None:
        for t in ("findings", "query_log"):
            self.conn.execute(f"DELETE FROM {t} WHERE case_id=?", (cid,))
        self.conn.execute("DELETE FROM cases WHERE id=?", (cid,))
        self.conn.commit()
        self.audit("case_deleted", cid, "")

    # ---- findings ----------------------------------------------------------
    def add_findings(self, cid: str, run_id: str, findings: Iterable[Finding]) -> int:
        n = 0
        for f in findings:
            self.conn.execute(
                "INSERT INTO findings (case_id, run_id, created_at, source, category, title, summary, url, severity, data_json)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (cid, run_id, now_iso(), f.source, f.category, f.title, f.summary, f.url, f.severity,
                 json.dumps(f.data, ensure_ascii=False, default=str)),
            )
            n += 1
        self.conn.commit()
        return n

    def get_findings(self, cid: str, run_id: str | None = None) -> list[dict]:
        q = "SELECT * FROM findings WHERE case_id=?"
        args: list[Any] = [cid]
        if run_id:
            q += " AND run_id=?"
            args.append(run_id)
        q += " ORDER BY id"
        out = []
        for r in self.conn.execute(q, args).fetchall():
            d = dict(r)
            d["data"] = json.loads(d.pop("data_json") or "{}")
            out.append(d)
        return out

    # ---- logging -----------------------------------------------------------
    def log_query(self, cid: str | None, run_id: str | None, source: str, action: str, request: Any,
                  status: str, duration_ms: int, result_count: int | None = None,
                  error: str | None = None, raw: Any = None) -> None:
        raw_path = None
        if raw is not None:
            d = CACHE_DIR / "raw" / (cid or "nocase")
            d.mkdir(parents=True, exist_ok=True)
            fn = d / f"{int(time.time()*1000)}_{source}_{uuid.uuid4().hex[:6]}.json"
            try:
                fn.write_text(json.dumps(raw, ensure_ascii=False, indent=1, default=str)[:5_000_000], encoding="utf-8")
                raw_path = str(fn)
            except Exception:  # noqa: BLE001
                raw_path = None
        self.conn.execute(
            "INSERT INTO query_log (case_id, run_id, ts, source, action, request, status, duration_ms, result_count, error, raw_path)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (cid, run_id, now_iso(), source, action,
             request if isinstance(request, str) else json.dumps(request, ensure_ascii=False, default=str),
             status, duration_ms, result_count, error, raw_path),
        )
        self.conn.commit()

    def get_query_log(self, cid: str, run_id: str | None = None) -> list[dict]:
        q = "SELECT * FROM query_log WHERE case_id=?"
        args: list[Any] = [cid]
        if run_id:
            q += " AND run_id=?"
            args.append(run_id)
        return [dict(r) for r in self.conn.execute(q + " ORDER BY id", args).fetchall()]

    def audit(self, event: str, cid: str | None = None, detail: str = "", actor: str | None = None) -> None:
        self.conn.execute("INSERT INTO audit (ts, actor, event, case_id, detail) VALUES (?,?,?,?,?)",
                          (now_iso(), actor or os.environ.get("USER", "?"), event, cid, detail))
        self.conn.commit()

    def get_audit(self, limit: int = 200) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


class QueryLogger:
    """Kontextus, amit a forrásmodulok kapnak: minden HTTP-hívást naplóz."""

    def __init__(self, store: Store, case_id: str, run_id: str):
        self.store, self.case_id, self.run_id = store, case_id, run_id

    def log(self, source: str, action: str, request: Any, status: str, started: float,
            result_count: int | None = None, error: str | None = None, raw: Any = None) -> None:
        self.store.log_query(self.case_id, self.run_id, source, action, request, status,
                             int((time.time() - started) * 1000), result_count, error, raw)
