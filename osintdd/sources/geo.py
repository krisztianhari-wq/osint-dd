"""GDELT GEO 2.0 – földrajzilag kötött hírlefedettség (hol írnak a célról). Kulcs nélkül, 1 kérés / 5 s."""
from __future__ import annotations

import time

from ..core import Finding, Target
from ..http import Http

API = "https://api.gdeltproject.org/api/v2/geo/geo"


def run(t: Target, http: Http, log, case) -> list[Finding]:
    out: list[Finding] = []
    subjects = [s for s in [t.company] if s]
    if case.get("person_checks") and t.person:
        subjects.append(t.person)
    for s in subjects[:2]:
        time.sleep(5.2)
        params = {"query": f'"{s}"', "mode": "PointData", "format": "GeoJSON", "timespan": "1y", "maxpoints": 40}
        body, r = http.get("gdelt_geo", API, params=params, expect_json=True)
        if r is not None and r.status_code == 429:
            time.sleep(8)
            body, r = http.get("gdelt_geo", API, params=params, expect_json=True)
        feats = (body or {}).get("features", []) if isinstance(body, dict) else []
        if not feats:
            out.append(Finding("gdelt_geo", "geo", f"GDELT GEO: nincs földrajzi hírtalálat – {s}", "elmúlt 1 év", severity="info", data={"query": s}))
            continue
        pts = []
        for f in feats:
            p = f.get("properties", {})
            g = f.get("geometry", {}).get("coordinates", [None, None])
            pts.append({"name": p.get("name"), "count": p.get("count", 0), "lon": g[0], "lat": g[1]})
        pts.sort(key=lambda x: -(x["count"] or 0))
        top = pts[:12]
        out.append(Finding("gdelt_geo", "geo", f"Hírek földrajza ({s}): {len(pts)} helyszín, elmúlt 1 év",
                           " · ".join(f"{x['name']} ({x['count']})" for x in top),
                           url=f"https://api.gdeltproject.org/api/v2/geo/geo?query=%22{s}%22&mode=PointData&format=html&timespan=1y", severity="info",
                           data={"query": s, "points": pts[:40]}))
    return out
