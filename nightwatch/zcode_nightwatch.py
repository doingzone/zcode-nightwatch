# -*- coding: utf-8 -*-
"""
ZCode Nightwatch (打更人) — night-shift guardian for the ZCode desktop app.

Runs once per invocation, driven by Windows Task Scheduler (default: every
30 minutes, silent - pythonw + CREATE_NO_WINDOW). Inside the configured night
window it keeps unattended night automations alive:

  - ZCode.exe not running            -> start it
  - main window unresponsive for
    >= hang_threshold_min (spanning
    two consecutive checks)          -> kill all ZCode.exe processes, restart

Configuration is read from nightwatch.json next to this script (written by
install-nightwatch.ps1):
    {
      "zcode_exe": "D:\\...\\ZCode.exe",
      "window": ["23:00", "09:00"],
      "hang_threshold_min": 15,
      "busy_retry_window": "all_day",
      "extra_patchers": [                       # optional, beyond busy-retry
        {"name": "compact-70%", "marker": "Math.max(0,Math.floor(t*.7))",
         "script": "D:\\...\\zcode-compact-patch.py"}
      ]
    }

Patch self-heal runs on EVERY tick (day and night - upgrades happen any
time): when the busy-retry / extra patch markers are absent from zcode.cjs
(i.e. ZCode just upgraded), the patchers are re-applied silently. The patched
code loads on the app's next start; ZCode is NEVER restarted by the heal step.

CLI flags override the config:
    --force                  ignore the night window (testing)
    --dry-run                log actions, do not execute
    --window 23:00-09:00     override the window
    --zcode-exe <path>       override the ZCode executable

Exit codes: 0 ok / handled, 1 configuration error.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Imperceptible by design: children (tasklist/powershell/taskkill) must never
# flash a console window when this script runs under pythonw.
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "nightwatch.json"
LOG = HERE / "nightwatch.log"
STATE = HERE / "nightwatch-state.json"

PROC_NAME = "ZCode.exe"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            # utf-8-sig: PowerShell 5.1's "UTF8" Set-Content writes a BOM
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def resolve_zcode_exe(cfg: dict, cli_value: str | None) -> str | None:
    if cli_value:
        return cli_value
    if cfg.get("zcode_exe"):
        return cfg["zcode_exe"]
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ZCode" / "ZCode.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "ZCode" / "ZCode.exe",
    ]
    for c in candidates:
        try:
            if c.exists():
                return str(c)
        except OSError:
            continue
    return None


def parse_window(spec) -> tuple[str, str]:
    """Accept ["23:00","09:00"] (config) or "23:00-09:00" (CLI/config)."""
    if isinstance(spec, (list, tuple)) and len(spec) == 2:
        return str(spec[0]), str(spec[1])
    if isinstance(spec, str) and "-" in spec:
        a, b = spec.split("-", 1)
        return a.strip(), b.strip()
    return "23:00", "09:00"


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    if sys.stdout:   # sys.stdout is None under pythonw
        print(line)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def in_window(now: datetime, window: tuple[str, str]) -> bool:
    start = datetime.strptime(window[0], "%H:%M").time()
    end = datetime.strptime(window[1], "%H:%M").time()
    t = now.time()
    if start <= end:
        return start <= t <= end
    return t >= start or t <= end   # window crosses midnight


def any_zcode() -> bool:
    # bytes-only capture: tasklist emits GBK ("信息: 没有运行的任务...") when
    # nothing matches, and text mode may decode as utf-8 (system UTF-8 option)
    # crashing the reader thread; decode tolerantly instead.
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {PROC_NAME}", "/FO", "CSV", "/NH"],
        capture_output=True, timeout=30, creationflags=NO_WINDOW,
    )
    stdout = out.stdout.decode("utf-8", errors="replace")
    return PROC_NAME.lower() in stdout.lower()


def windowed_processes():
    """ZCode processes with a real main window (excludes Electron helpers)."""
    cmd = (
        "Get-Process ZCode -ErrorAction SilentlyContinue | "
        "Where-Object {$_.MainWindowHandle -ne 0} | "
        "Select-Object Id,Responding | ConvertTo-Json"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, creationflags=NO_WINDOW,
    )
    s = out.stdout.strip()
    if not s:
        return []
    data = json.loads(s)
    return data if isinstance(data, list) else [data]


def start_zcode(exe: str, dry: bool) -> None:
    if dry:
        log("[dry-run] would start ZCode")
        return
    os.startfile(exe)   # detached launch in the interactive session
    log(f"started {exe}")


def restart_zcode(exe: str, dry: bool) -> None:
    if dry:
        log("[dry-run] would kill hung ZCode and restart")
        return
    subprocess.run(["taskkill", "/IM", PROC_NAME, "/F"], capture_output=True,
                   text=True, creationflags=NO_WINDOW)
    time.sleep(3)
    os.startfile(exe)
    log("killed hung ZCode and restarted")


BUSY_MARKER = "Math.min(e.state.streamRecoveryRetryCount"


def patch_selfheal(cfg: dict, dry: bool) -> None:
    """Re-apply client patches when their markers vanished from zcode.cjs.

    A missing marker means ZCode upgraded and the bundle was replaced. The
    patchers are idempotent and pre-flight node --check the bundle, so a
    half-written (mid-upgrade) file is skipped and retried on the next tick.
    """
    exe = cfg.get("zcode_exe")
    if not exe:
        return
    cjs = Path(str(exe)).parent / "resources" / "glm" / "zcode.cjs"
    if not cjs.exists():
        return
    guards = []
    if (cfg.get("busy_retry_window") or "all_day") != "off":
        guards.append(("busy-retry", BUSY_MARKER, HERE / "busy_retry_patch.py",
                       ["--zcode-exe", str(exe)]))
    for extra in cfg.get("extra_patchers", []):
        try:
            guards.append((extra.get("name", Path(extra["script"]).stem),
                           extra["marker"], Path(extra["script"]),
                           list(extra.get("args", []))))
        except (KeyError, TypeError):
            log(f"[FAIL] bad extra_patchers entry: {extra}")
    for name, marker, script, sargs in guards:
        try:
            present = marker in cjs.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return   # file churn (mid-upgrade) - wait for the next tick
        if present:
            continue
        if dry:
            log(f"[dry-run] would re-apply {name} patch (marker absent)")
            continue
        if not script.exists():
            log(f"[FAIL] {name} patcher missing: {script}")
            continue
        try:
            r = subprocess.run([sys.executable, str(script), *sargs],
                               capture_output=True, text=True, timeout=300,
                               creationflags=NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired) as e:
            log(f"[FAIL] {name} patch reapply error: {e}")
            continue
        if r.returncode == 0:
            log(f"patch reapplied: {name} (marker was absent -> ZCode upgrade?)")
        else:
            log(f"[FAIL] {name} patch reapply rc={r.returncode} - anchor review needed")


def main() -> int:
    args = sys.argv[1:]
    force = "--force" in args
    dry = "--dry-run" in args
    cfg = load_config()

    cli_exe = args[args.index("--zcode-exe") + 1] if "--zcode-exe" in args else None
    zcode_exe = resolve_zcode_exe(cfg, cli_exe)

    window = parse_window(args[args.index("--window") + 1] if "--window" in args
                          else cfg.get("window", ["23:00", "09:00"]))
    hang_min = int(cfg.get("hang_threshold_min", 15))

    patch_selfheal(cfg, dry)   # every tick, window-independent: silent file work only

    now = datetime.now()
    if not force and not in_window(now, window):
        return 0
    if not zcode_exe or not Path(zcode_exe).exists():
        log(f"[FAIL] ZCode.exe not found (config/CLI). "
            f"Run install-nightwatch.ps1 or pass --zcode-exe.")
        return 1

    if not any_zcode():
        STATE.unlink(missing_ok=True)
        log("ZCode not running -> starting")
        start_zcode(zcode_exe, dry)
        return 0

    procs = windowed_processes()
    if procs and not any(p.get("Responding") for p in procs):
        first = None
        if STATE.exists():
            try:
                first = json.loads(STATE.read_text()).get("unresponsiveSince")
            except (json.JSONDecodeError, OSError):
                first = None
        if not first:
            STATE.write_text(json.dumps({"unresponsiveSince": now.isoformat()}))
            log("main window unresponsive (first observation)")
            return 0
        age = (now - datetime.fromisoformat(first)).total_seconds() / 60
        if age >= hang_min:
            log(f"unresponsive for {age:.0f} min (>= {hang_min}) -> restart")
            STATE.unlink(missing_ok=True)
            restart_zcode(zcode_exe, dry)
        else:
            log(f"unresponsive for {age:.0f} min (< {hang_min}), waiting")
        return 0

    STATE.unlink(missing_ok=True)
    log(f"alive ({len(procs)} windowed process(es), responding)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
