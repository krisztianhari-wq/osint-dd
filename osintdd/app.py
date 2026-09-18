"""Önállóan futtatható belépési pont (PyInstaller / `osint-dd` parancs): elindítja a GUI-t és megnyitja a böngészőt."""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import webbrowser


def _free_port(start: int) -> int:
    for p in range(start, start + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="osint-dd", description="osint-dd · Átvilágító – helyi due diligence asszisztens (sadrobot)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--version", action="store_true")
    a = ap.parse_args(argv)
    if a.version:
        from . import __version__
        print(f"osint-dd {__version__}")
        return 0
    # .env a felhasználói adatkönyvtárból (kulcsok, LLM-beállítás)
    from .core import BASE_DIR
    envf = BASE_DIR / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))
    port = _free_port(a.port)
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    from .webapp import serve
    serve(port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
