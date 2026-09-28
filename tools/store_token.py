"""Hosszú élettartamú Claude-token mentése a macOS Keychainbe (osint-dd-claude-token).
Beillesztés sortörésekkel is jó: minden whitespace kikerül. Befejezés: Enter, majd Ctrl-D."""
import subprocess
import sys

print("Illeszd be a tokent (tördelve is jó), utána Enter, majd Ctrl-D:")
tok = "".join(sys.stdin.read().split())
if not tok.startswith("sk-ant-oat01-") or len(tok) < 60:
    print(f"HIBA: nem sk-ant-oat01- kezdetű vagy túl rövid (hossz: {len(tok)}). Nem mentettem.")
    sys.exit(1)
r = subprocess.run(["security", "add-generic-password", "-a", "osintdd", "-s", "osint-dd-claude-token", "-w", tok, "-U"])
print(f"Keychainbe mentve, hossz: {len(tok)}" if r.returncode == 0 else f"security hiba: {r.returncode}")
