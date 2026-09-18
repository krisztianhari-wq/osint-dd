#!/usr/bin/env bash
# Önálló alkalmazás építése PyInstallerrel (macOS .app / Windows .exe / Linux mappa). CI-ben és helyben is fut.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python}
$PY -m pip install -q . pyinstaller
NAME="osint-dd"
ARGS=(--noconfirm --clean --name "$NAME" --windowed
      --collect-all ddgs --collect-all reportlab --collect-all phonenumbers --collect-all anthropic --collect-all dns --collect-all markdown --collect-all rapidfuzz
      --hidden-import osintdd.sources.company --hidden-import osintdd.sources.sanctions --hidden-import osintdd.sources.web --hidden-import osintdd.sources.domain
      --hidden-import osintdd.sources.person --hidden-import osintdd.sources.phone --hidden-import osintdd.sources.grey --hidden-import osintdd.sources.manual
      --hidden-import osintdd.splitter --hidden-import osintdd.report --hidden-import osintdd.llm)
case "$(uname -s)" in
  Darwin) ARGS+=(--osx-bundle-identifier hu.sadrobot.osintdd) ;;
esac
$PY -m PyInstaller "${ARGS[@]}" launcher.py
ls -la dist
