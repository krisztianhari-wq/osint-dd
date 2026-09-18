"""Claude-alapú narratív összefoglaló. Opcionális: ANTHROPIC_API_KEY (vagy `ant auth login` profil) nélkül szabályalapú összegzés készül."""
from __future__ import annotations

import json
import os
from typing import Any

MODEL = os.environ.get("OSINTDD_MODEL", "claude-opus-5")

SYSTEM = {
    "hu": ("Biztonsági átvilágítási (due diligence) elemző vagy. Csak a megadott, forrásokkal ellátott megállapításokból dolgozz, "
           "ne találj ki adatot. Írj tömör, magyar nyelvű vezetői összefoglalót Markdownban: 1) 3–6 mondatos összegzés, "
           "2) 'Kockázati értékelés' fejezet (alacsony/közepes/magas, indoklással, a szankciós fuzzy találatoknál hangsúlyozd a kézi ellenőrzést), "
           "3) 'Javasolt következő lépések' lista. Hivatkozz a forrásnevekre szögletes zárójelben, pl. [vies], [ddg_news]. "
           "Ne használj személyes adatot, ha a személyi modul ki van kapcsolva."),
    "en": ("You are a security due-diligence analyst. Work only from the sourced findings provided; never invent data. "
           "Write a concise executive summary in English, in Markdown: 1) a 3–6 sentence summary, 2) a 'Risk assessment' section "
           "(low/medium/high with reasoning; stress manual verification for fuzzy sanctions matches), 3) a 'Recommended next steps' list. "
           "Cite source names in square brackets, e.g. [vies], [ddg_news]. Do not use personal data if the person module is off."),
}


import shutil
import subprocess

CLAUDE_CLI_CANDIDATES = [os.path.expanduser("~/.local/bin/claude"), "/opt/homebrew/bin/claude", "/usr/local/bin/claude"]
OLLAMA_URL = os.environ.get("OSINTDD_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OSINTDD_OLLAMA_MODEL", "llama3.1")


def _claude_cli() -> str | None:
    p = shutil.which("claude")
    if p:
        return p
    for c in CLAUDE_CLI_CANDIDATES:
        if os.path.exists(c):
            return c
    return None


def _ollama_up() -> bool:
    try:
        import httpx
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return r.status_code == 200 and any(m.get("name", "").startswith(OLLAMA_MODEL.split(":")[0]) for m in r.json().get("models", []))
    except Exception:  # noqa: BLE001
        return False


def api_available() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return os.path.isdir(os.path.expanduser("~/.config/anthropic"))


def backends() -> list[str]:
    """Elérhető háttérrendszerek prioritási sorrendben. OSINTDD_LLM=api|cli|ollama|rules kényszeríti."""
    forced = os.environ.get("OSINTDD_LLM")
    if forced:
        return [forced]
    out = []
    if api_available():
        out.append("api")
    if _claude_cli():
        out.append("cli")
    if _ollama_up():
        out.append("ollama")
    return out + ["rules"]


def summarize(case: dict, findings: list[dict], lang: str = "hu") -> tuple[str, str]:
    """(markdown, backend) – backend: 'claude-api' | 'claude-cli' | 'ollama:<model>' | 'rules'."""
    errors = []
    for b in backends():
        try:
            if b == "api":
                return _claude(case, findings, lang), "claude-api"
            if b == "cli":
                return _claude_cli_run(case, findings, lang), "claude-cli"
            if b == "ollama":
                return _ollama(case, findings, lang), f"ollama:{OLLAMA_MODEL}"
            break
        except Exception as e:  # noqa: BLE001
            errors.append(f"{b}: {e}")
    md = _rules(case, findings, lang)
    if errors:
        md += "\n\n> LLM backend hiba / error: " + " · ".join(errors)
    return md, "rules"


def _user_prompt(case, findings, lang) -> str:
    return ("Készíts vezetői összefoglalót ebből az adathalmazból:\n\n" if lang == "hu" else "Produce the executive summary from this dataset:\n\n") + _payload(case, findings)


def _claude_cli_run(case: dict, findings: list[dict], lang: str) -> str:
    """Claude Code CLI nem interaktív módban (`claude -p`) – a meglévő Claude-előfizetést használja, API-kulcs nélkül."""
    exe = _claude_cli()
    if not exe:
        raise RuntimeError("claude CLI nincs telepítve")
    cmd = [exe, "-p", "--output-format", "text", "--append-system-prompt", SYSTEM[lang] + " Ne használj eszközöket; minden adat a bemenetben van. / Do not use tools; all data is inline."]
    model = os.environ.get("OSINTDD_CLI_MODEL")
    if model:
        cmd += ["--model", model]
    p = subprocess.run(cmd, input=_user_prompt(case, findings, lang), capture_output=True, text=True, timeout=600,
                       env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"})
    if p.returncode != 0 or not p.stdout.strip():
        raise RuntimeError((p.stderr or p.stdout or "üres válasz").strip()[-300:])
    return p.stdout.strip()


def _ollama(case: dict, findings: list[dict], lang: str) -> str:
    import httpx
    r = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=600, json={
        "model": OLLAMA_MODEL, "stream": False, "options": {"temperature": 0.2, "num_ctx": 16384},
        "messages": [{"role": "system", "content": SYSTEM[lang]}, {"role": "user", "content": _user_prompt(case, findings, lang)}]})
    r.raise_for_status()
    txt = r.json().get("message", {}).get("content", "").strip()
    if not txt:
        raise RuntimeError("üres Ollama-válasz")
    return txt


def _payload(case: dict, findings: list[dict]) -> str:
    slim = [{k: f.get(k) for k in ("source", "category", "severity", "title", "summary", "url")} for f in findings if f.get("category") != "manual"]
    tgt: Any = case["target"].to_dict() if hasattr(case["target"], "to_dict") else case["target"]
    if not case.get("person_checks"):
        tgt = {k: v for k, v in tgt.items() if k not in ("person", "email", "username", "phone")}
    return json.dumps({"case": {"title": case["title"], "purpose": case["purpose"], "legal_basis": case["legal_basis"],
                                "person_checks": case.get("person_checks")}, "target": tgt, "findings": slim}, ensure_ascii=False, indent=1)


def _claude(case: dict, findings: list[dict], lang: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    user = _user_prompt(case, findings, lang)
    kwargs: dict[str, Any] = dict(model=MODEL, max_tokens=8000, system=SYSTEM[lang],
                                  messages=[{"role": "user", "content": user}],
                                  thinking={"type": "adaptive"}, output_config={"effort": "medium"})
    try:
        with client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs) as s:
            msg = s.get_final_message()
    except TypeError:
        with client.messages.stream(**kwargs) as s:
            msg = s.get_final_message()
    if getattr(msg, "stop_reason", None) == "refusal":
        raise RuntimeError("model refused (stop_reason=refusal)")
    return "\n".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


def _rules(case: dict, findings: list[dict], lang: str) -> str:
    from .i18n import t
    real = [f for f in findings if f.get("category") != "manual"]
    hi = [f for f in real if f.get("severity") == "high"]
    me = [f for f in real if f.get("severity") == "medium"]
    lo = [f for f in real if f.get("severity") == "low"]
    lines = [f"> {t(lang, 'no_llm')}", "", t(lang, "counts", n=len(real), h=len(hi), m=len(me), l=len(lo)), ""]
    level = "high" if hi else "medium" if me else "low"
    lines.append(f"## {t(lang, 'risk')}: **{t(lang, 'sev')[level]}**")
    for f in hi + me:
        lines.append(f"- **[{f['source']}]** {f['title']} — {f.get('summary','')[:200]}")
    if not hi and not me:
        lines.append("- " + ("Nem került elő magas vagy közepes kockázatú jel az ingyenes forrásokban." if lang == "hu" else "No high- or medium-risk signals surfaced in the free sources."))
    lines.append("")
    lines.append("## " + ("Javasolt következő lépések" if lang == "hu" else "Recommended next steps"))
    steps_hu = ["Hiteles cégkivonat lekérése az e-cégjegyzékből (kézi link).", "NAV adóalany- és adóslista-ellenőrzés (kézi link).",
                "Szankciós fuzzy találatok kézi kizárása születési dátum / székhely alapján.", "Negatív sajtótalálatok forrásának és dátumának ellenőrzése."]
    steps_en = ["Pull the certified extract from the Hungarian company registry (manual link).", "Check NAV taxpayer and debtor lists (manual link).",
                "Manually clear fuzzy sanctions matches using DOB / registered address.", "Verify source and date of negative press hits."]
    lines += [f"{i}. {s}" for i, s in enumerate(steps_hu if lang == "hu" else steps_en, 1)]
    return "\n".join(lines)


def raw_completion(prompt: str, lang: str = "hu") -> str:
    """Egyszerű szöveges kérés az első elérhető LLM-háttéren (klaszterezéshez)."""
    sysmsg = "Válaszolj pontosan a kért formátumban, magyarázat nélkül." if lang == "hu" else "Answer exactly in the requested format, without explanation."
    for b in backends():
        try:
            if b == "api":
                import anthropic
                client = anthropic.Anthropic()
                with client.messages.stream(model=MODEL, max_tokens=4000, system=sysmsg, messages=[{"role": "user", "content": prompt}], thinking={"type": "adaptive"}) as st:
                    msg = st.get_final_message()
                return "\n".join(bl.text for bl in msg.content if getattr(bl, "type", "") == "text")
            if b == "cli":
                exe = _claude_cli()
                p = subprocess.run([exe, "-p", "--output-format", "text", "--append-system-prompt", sysmsg + " Do not use tools."], input=prompt, capture_output=True, text=True, timeout=600,
                                   env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"})
                if p.returncode == 0 and p.stdout.strip():
                    return p.stdout
                raise RuntimeError(p.stderr[-200:])
            if b == "ollama":
                import httpx
                r = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=600, json={"model": OLLAMA_MODEL, "stream": False, "messages": [{"role": "system", "content": sysmsg}, {"role": "user", "content": prompt}]})
                r.raise_for_status()
                return r.json()["message"]["content"]
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("no LLM backend")
