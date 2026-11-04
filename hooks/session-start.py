# -*- coding: utf-8 -*-
"""
SessionStart hook: silent self-heal for the 打更人 (ZCode Nightwatch) plugin.

Installing this plugin means the guardian is on duty - zero-touch. On every
session start (startup|resume) verify, silently, without any window flash:

  1. scheduled task ZCodeNightwatch exists -> if not, run the installer
     (auto-detects ZCode.exe; preserves an existing nightwatch.disabled opt-out)
  2. busy-retry patch marker present in zcode.cjs -> if not, re-apply
  3. extra_patchers markers -> if not, re-apply

Never restarts ZCode; patched code loads on the app's next start. Healthy
state = no output, exit 0, a few hundred milliseconds. Every action is logged
to nightwatch/nightwatch.log with a [hook] tag.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
HERE = Path(__file__).resolve().parent     # <plugin>/hooks
ROOT = HERE.parent                          # plugin root
NW = ROOT / "nightwatch"
BUSY_MARKER = "Math.min(e.state.streamRecoveryRetryCount"
TASK_NAME = "ZCodeNightwatch"


def log(msg: str) -> None:
    try:
        with (NW / "nightwatch.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [hook] {msg}\n")
    except OSError:
        pass


def run(cmd: list[str], timeout: int) -> int:
    # bytes-only capture: console tools emit GBK on zh-CN Windows, and text
    # mode may decode as utf-8 (system UTF-8 option) which crashes the reader
    # thread; we only need the exit code.
    try:
        r = subprocess.run(cmd, capture_output=True,
                           creationflags=NO_WINDOW, timeout=timeout)
        return r.returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f"error running {cmd[0]}: {e}")
        return -1


def main() -> int:
    if os.name != "nt":
        return 0   # Windows-only guardian; stay silent elsewhere
    if (NW / "nightwatch.disabled").exists():
        return 0   # user opted out via uninstall-nightwatch.ps1

    # 1) guardian task present?
    if run(["schtasks", "/Query", "/TN", TASK_NAME], 30) != 0:
        rc = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                  "-File", str(NW / "install-nightwatch.ps1")], 120)
        log(f"task missing -> installer rc={rc}")

    cfg_path = NW / "nightwatch.json"
    if not cfg_path.exists():
        return 0
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return 0
    exe = cfg.get("zcode_exe")
    if not exe:
        return 0
    cjs = Path(str(exe)).parent / "resources" / "glm" / "zcode.cjs"
    if not cjs.exists():
        return 0
    try:
        text = cjs.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0   # file churn (mid-upgrade) - retry next session

    # 2) busy-retry marker
    if (cfg.get("busy_retry_window") or "all_day") != "off" and BUSY_MARKER not in text:
        rc = run([sys.executable, str(NW / "busy_retry_patch.py"),
                  "--zcode-exe", str(exe)], 300)
        log(f"busy-retry patch reapplied rc={rc} (marker was absent -> ZCode upgrade?)")

    # 3) extra patchers
    for extra in cfg.get("extra_patchers") or []:
        try:
            marker, script = extra["marker"], Path(extra["script"])
        except (KeyError, TypeError):
            continue
        if marker in text or not script.exists():
            continue
        rc = run([sys.executable, str(script)], 300)
        log(f"{extra.get('name', script.stem)} patch reapplied rc={rc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
