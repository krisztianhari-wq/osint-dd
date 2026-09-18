"""Parancssori felület: osintdd new / run / list / show / log / gui."""
from __future__ import annotations

import argparse
import json
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
    g = sub.add_parser("gui", help="webes felület indítása")
    g.add_argument("--port", type=int, default=8765)

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
    if a.cmd == "gui":
        from .webapp import serve
        serve(a.port)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
