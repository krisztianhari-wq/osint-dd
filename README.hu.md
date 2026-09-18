# osint-dd · Átvilágító — *crafted by sadrobot*

Helyi, a saját gépeden futó **due diligence / OSINT asszisztens** cégek, szolgáltatók, domainek és – rögzített GDPR-jogalappal – személyek ellenőrzésére. Csak **ingyenes, nyilvános forrásokat** használ, **minden lekérést és eredményt naplóz** (SQLite + nyers JSON), és minden ügyből **nyomtatható PDF** jelentést készít magyar vagy angol nyelven.

## Telepítés

**Kész alkalmazás (nem kell Python):** a [Releases](https://github.com/krisztianhari-wq/osint-dd/releases) oldalról töltsd le a rendszerednek megfelelőt (`osint-dd-macos-arm64.zip`, `osint-dd-windows-x64.zip`, `osint-dd-linux-x86_64.tar.gz`), csomagold ki, indítsd az `osint-dd` alkalmazást. Megnyílik a böngésző a helyi felülettel. macOS-en első indításnál: jobb klikk → Megnyitás (nem aláírt app).

**Python-csomagként:**
```
pipx install git+https://github.com/krisztianhari-wq/osint-dd      # vagy: pip install git+https://…
osint-dd                 # GUI + böngésző
osintdd --help           # parancssor
pipx inject osint-dd maigret holehe   # opcionális személyi eszközök
```

**Fejlesztői futtatás a repóból:**
```
./run.sh            # GUI: http://127.0.0.1:8765   (HU/EN váltó jobb fent)
```

Adatkönyvtár (ügyek, naplók, jelentések, `.env`): telepítve `~/Library/Application Support/osint-dd` (macOS), `%APPDATA%\osint-dd` (Windows), `~/.local/share/osint-dd` (Linux); a repóból futtatva `./data`. Az `OSINTDD_HOME` változó átállítja. A felület lábléce mutatja az aktuális utat.

CLI:
```
.venv/bin/python -m osintdd new --title "Beszállító X" --purpose "NIS2 beszállítói kockázat" \
    --legal-basis nem_szemelyes --company "X Kft." --tax-id 12345678 --domain x.hu --run
.venv/bin/python -m osintdd list | show <id> | log <id> | audit | run <id> --only sanctions,company
```

## AI-összefoglaló – API-kulcs nélkül is

Az összefoglalót az első elérhető háttér írja, ebben a sorrendben (`OSINTDD_LLM` kényszeríti):

| Háttér | Feltétel | Költség / adatvédelem |
|---|---|---|
| `claude-api` | `ANTHROPIC_API_KEY` a `.env`-ben | API-számlázás |
| `claude-cli` | Claude Code CLI telepítve (`curl -fsSL https://claude.ai/install.sh \| bash`, majd `claude` egyszer bejelentkezve) | a meglévő Claude-előfizetést használja, nincs külön kulcs |
| `ollama:<modell>` | `brew install ollama && ollama pull llama3.1` és fut az Ollama | ingyenes, **teljesen offline** – személyes adat nem hagyja el a gépet |
| `rules` | mindig | szabályalapú összegzés |

A jelentés lábléce mutatja, melyik háttér írta az összefoglalót. Az összefoglaló futásonként a `runs` táblába is elmentődik, így a GUI jelentés-oldalán mindig a teljes szöveg látszik.

## Mit ellenőriz (ingyenes, beépített)

| Modul | Forrás | Mit ad |
|---|---|---|
| **Cégadatok** | EU VIES REST (HU adószám) | ÁFA-alany érvényesség, hivatalos név, székhely |
| | GLEIF LEI API | globális jogi entitás, státusz, jogi forma |
| | DuckDuckGo `site:` keresés (nemzeticegtar, e-cegjegyzek, ceginformacio, opten, kozbeszerzes, birosag, nav) | snippet szintű cégadat, eljárás alatt áll-e |
| **Szankciós listák** | EU konszolidált (FSF), US OFAC SDN, ENSZ BT, UK OFSI – hivatalos fájlok, 24 h cache | fuzzy névillesztés (rapidfuzz ≥ 88 %) |
| **Web és sajtó** | DuckDuckGo (általános, negatív kulcsszavak HU/EN, hírek), GDELT DOC API | találatok, negatív hírek, 3 éves hírmonitor |
| **Domain** | DNS (A/MX/NS/TXT), SPF/DMARC, crt.sh, RDAP / whois, Wayback CDX, Shodan InternetDB | aldomainek, e-mail védelem, kor, nyitott portok, ismert CVE-k |
| **Személy** *(csak jogalappal)* | 20 platform felhasználónév-ellenőrzés, Gravatar, **maigret** (top 500 oldal), **holehe** (120 szolgáltatás, rate-limitelt oldalakra 25 s után második kör) | fiókok, e-mail regisztrációk; a jelentés kimondja, hány szolgáltatás nem volt ellenőrizhető |
| **Telefon** *(csak jogalappal)* | phonenumbers (offline) | érvényesség, típus, régió, eredeti szolgáltató |
| **Kézi linkek** | e-cégjegyzék, NAV adóslisták, bírósági határozatok, EKR/TED, Cégközlöny, OpenCorporates, OpenSanctions, OCCRP Aleph, LinkedIn… | előre kitöltött keresések ott, ahol nincs ingyenes API |

## Azonosítás: pontosítás vagy szétválasztás

- **Pontosító mezők** az ügynél: cégjegyzékszám, székhely/lakhely város, születési év, munkahely/pozíció. Bekerülnek a lekérdezésekbe, és a webes találatoknál `✓` jelzi, ha a találat tartalmazza őket.
- **Kétértelműség-felismerés** futás után: ha a cégnek nincs adószáma/cégjegyzékszáma és a cégadat-oldalak több különböző céget hoznak, vagy a személyhez nincs pontosító adat és sok/ellentmondó találat van, a jelentés tetején sárga **„Pontosítás szükséges"** kártya kérdez rá a szűrő adatokra → *Pontosítás és újrafuttatás*.
- **Ha nem lehet pontosítani**: *„Külön jelentés minden jelöltre"* gomb (CLI: `split <id>`). Cégnél a talált adószámok/cégjegyzékszámok, személynél Claude által csoportosított identitások szerint **al-ügyek** jönnek létre (max. 6), mindegyik saját futással és saját PDF-fel; a szülő ügy oldalán listázva.

## Fizetős források – jelezve, NINCS beépítve

| Forrás | Miért nincs benne | Ár (2026) |
|---|---|---|
| **Opten Cégtár / Partnerfigyelő** | előfizetés; kapcsolati háló, negatív események, követelés | egyedi |
| **cegadatapi.hu, PK.API** | előfizetéses magyar cégadat API (tulajdonos, vezető, mérleg) | csomagár |
| **OpenCorporates API** | webes keresés ingyenes, API fizetős | £2 250/év-től |
| **OpenSanctions API / yente** | non-profitnak ingyenes, **kereskedelmi használat licencköteles**; ha van licenc: `OSINTDD_YENTE_URL` | 0,10 €/lekérés vagy bulk licenc |
| **Have I Been Pwned API** | adatszivárgás e-mail alapján | ~5 USD/hó |
| **Shodan (teljes) / Censys / VirusTotal API** | InternetDB kulcs nélkül benne; a teljes keresés fizetős | freemium |
| **Maltego + Social Links / ShadowDragon** | kereskedelmi gráf- és social OSINT | évi több millió Ft |

## Szürke zónás források – ügyenként engedélyezhető (jogi egyeztetés: 2026-09-18)

Az ügy létrehozásakor külön, sárga keretes blokkban pipálhatók; alapból kikapcsolva, csak személyi modullal és jogalappal futnak, a választás a rendszernaplóba kerül.

| Modul | Forrás | Beépítés |
|---|---|---|
| `breach` | **LeakCheck public** (kulcs nélkül, csak forrásnév + dátum) · **HIBP**, **DeHashed**, **IntelX** kulccsal | automatikus; jelszómezőt nem tárol |
| `aleph` | **OCCRP Aleph** oknyomozó adattár | ingyenes API-kulccsal automatikus, különben kézi link |
| `social` | LinkedIn / Facebook / Instagram / X / TikTok profilok **keresőmotoron át** (nem scraping, nem ToS-sértő) | automatikus |
| `face` | PimEyes, FaceCheck.ID, Yandex képkeresés | **csak kézi link** – biometrikus adat (GDPR 9. cikk), kép feltöltése kézzel, egyedi döntéssel |

Tudatosan **nem** került be: Telegram OSINT-botok (illegális eredetű adatbázisok, malware-kockázat), GetContact/Truecaller (nincs hivatalos API, kontaktlista-alapú adat), LinkedIn-scraping, TAKARNET.

Áttekintés a szürke zóna kockázatairól:

| Forrás | Mi ez | Kockázat |
|---|---|---|
| **DeHashed, IntelX, LeakCheck, Snusbase, BreachDirectory** | kiszivárgott adatbázisok keresője (jelszó-hash, cím, telefon) | lopott adat feldolgozása; GDPR 6. és 9. cikk; LeakCheck UK-GDPR alatt, a többi offshore |
| **PimEyes, FaceCheck.ID, Search4Faces** | arcfelismerő keresők | biometrikus = különleges adat (GDPR 9. cikk); német/olasz/lengyel hatóságok eljárást indítottak, bírságoltak |
| **GetContact, Truecaller, NumLookup** | telefonszám → név a felhasználók kontaktlistáiból | a forrásadat hozzájárulás nélkül gyűjtött; NAIH-szempontból problémás |
| **Telegram OSINT-botok** („Глаз Бога” típus) | kiszivárgott orosz/ukrán/EU adatbázisok bot-felületen | illegális forrás, malware- és OPSEC-kockázat, hamis adat |
| **OCCRP Aleph** *(beépítve, `aleph` modul)* | oknyomozó adattár, kiszivárgott dokumentumok is | nyilvános, újságírói célra készült; üzleti döntésre óvatosan |
| **LinkedIn / Facebook scraping** | automatizált profilgyűjtés | ToS-sértés, fiókletiltás; kézi keresés linkje benne |
| **TAKARNET tulajdoni lap** | ingatlan-nyilvántartás | csak regisztrált, jogosult felhasználónak, díjköteles, célhoz kötött |
| **KHR (BAR-lista), NAV végrehajtási lista** | adós-nyilvántartások | KHR nem nyilvános; NAV listák nyilvánosak → kézi link benne |

## Jogi keret (röviden)

- **Cég, szolgáltatás, domain**: nyilvános adat, jogalap „Nem személyes adat”.
- **Természetes személy**: GDPR 6. cikk szerinti jogalap kötelező (jogos érdek + érdekmérlegelési teszt, szerződés, jogi kötelezettség pl. Pmt./NIS2, vagy hozzájárulás). Munkavállaló-jelölteknél az Mt. 10. § korlátoz; a NAIH gyakorlata szigorú. A személyi modul ezért csak kifejezetten bekapcsolva és jogalap rögzítésével fut; a jogalap minden jelentésbe és a rendszernaplóba bekerül.
- **Megőrzés**: `data/` alatt minden ügy, napló, nyers válasz és jelentés; az adatkezelési szabályzat szerinti idő után törlendő (`delete` gomb / `data/` ürítése).

## Felépítés

```
osintdd/core.py        ügyek, megállapítások, lekérdezési napló, rendszernapló (SQLite, WAL)
osintdd/http.py        naplózott HTTP-kliens (minden GET → query_log + nyers JSON a data/cache/raw alá)
osintdd/sources/*.py   company · sanctions · web · domain · person · phone · manual
osintdd/llm.py         Claude (claude-opus-5, adaptív gondolkodás, server-side fallback) vagy szabályalapú összefoglaló
osintdd/report.py      Markdown + HTML + PDF (reportlab, Montserrat/Arial Unicode – ékezethelyes)
osintdd/webapp.py      helyi GUI (127.0.0.1, stdlib), HU/EN
osintdd/cli.py         parancssor
```

Adatkönyvtár: `data/` (átállítható `OSINTDD_HOME`-mal). Egy futás ~1–2 perc a forrás-udvariassági várakozások miatt (DDG 1 s, GDELT 5 s).
