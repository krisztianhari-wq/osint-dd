"""Parancssori felület: osintdd new / run / list / show / log / gui."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .core import DEFAULT_MODULES, LEGAL_BASES, MODULES_META, Store, Target
from .runner import run_case


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="osintdd", description="osint-dd · helyi átvilágító asszisztens (sadrobot)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="új ügy létrehozása")
    n.add_argument("--title", required=True)
    n.add_argument("--purpose", required=True, help="pl. beszállító-átvilágítás NIS2 miatt")
    n.add_argument("--legal-basis", required=True, choices=list(LEGAL_BASES))
    n.add_argument("--company", default="")
    n.add_argument("--tax-id", default="")
    n.add_argument("--country", default="HU")
    n.add_argument("--domain", default="")
    n.add_argument("--person", default="")
    n.add_argument("--email", default="")
    n.add_argument("--username", default="")
    n.add_argument("--phone", default="")
    n.add_argument("--keyword", action="append", default=[])
    n.add_argument("--birth-year", default="")
    n.add_argument("--location", default="", help="lakhely / székhely város")
    n.add_argument("--employer", default="", help="munkahely / pozíció")
    n.add_argument("--reg-number", default="", help="cégjegyzékszám")
    n.add_argument("--person-checks", action="store_true", help="személyi modul engedélyezése (jogalap kell)")
    n.add_argument("--requester", default="")
    n.add_argument("--lang", default="hu", choices=["hu", "en"])
    n.add_argument("--modules", default=",".join(DEFAULT_MODULES), help="vesszővel: " + ",".join(m for m, _ in MODULES_META) + " (szürke zóna: breach,aleph,social,face)")
    n.add_argument("--run", action="store_true", help="azonnal futtassa is")

    r = sub.add_parser("run", help="ügy futtatása")
    r.add_argument("case_id")
    r.add_argument("--only", help="vesszővel: company,sanctions,domain,web,person,phone,manual")

    sub.add_parser("list", help="ügyek listája")
    s = sub.add_parser("show", help="ügy megállapításai")
    s.add_argument("case_id")
    s.add_argument("--json", action="store_true")
    lg = sub.add_parser("log", help="lekérdezési napló")
    lg.add_argument("case_id")
    sub.add_parser("audit", help="rendszernapló")
    sp = sub.add_parser("split", help="azonos nevű jelöltekre külön al-ügy + jelentés")
    sp.add_argument("case_id")
    gr = sub.add_parser("graph", help="entitásgráf: lista / felülvizsgálati sor / export")
    gr.add_argument("case_id")
    gr.add_argument("--export", choices=["ftm", "csv"], help="export stdout-ra")
    gr.add_argument("--review", action="store_true", help="egyezés-jelöltek listája")
    gr.add_argument("--accept", type=int, help="jelölt elfogadása (same_as id)")
    gr.add_argument("--reject", type=int, help="jelölt elutasítása (same_as id)")
    gr.add_argument("--rebuild", action="store_true", help="gráf újraépítése az utolsó futásból")
    sub.add_parser("mcp", help="MCP-szerver (stdio) – Claude Code / Claude Desktop számára")
    ep = sub.add_parser("export-pending", help="szerveren: Claude-összefoglaló nélküli futások exportja (JSON, stdout)")
    ep.add_argument("--limit", type=int, default=20)
    sub.add_parser("import-summary", help="szerveren: Macen készült összefoglalók beolvasása (JSON, stdin) + jelentés újraépítése")
    sm = sub.add_parser("summarize-export", help="Macen: export JSON → Claude → import JSON (stdin → stdout)")
    sm.add_argument("--lang", default=None)
    g = sub.add_parser("gui", help="webes felület indítása")
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--host", default=None)

    a = ap.parse_args(argv)
    store = Store()

    if a.cmd == "new":
        tg = Target(company=a.company, tax_id=a.tax_id, country=a.country, domain=a.domain, person=a.person, email=a.email,
                    username=a.username, phone=a.phone, extra_keywords=a.keyword,
                    birth_year=a.birth_year, location=a.location, employer=a.employer, reg_number=a.reg_number)
        cid = store.create_case(a.title, a.purpose, a.legal_basis, tg, a.person_checks, a.requester, a.lang, [m.strip() for m in a.modules.split(",") if m.strip()])
        print(cid)
        if a.run:
            run_case(store, cid, print)
        return 0
    if a.cmd == "run":
        run_case(store, a.case_id, print, a.only.split(",") if a.only else None)
        return 0
    if a.cmd == "list":
        for c in store.list_cases():
            print(f"{c['id']}  {c['created_at'][:16]}  {c['status']:8}  {c['title']}  [{c['target'].get('company') or c['target'].get('domain')}]  {c['report_path'] or ''}")
        return 0
    if a.cmd == "show":
        fs = store.get_findings(a.case_id)
        if a.json:
            print(json.dumps(fs, ensure_ascii=False, indent=1))
        else:
            for f in fs:
                print(f"[{f['severity']:6}] {f['category']:9} {f['source']:16} {f['title']}\n         {f['summary'][:160]} {f['url']}")
        return 0
    if a.cmd == "log":
        for q in store.get_query_log(a.case_id):
            print(f"{q['ts'][11:19]} {q['source']:18} {q['action']:9} {q['status']:9} {q['duration_ms']:>6}ms  n={q['result_count']}  {(q['request'] or '')[:100]} {q['error'] or ''}")
        return 0
    if a.cmd == "split":
        from .splitter import split_case
        print(split_case(store, a.case_id, print))
        return 0
    if a.cmd == "audit":
        for e in store.get_audit():
            print(f"{e['ts']} {e['actor']:10} {e['event']:18} {e['case_id'] or '-':12} {e['detail'] or ''}")
        return 0
    if a.cmd == "graph":
        from .graph import Graph, build_graph
        gph = Graph(store)
        if a.rebuild:
            fs = store.get_findings(a.case_id)
            print(build_graph(store, store.get_case(a.case_id), fs[-1]["run_id"] if fs else ""))
        if a.accept:
            gph.decide(a.accept, True, "cli")
        if a.reject:
            gph.decide(a.reject, False, "cli")
        if a.export == "ftm":
            print(gph.export_ftm(a.case_id), end="")
        elif a.export == "csv":
            print(gph.export_csv(a.case_id), end="")
        elif a.review:
            for q in gph.review_queue(a.case_id):
                print(f"[{q['id']:4}] {q['score']:5.1f}  {q['a_schema']}:{q['a_caption']}  ≟  {q['b_schema']}:{q['b_caption']}   ({q['reason']})")
        else:
            for e in gph.entities(a.case_id):
                print(f"{'★' if e['is_subject'] else ' '} {e['schema']:12} {e['caption'][:60]:60} {len(e['properties'])} tulajdonság, {sum(len(v) for v in e['properties'].values())} állítás")
            for x in gph.cross_case(a.case_id):
                print(f"  ↔ más ügyben is: {x['schema']} {x['caption']} → {x['other_title']} ({x['other_case']})")
        return 0
    if a.cmd == "export-pending":
        rows = store.conn.execute(
            "SELECT r.run_id, r.case_id FROM runs r JOIN cases c ON c.id=r.case_id WHERE r.backend NOT LIKE 'claude%' "
            "AND r.run_id = (SELECT run_id FROM runs r2 WHERE r2.case_id=r.case_id ORDER BY created_at DESC LIMIT 1) ORDER BY r.created_at DESC LIMIT ?", (a.limit,)).fetchall()
        out = []
        for r in rows:
            c = store.get_case(r["case_id"])
            fs = store.get_findings(r["case_id"], r["run_id"])
            out.append({"case_id": r["case_id"], "run_id": r["run_id"], "lang": c.get("lang", "hu"),
                        "case": {"title": c["title"], "purpose": c["purpose"], "legal_basis": c["legal_basis"], "person_checks": c.get("person_checks"), "target": c["target"].to_dict()},
                        "findings": [{k: f.get(k) for k in ("source", "category", "severity", "title", "summary", "url")} for f in fs if f.get("category") != "manual"]})
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if a.cmd == "summarize-export":
        from .core import Target
        from .llm import _claude_cli_run
        items = json.load(sys.stdin)
        res = []
        for it in items:
            case = dict(it["case"]); case["target"] = Target.from_dict(case["target"]); case["id"] = it["case_id"]
            if not case["target"].has_person_data() and not case.get("person_checks"):
                pass
            try:
                md = _claude_cli_run(case, it["findings"], a.lang or it.get("lang", "hu"))
                res.append({"case_id": it["case_id"], "run_id": it["run_id"], "summary_md": md, "backend": "claude-cli@mac"})
                print(f"  ✓ {it['case']['title']}", file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {it['case']['title']}: {e}", file=sys.stderr)
        print(json.dumps(res, ensure_ascii=False))
        return 0
    if a.cmd == "import-summary":
        from .report import build_report
        items = json.load(sys.stdin)
        n = 0
        for it in items:
            if not store.get_case(it["case_id"]):
                continue
            store.save_summary(it["case_id"], it["run_id"], it["summary_md"], it.get("backend", "claude-cli@mac"))
            os.environ["OSINTDD_LLM"] = "stored"
            try:
                p = build_report(store, it["case_id"], it["run_id"])
                store.set_status(it["case_id"], "done", report_path=str(p))
            except Exception as e:  # noqa: BLE001
                store.audit("import_summary_report_failed", it["case_id"], str(e)[:200])
            n += 1
        print(f"{n} összefoglaló beolvasva")
        return 0
    if a.cmd == "mcp":
        from .mcp_server import main as mcp_main
        mcp_main()
        return 0
    if a.cmd == "gui":
        from .webapp import serve
        serve(a.port, a.host)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
