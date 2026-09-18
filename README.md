# osint-dd · Due Diligence — *crafted by sadrobot*

A **local, fully logged due-diligence / OSINT assistant** for vetting companies, vendors, domains and — only with a recorded GDPR legal basis — people. It runs on your own machine, uses **free public sources** by default, **logs every query and result** (SQLite + raw JSON), and turns each case into a **printable PDF report** in Hungarian or English. Grey-zone sources are available as explicit per-case opt-ins. An AI executive summary is written by Claude when an API key, the Claude Code CLI or a local Ollama model is available; otherwise a rule-based summary is produced.

Magyar leírás: [README.hu.md](README.hu.md)

## Install

**Standalone app (no Python needed):** download the build for your OS from [Releases](https://github.com/krisztianhari-wq/osint-dd/releases) (`osint-dd-macos-arm64.zip`, `osint-dd-macos-x86_64.zip`, `osint-dd-windows-x64.zip`, `osint-dd-linux-x86_64.tar.gz`), unpack and start `osint-dd`. Your browser opens on the local UI. On macOS the app is unsigned: right-click → Open on first launch.

**As a Python package:**
```
pipx install git+https://github.com/krisztianhari-wq/osint-dd     # or: pip install git+https://…
osint-dd                 # GUI + browser
osintdd --help           # command line
pipx inject osint-dd maigret holehe   # optional person-module tools
```

**From the repository (development):**
```
./run.sh            # GUI: http://127.0.0.1:8765   (HU/EN switch top right)
```

Data directory (cases, logs, reports, `.env`): `~/Library/Application Support/osint-dd` (macOS), `%APPDATA%\osint-dd` (Windows), `~/.local/share/osint-dd` (Linux); `./data` when run from the repo. Override with `OSINTDD_HOME`. The UI footer shows the active path.

## Command line

```
osintdd new --title "Vendor X" --purpose "NIS2 supplier risk" --legal-basis nem_szemelyes \
    --company "X Ltd." --tax-id 12345678 --domain x.hu --run
osintdd list | show <id> | log <id> | audit | run <id> --only sanctions,company | split <id>
```

Legal-basis keys: `nem_szemelyes` (no personal data), `jogos_erdek` (legitimate interest), `szerzodes` (contract), `jogi_kotelezettseg` (legal obligation), `hozzajarulas` (consent).

## What it checks (free, built in)

| Module | Source | Output |
|---|---|---|
| **Company** | EU VIES REST (HU VAT) | VAT validity, official name, registered address |
| | GLEIF LEI API | global legal entity, status, legal form |
| | DuckDuckGo `site:` search over Hungarian registry sites (nemzeticegtar, e-cegjegyzek, ceginformacio, opten, kozbeszerzes, birosag, nav) | snippet-level company data, insolvency status |
| **Sanctions** | EU consolidated (FSF), US OFAC SDN, UN Security Council, UK OFSI — official files, 24 h cache | fuzzy name matching (rapidfuzz ≥ 88 %) |
| **Web & press** | DuckDuckGo (general, negative keywords HU/EN, news), GDELT DOC API | hits, adverse media, 3-year news monitor |
| **Domain** | DNS (A/MX/NS/TXT), SPF/DMARC, crt.sh, RDAP / whois, Wayback CDX, Shodan InternetDB | subdomains, e-mail protection, age, open ports, known CVEs |
| **Person** *(legal basis required)* | username check on 20 platforms, Gravatar, **maigret** (top 500 sites), **holehe** (120 services, second pass for rate-limited ones) | accounts, e-mail registrations; the report states how many services could not be checked |
| **Phone** *(legal basis required)* | phonenumbers (offline) | validity, type, region, original carrier |
| **Manual links** | e-cégjegyzék, NAV debtor lists, court decisions, EKR/TED, Cégközlöny, OpenCorporates, OpenSanctions, OCCRP Aleph, LinkedIn… | pre-filled searches where no free API exists |

## AI summary — with or without an API key

The summary is written by the first available backend, in this order (`OSINTDD_LLM` forces one):

| Backend | Requirement | Cost / privacy |
|---|---|---|
| `claude-api` | `ANTHROPIC_API_KEY` in `.env` | API billing |
| `claude-cli` | Claude Code CLI installed (`curl -fsSL https://claude.ai/install.sh \| bash`, then `claude auth login` once) | uses your existing Claude subscription, no separate key |
| `ollama:<model>` | `brew install ollama && ollama pull llama3.1`, Ollama running | free, **fully offline** — personal data never leaves the machine |
| `rules` | always | rule-based summary |

The report footer shows which backend wrote the summary. Summaries are stored per run, so the UI always shows the full text.

## Identification: refine or split

- **Disambiguation fields** on a case: company registration number, seat/residence city, birth year, employer/position. They feed the queries, and web hits containing them are marked with `✓`.
- **Ambiguity detection** after a run: if a company has no tax ID / registration number and registry sites return several different companies, or a person has no disambiguators and many conflicting hits, a yellow **“Refinement needed”** card at the top of the report asks for the filter data → *Refine and re-run*.
- **If refinement is impossible**: *“Separate report per candidate”* (CLI: `split <id>`). Companies are split by the tax IDs / registration numbers found; people are grouped into distinct identities by Claude. Each candidate becomes a **sub-case** (max 6) with its own run and PDF, listed on the parent case.

## Grey-zone sources — per-case opt-in

Shown in a separate amber block when creating a case; off by default, run only with the person module and a legal basis; the selection is written to the audit log.

| Module | Source | Integration |
|---|---|---|
| `breach` | **LeakCheck public** (no key; source names + dates only) · **HIBP**, **DeHashed**, **IntelX** with keys | automatic; password fields are never stored |
| `aleph` | **OCCRP Aleph** investigative archive | automatic with a free API key, otherwise a manual link |
| `social` | LinkedIn / Facebook / Instagram / X / TikTok profiles **via search engines** (no scraping, no ToS breach) | automatic |
| `face` | PimEyes, FaceCheck.ID, Yandex image search | **manual link only** — biometric data (GDPR Art. 9), image uploaded by hand, case-by-case decision |

Deliberately **not** integrated: Telegram OSINT bots (illegally sourced databases, malware risk), GetContact/Truecaller (no official API, contact-list-derived data), LinkedIn scraping, the Hungarian land registry (TAKARNET).

Why these are grey: breach engines process stolen data (GDPR Art. 6/9); face search engines have been fined by German, Italian and Polish DPAs; contact-list phone lookups rely on data collected without consent. Get legal/DPO sign-off before enabling them.

## Paid sources — flagged, NOT built in

| Source | Why not included | Price (2026) |
|---|---|---|
| **Opten Cégtár / Partnerfigyelő** | subscription; ownership network, negative events, receivables | custom |
| **cegadatapi.hu, PK.API** | subscription Hungarian company-data APIs (owners, officers, financials) | plan-based |
| **OpenCorporates API** | web search is free, API is paid | from £2,250/yr |
| **OpenSanctions API / yente** | free for non-profits, **commercial use needs a licence**; with a licence set `OSINTDD_YENTE_URL` | €0.10/query or bulk licence |
| **Have I Been Pwned API** | breach lookup by e-mail | ~US$5/month |
| **Shodan (full) / Censys / VirusTotal API** | InternetDB is included key-free; full search is paid | freemium |
| **Maltego + Social Links / ShadowDragon** | commercial graph and social OSINT platforms | several k€/yr |

## Legal frame (short)

- **Companies, services, domains**: public data; legal basis “no personal data”.
- **Natural persons**: a GDPR Art. 6 basis is mandatory (legitimate interest with a balancing test, contract, legal obligation such as AML/NIS2, or consent). For job candidates the Hungarian Labour Code §10 restricts checks and the DPA (NAIH) is strict. The person module therefore runs only when explicitly enabled with a recorded legal basis, which appears in every report and in the audit log.
- **Retention**: everything lives in the data directory; delete after the period defined in your data-protection policy (Delete button / clear the directory).

## Configuration

Copy `.env.example` to `.env` in the data directory (or repo root when developing). All keys are optional; never commit `.env`.

## Layout

```
osintdd/core.py        cases, findings, query log, audit log (SQLite, WAL)
osintdd/http.py        logging HTTP client (every GET → query_log + raw JSON under cache/raw)
osintdd/sources/*.py   company · sanctions · web · domain · person · phone · grey · manual
osintdd/runner.py      module orchestration, ambiguity detection
osintdd/splitter.py    per-candidate sub-cases
osintdd/llm.py         Claude (API / Claude Code CLI) or Ollama or rule-based summary
osintdd/report.py      Markdown + HTML + PDF (reportlab, Unicode fonts)
osintdd/webapp.py      local GUI (127.0.0.1, stdlib), HU/EN
osintdd/app.py         standalone entry point (GUI + browser), used by PyInstaller
osintdd/cli.py         command line
```

A run takes 1–3 minutes because of per-source courtesy delays (DDG 1 s, GDELT 5 s). Licence: MIT.
