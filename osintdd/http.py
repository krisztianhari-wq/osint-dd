"""Naplózott HTTP-kliens a forrásmodulokhoz."""
from __future__ import annotations

import time
from typing import Any

import httpx

from .core import QueryLogger

UA = "osint-dd/0.1 (+local due-diligence tool; contact: security team)"


class Http:
    def __init__(self, log: QueryLogger, timeout: float = 20.0):
        self.log = log
        self.client = httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA})

    def get(self, source: str, url: str, params: dict | None = None, headers: dict | None = None,
            expect_json: bool = False, save_raw: bool = True) -> tuple[Any, httpx.Response | None]:
        started = time.time()
        req = {"url": url, "params": params or {}}
        try:
            r = self.client.get(url, params=params, headers=headers)
            body: Any
            if expect_json:
                try:
                    body = r.json()
                except Exception:  # noqa: BLE001
                    body = None
            else:
                body = r.text
            count = None
            if isinstance(body, list):
                count = len(body)
            elif isinstance(body, dict):
                count = len(body.get("data", body.get("results", body.get("articles", [])))) if isinstance(
                    body.get("data", body.get("results", body.get("articles", []))), list) else None
            self.log.log(source, "GET", req, f"HTTP {r.status_code}", started, count,
                         None if r.is_success else f"HTTP {r.status_code}",
                         raw=(body if save_raw and expect_json else (body[:20000] if save_raw and isinstance(body, str) else None)))
            return body, r
        except Exception as e:  # noqa: BLE001
            self.log.log(source, "GET", req, "ERROR", started, 0, str(e))
            return None, None

    def close(self) -> None:
        self.client.close()
