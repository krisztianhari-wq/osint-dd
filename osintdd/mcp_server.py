"""osintdd MCP-szerver (stdio) – Claude Code / Claude Desktop / bármely MCP-kliens innen indíthat átvilágítást.

Beállítás Claude Desktopban (claude_desktop_config.json):
  {"mcpServers": {"osintdd": {"command": "/path/to/.venv/bin/osintdd", "args": ["mcp"]}}}
Claude Code-ban:  claude mcp add osintdd -- /path/to/.venv/bin/osintdd mcp
"""
from __future__ import annotations

import json
from typing import Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ConfigDict, Field

from .core import DEFAULT_MODULES, LEGAL_BASES, MODULES_META, Store, Target

server = MCPServer(
    "osintdd_mcp",
    instructions=("Local due-diligence / OSINT assistant (osint-dd by sadrobot). Every check is a *case* with a purpose and a GDPR legal basis. "
                  "Company/domain checks use legal_basis 'nem_szemelyes'. Person checks require person_checks=true AND a real GDPR basis "
                  "(jogos_erdek / szerzodes / jogi_kotelezettseg / hozzajarulas). Grey-zone modules (breach, paste, aleph, social, face) run only when listed explicitly. "
                  "Runs take 1–3 minutes. Findings carry source and URL; name matches never prove identity."),
)
_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False, default=str, indent=1)


class CreateCase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: str = Field(..., min_length=1, max_length=200, description="Case title, e.g. 'Vendor X onboarding'")
    purpose: str = Field(..., min_length=1, max_length=500, description="Why the check is done, e.g. 'NIS2 supplier risk assessment'")
    legal_basis: Literal["nem_szemelyes", "jogos_erdek", "szerzodes", "jogi_kotelezettseg", "hozzajarulas"] = Field("nem_szemelyes", description="GDPR basis key. 'nem_szemelyes' = no personal data (company/domain only).")
    company: str = Field("", description="Company name")
    tax_id: str = Field("", description="Hungarian tax number (8 or 11 digits) or EU VAT id")
    country: str = Field("HU", description="ISO country code for VAT lookup")
    domain: str = Field("", description="Primary domain, e.g. example.hu")
    reg_number: str = Field("", description="Company registration number (cégjegyzékszám), for disambiguation")
    location: str = Field("", description="Seat / residence city, for disambiguation")
    person: str = Field("", description="Natural person's name (requires person_checks and a legal basis)")
    email: str = Field("", description="Person's e-mail (person module)")
    username: str = Field("", description="Person's username/handle (person module)")
    phone: str = Field("", description="Person's phone in international format (person module)")
    birth_year: str = Field("", description="Birth year, for disambiguation")
    employer: str = Field("", description="Employer / position, for disambiguation")
    keywords: list[str] = Field(default_factory=list, description="Extra search keywords")
    person_checks: bool = Field(False, description="Enable the person module. Requires a GDPR legal basis other than 'nem_szemelyes'.")
    modules: list[str] = Field(default_factory=lambda: list(DEFAULT_MODULES), description="Modules to run. Core: company, sanctions, domain, web, github, geo, dorks, manual. Person: person, phone. Grey (explicit opt-in only): breach, paste, aleph, social, face.")
    lang: Literal["hu", "en"] = Field("hu", description="Report language")
    requester: str = Field("", description="Who requested the check (audit trail)")
    run: bool = Field(True, description="Run immediately (blocks 1–3 minutes) and return the summary")


@server.tool(name="osintdd_create_case", description="Create a due-diligence case (and by default run it and return the summary). Enforces GDPR gating: person data needs person_checks=true and a real legal basis.",
             annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def osintdd_create_case(params: CreateCase) -> str:
    known = {m for m, _ in MODULES_META}
    bad = [m for m in params.modules if m not in known]
    if bad:
        return _j({"error": f"unknown modules: {bad}", "allowed": sorted(known)})
    tg = Target(company=params.company, tax_id=params.tax_id, country=params.country, domain=params.domain, person=params.person, email=params.email,
                username=params.username, phone=params.phone, extra_keywords=params.keywords, birth_year=params.birth_year, location=params.location,
                employer=params.employer, reg_number=params.reg_number)
    mods = params.modules if params.person_checks else [m for m in params.modules if m not in ("person", "phone", "breach", "social", "face")]
    try:
        cid = store().create_case(params.title, params.purpose, params.legal_basis, tg, params.person_checks, params.requester or "mcp", params.lang, mods)
    except ValueError as e:
        return _j({"error": str(e), "legal_bases": LEGAL_BASES})
    store().audit("mcp_create", cid, f"modules={','.join(mods)}")
    out = {"case_id": cid, "modules": mods, "status": "created"}
    if params.run:
        out.update(_run(cid))
    return _j(out)


def _run(cid: str, only: list[str] | None = None) -> dict:
    from .runner import run_case
    log: list[str] = []
    run_id = run_case(store(), cid, log.append, only)
    c = store().get_case(cid)
    sm = store().get_summary(cid, run_id) or {}
    fs = store().get_findings(cid, run_id)
    sev = {k: sum(1 for f in fs if f["severity"] == k) for k in ("high", "medium", "low", "info")}
    return {"run_id": run_id, "status": "done", "report_path": c.get("report_path"), "findings": len(fs), "severity": sev,
            "identity_uncertain": any(f["category"] == "identity" for f in fs), "summary_backend": sm.get("backend"), "summary_md": sm.get("summary_md")}


class RunCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(..., description="Case id from osintdd_create_case / osintdd_list_cases")
    only: list[str] = Field(default_factory=list, description="Optional subset of modules to run (default: the case's modules)")


@server.tool(name="osintdd_run_case", description="(Re-)run a case's modules, regenerate the report and return the summary. Blocks 1–3 minutes.",
             annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
def osintdd_run_case(params: RunCase) -> str:
    if not store().get_case(params.case_id):
        return _j({"error": "case not found"})
    return _j(_run(params.case_id, params.only or None))


class ListCases(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(50, ge=1, le=500)


@server.tool(name="osintdd_list_cases", description="List cases (newest first) with status, subject and report path.", annotations={"readOnlyHint": True, "openWorldHint": False})
def osintdd_list_cases(params: ListCases) -> str:
    rows = store().list_cases()[: params.limit]
    return _j([{"case_id": c["id"], "title": c["title"], "status": c["status"], "created_at": c["created_at"], "legal_basis": c["legal_basis"],
                "person_checks": bool(c["person_checks"]), "subject": c["target"].get("company") or c["target"].get("domain") or c["target"].get("person"),
                "parent_id": c.get("parent_id"), "report_path": c.get("report_path")} for c in rows])


class GetFindings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    category: str = Field("", description="Filter: identity, sanctions, company, domain, web, geo, person, breach, paste, aleph, social, phone, manual")
    min_severity: Literal["info", "low", "medium", "high"] = Field("info", description="Minimum severity to include")
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=500)


@server.tool(name="osintdd_get_findings", description="Get a case's findings from its latest run, filtered and paginated. Each finding has source, category, severity, title, summary, url.",
             annotations={"readOnlyHint": True, "openWorldHint": False})
def osintdd_get_findings(params: GetFindings) -> str:
    fs = store().get_findings(params.case_id)
    if not fs:
        return _j({"total": 0, "findings": []})
    run_id = fs[-1]["run_id"]
    order = {"info": 0, "low": 1, "medium": 2, "low": 1, "high": 3}
    sel = [f for f in fs if f["run_id"] == run_id and (not params.category or f["category"] == params.category) and order.get(f["severity"], 0) >= order[params.min_severity]]
    page = sel[params.offset: params.offset + params.limit]
    return _j({"run_id": run_id, "total": len(sel), "offset": params.offset, "next_offset": params.offset + len(page) if params.offset + len(page) < len(sel) else None,
               "findings": [{k: f.get(k) for k in ("id", "source", "category", "severity", "title", "summary", "url")} for f in page]})


class CaseId(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str


@server.tool(name="osintdd_get_summary", description="Get the executive summary (Markdown), the backend that wrote it, and the report file paths for a case.", annotations={"readOnlyHint": True, "openWorldHint": False})
def osintdd_get_summary(params: CaseId) -> str:
    c = store().get_case(params.case_id)
    if not c:
        return _j({"error": "case not found"})
    sm = store().get_summary(params.case_id) or {}
    rp = c.get("report_path")
    from pathlib import Path
    paths = {ext: str(Path(rp).with_suffix("." + ext)) for ext in ("pdf", "html", "md") if rp and Path(rp).with_suffix("." + ext).exists()} if rp else {}
    return _j({"case_id": c["id"], "title": c["title"], "status": c["status"], "backend": sm.get("backend"), "summary_md": sm.get("summary_md"), "reports": paths})


class QueryLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    errors_only: bool = Field(False, description="Only failed queries")
    limit: int = Field(100, ge=1, le=1000)


@server.tool(name="osintdd_query_log", description="The full query log of a case: every source call with parameters, status, duration and result count (audit trail).", annotations={"readOnlyHint": True, "openWorldHint": False})
def osintdd_query_log(params: QueryLog) -> str:
    rows = store().get_query_log(params.case_id)
    if params.errors_only:
        rows = [r for r in rows if r["error"] or (r["status"] or "").startswith(("ERROR", "HTTP 4", "HTTP 5"))]
    return _j([{k: r.get(k) for k in ("ts", "source", "action", "request", "status", "duration_ms", "result_count", "error")} for r in rows[-params.limit:]])


class Refine(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    case_id: str
    tax_id: str = ""
    reg_number: str = ""
    location: str = ""
    birth_year: str = ""
    employer: str = ""
    run: bool = Field(True, description="Re-run after refinement")


@server.tool(name="osintdd_refine_case", description="Add disambiguation data (tax id, registration number, city, birth year, employer) to a case whose subject was ambiguous, then re-run.",
             annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True})
def osintdd_refine_case(params: Refine) -> str:
    c = store().get_case(params.case_id)
    if not c:
        return _j({"error": "case not found"})
    tg = c["target"]
    for k in ("tax_id", "reg_number", "location", "birth_year", "employer"):
        v = getattr(params, k)
        if v:
            setattr(tg, k, v)
    store().update_target(params.case_id, tg, "mcp refine")
    return _j(_run(params.case_id) if params.run else {"status": "refined"})


@server.tool(name="osintdd_split_case", description="When the subject cannot be disambiguated: create one sub-case per same-name candidate (companies by tax/registration number, people by LLM-clustered identities), run each, return their ids.",
             annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True})
def osintdd_split_case(params: CaseId) -> str:
    from .splitter import split_case
    ids = split_case(store(), params.case_id, None)
    return _j({"parent": params.case_id, "children": [{"case_id": k, "title": store().get_case(k)["title"], "report_path": store().get_case(k).get("report_path")} for k in ids]})


class GraphQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    include_statements: bool = Field(False, description="Include every statement with its source/url provenance (verbose)")


@server.tool(name="osintdd_graph", description="Entity graph of a case: entities (Company, Person, Domain, UserAccount, Sanction, DataBreach…), their properties with provenance, accepted same-as links, cross-case overlaps, and the pending same-as review queue.",
             annotations={"readOnlyHint": True, "openWorldHint": False})
def osintdd_graph(params: GraphQuery) -> str:
    from .graph import Graph
    g = Graph(store())
    ents = []
    for e in g.entities(params.case_id):
        props = e["properties"] if params.include_statements else {k: sorted({s["value"] for s in v})[:20] for k, v in e["properties"].items()}
        ents.append({"id": e["id"], "schema": e["schema"], "caption": e["caption"], "subject": bool(e["is_subject"]), "properties": props, "same_as": [l["b"] if l["a"] == e["id"] else l["a"] for l in e["links"]]})
    return _j({"entities": ents, "review_queue": [{k: q[k] for k in ("id", "score", "reason", "a", "a_schema", "a_caption", "b", "b_schema", "b_caption")} for q in g.review_queue(params.case_id)],
               "cross_case": g.cross_case(params.case_id)})


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    same_as_id: int = Field(..., description="id from osintdd_graph.review_queue")
    accept: bool
    decided_by: str = Field("mcp", description="Who decided (audit trail)")


@server.tool(name="osintdd_review_same_as", description="Accept or reject a same-as candidate in the entity graph (non-destructive; records the decision).",
             annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
def osintdd_review_same_as(params: Review) -> str:
    from .graph import Graph
    Graph(store()).decide(params.same_as_id, params.accept, params.decided_by)
    store().audit("same_as_decided", None, f"id={params.same_as_id} accept={params.accept} by={params.decided_by}")
    return _j({"same_as_id": params.same_as_id, "status": "accepted" if params.accept else "rejected"})


class Export(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    fmt: Literal["ftm", "csv"] = "ftm"


@server.tool(name="osintdd_export_graph", description="Export a case's entity graph as FollowTheMoney JSON Lines (.ftm) or a statements CSV with provenance.", annotations={"readOnlyHint": True, "openWorldHint": False})
def osintdd_export_graph(params: Export) -> str:
    from .graph import Graph
    g = Graph(store())
    return g.export_ftm(params.case_id) if params.fmt == "ftm" else g.export_csv(params.case_id)


@server.tool(name="osintdd_modules", description="List available modules with their group (core / person / grey) and the legal-basis keys.", annotations={"readOnlyHint": True, "openWorldHint": False})
def osintdd_modules() -> str:
    return _j({"modules": [{"key": m, "group": g} for m, g in MODULES_META], "default": DEFAULT_MODULES, "legal_bases": LEGAL_BASES})


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
