# osint-dd (Átvilágító) – fejlesztői jegyzet

Helyi, naplózott due-diligence / OSINT asszisztens cégekre, domainekre és – GDPR-jogalappal – személyekre; HU/EN, PDF-jelentés, „crafted by sadrobot”. Felhasználói leírás: README.md (EN) és README.hu.md.

## Indítás és teszt
- `./run.sh` → GUI a http://127.0.0.1:8765 címen (venv `/opt/homebrew/bin/python3.14`-gyel, ha nincs; betölti a `.env`-et). launch.json: `osint-dd-gui` (port 8765, `~/Claude_code/.claude/launch.json`).
- CLI: `.venv/bin/python -m osintdd new|run|list|show|log|audit|split|graph|mcp|gui` (+ szerveres `export-pending`, `import-summary`, `summarize-export`). pip-csomagként: `osintdd` (CLI) és `osint-dd` (GUI + böngésző).
- Adat: repóból futtatva `./data/`, telepített appban `~/Library/Application Support/osint-dd` (Win: `%APPDATA%`, Linux: XDG); `OSINTDD_HOME` felülírja (`osintdd/core.py`).
- Automatikus teszt nincs. Kézi füstteszt: cégügy `nem_szemelyes` jogalappal egy ismert adószámra/domainre, majd a jelentés és a gráf ellenőrzése.

## Felépítés
- `osintdd/sources/` – company (VIES, GLEIF), domain (DNS, crt.sh, RDAP, whois, Wayback, Shodan InternetDB), sanctions (EU/OFAC/UN/UK listák, rapidfuzz), web (DDG / GDELT), geo, github, phone, person (felhasználónév-ellenőrzés, Gravatar, opcionális maigret/holehe), grey (szürke zóna), paste, manual.
- `osintdd/runner.py`, `core.py` (SQLite / SQLCipher, ha van kulcsfájl), `splitter.py` (azonos nevű jelöltek → al-ügyek `parent_id`-val), `graph.py` (saját FtM-kompatibilis entitásgráf, provenance, same-as felülvizsgálat, `.ftm` export).
- `osintdd/llm.py` – összefoglaló-háttérlánc: `ANTHROPIC_API_KEY` → Claude Code CLI (`claude -p`, hosszú életű tokennel env-ből vagy Keychainből) → Ollama → szabályalapú. `tools/store_token.py` menti a tokent Keychainbe.
- `osintdd/mcp_server.py` – `osintdd mcp`, stdio MCP-szerver 12 eszközzel.
- `osintdd/webapp.py` + `static/` – stdlib GUI; `report.py` – PDF (reportlab).
- Konfiguráció: `.env.example` (`OSINTDD_*` változók, szürke zónás kulcsok).

## Telepítés / kiadás
- Verzió: `pyproject.toml` és `osintdd/__init__.py` (jelenleg 0.3.0) – mindkettőt együtt emeld. Kiadás: /release skill; `v*` tag → `.github/workflows/build.yml` PyInstaller-app (macOS arm64 + x86_64, Windows, Linux) a release-hez.
- Szerveres mód: `Dockerfile` (python:3.12-slim, port 8780, `requirements-server.txt` SQLCipherrel és maigret/holehe-vel), `OSINTDD_AUTH=proxy` (megosztott titok fejlécben + e-mail allowlist, fail-closed), szerveren `OSINTDD_LLM=rules`; a Claude-összefoglalót a Mac írja meg az `export-pending` → `summarize-export` → `import-summary` láncon. Telepítés: lásd /deploy-sadrobot skill és sadrobot-infra/SADROBOT-INFRA.md.

## Döntések
1. Ingyenes források beépítve; a fizetősek csak jelölve, nincsenek integrálva. Minden lekérdezés naplózva.
2. Személyes ellenőrzés csak `person_checks=true` + valódi GDPR-jogalap mellett (jogos_erdek / szerzodes / jogi_kotelezettseg / hozzajarulas). Cégre/domainre `nem_szemelyes`.
3. Szürke zónás források (LeakCheck, HIBP / DeHashed / IntelX kulccsal, OCCRP Aleph, social keresőn át, arckeresés kézi linkkel) ügyenként opt-in modulok, jogi jóváhagyás után (2026-09-18).
4. Tudatosan kizárva: Telegram-botok, GetContact, LinkedIn-scraping.
5. Licenc: saját sadrobot proprietary (EN/HU), nem MIT (0.3.0 óta).
6. Arculat: sadrobot tokenek (Figtree, ink #0b1f4d, teal #0a8aa4), világos/sötét mód, a GUI-ban és a jelentésekben is.

## Buktatók
- A psbdmp.ws 2026-ban megszűnt → a paste modul DDG-n keres 12 paste-oldalon.
- A `followthemoney` lib pyicu-t igényel → saját gráf a `graph.py`-ban.
- mcp 2.x API: `from mcp.server.mcpserver import MCPServer`.
- A Claude CLI OAuth-sessionje lejárhat → `claude auth login` újra; addig az LLM szabályalapúra esik vissza.
- A build-bélyeg `osintdd/BUILD`-ben van (a repo gyökerében ütközne a `build/`-del kis-nagybetű-érzéketlen fájlrendszeren).
