# -*- coding: utf-8 -*-
"""
Overlay heal — keep the token-usage status bar (zcode-token-usage-statusbar)
alive across ZCode upgrades.

ZCode replaces resources/app.asar on upgrade, which drops the injected
overlay line. Re-injecting requires ZCode to be fully closed (the file is
locked while the app runs), so this heal step only:

  1. stages a pending install (repack + signed record) when no valid pending
     record exists, and
  2. makes sure a detached finalize watcher is alive — it swaps the staged
     package in during the next ZCode exit.

It never restarts ZCode and never touches the running app.

Configuration (nightwatch.json):
    "overlay_runtime_dir": "C:\\Users\\you\\.zcode\\zcode-token-usage-statusbar"
Omit the key to disable overlay healing.

Usage:
    python overlay_heal.py [--runtime-dir PATH] [--asar PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
DETACHED = 0x00000008 if os.name == "nt" else 0     # DETACHED_PROCESS
BREAKAWAY = 0x01000000 if os.name == "nt" else 0   # CREATE_BREAKAWAY_FROM_JOB

MARKER = b"inject-main.cjs"
WATCHER = "finalize_watch.py"


def log(msg: str) -> None:
    if sys.stdout:
        print(msg)


def pending_paths(asar: Path):
    tmp = asar.with_name(asar.name + ".zusage.tmp")
    rec = asar.with_name(asar.name + ".zusage.tmp.json")
    return tmp, rec


def pending_valid(asar: Path) -> bool:
    tmp, rec = pending_paths(asar)
    if not (tmp.exists() and rec.exists()):
        return False
    try:
        data = json.loads(rec.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return False
    if data.get("operation") != "install" or not data.get("validated"):
        return False
    try:
        return tmp.stat().st_size == data.get("tmp", {}).get("size")
    except (OSError, AttributeError):
        return False


def watcher_alive(runtime: Path) -> bool:
    """True when a finalize watcher for this runtime is already running."""
    # no inner double quotes: subprocess mangles them into the -Command string
    cmd = ("(Get-CimInstance Win32_Process | Where-Object "
           "{$_.CommandLine -like '*" + WATCHER + "*'}).Count")
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=NO_WINDOW)
        text = (out.stdout or "").strip().splitlines()
        return bool(text) and text[-1].strip() not in ("", "0")
    except (OSError, subprocess.TimeoutExpired):
        return False


def spawn_watcher(runtime: Path, dry: bool) -> bool:
    script = runtime / WATCHER
    if not script.exists():
        log(f"[SKIP] watcher script missing: {script}")
        return False
    pyw = None
    for cand in ("pythonw.exe", "python.exe"):
        path = Path(sys.executable).with_name(cand)
        if path.exists():
            pyw = path
            break
    if pyw is None:
        log("[SKIP] no python interpreter found for watcher")
        return False
    if dry:
        log(f"[dry-run] would spawn watcher: {pyw} {script}")
        return True
    kwargs = dict(cwd=str(runtime), stdin=subprocess.DEVNULL,
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Preferred: WMI/CIM creation - the process is parented by WmiPrvSE and
    # therefore survives the caller's job object. A plain Popen child dies
    # with the ZCode session that spawned it (observed repeatedly: the
    # watcher vanished minutes after an agent tool call ended).
    spawn_ps1 = runtime / "spawn_finalize_watch.ps1"
    if spawn_ps1.exists():
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(spawn_ps1)],
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=60, creationflags=NO_WINDOW)
            if r.returncode == 0 and "ReturnValue=0" in (r.stdout or ""):
                return True
            log(f"[WARN] WMI spawn returned: {(r.stdout or '').strip()[:120]}")
        except (OSError, subprocess.TimeoutExpired) as e:
            log(f"[WARN] WMI spawn failed: {e}")
    try:
        subprocess.Popen([str(pyw), str(script)],
                         creationflags=NO_WINDOW | DETACHED | BREAKAWAY, **kwargs)
        return True
    except OSError:
        # job objects may refuse breakaway - fall back to a plain detached run
        try:
            subprocess.Popen([str(pyw), str(script)],
                             creationflags=NO_WINDOW | DETACHED, **kwargs)
            return True
        except OSError as e:
            log(f"[FAIL] watcher spawn failed: {e}")
            return False


def stage_install(runtime: Path, asar: Path, dry: bool) -> bool:
    """Repack the asar with the injection line and write the pending record."""
    pi_path = runtime / "patch_install.py"
    if not pi_path.exists():
        log(f"[SKIP] patch_install.py missing in {runtime}")
        return False
    if dry:
        log(f"[dry-run] would stage install into {asar}")
        return True
    sys.path.insert(0, str(runtime))
    try:
        import patch_install as pi
    except Exception as e:                      # noqa: BLE001
        log(f"[FAIL] cannot import patch_install: {e}")
        return False
    try:
        pi.set_target(asar)
        # no console monitor from install: we arm our own detached watcher
        os.environ["ZUSAGE_NO_MONITOR"] = "1"
        ok = pi.install()
        log(f"[OK] staged install (pending record written): {bool(ok)}")
        return bool(ok)
    except Exception as e:                      # noqa: BLE001
        log(f"[FAIL] staging failed: {e!r}")
        return False
    finally:
        sys.path.pop(0)


def heal(runtime: Path, asar: Path, dry: bool = False) -> int:
    if not runtime.is_dir():
        log(f"[SKIP] overlay runtime dir not found: {runtime}")
        return 0
    if not asar.exists():
        log(f"[SKIP] asar not found: {asar}")
        return 0
    try:
        if MARKER in asar.read_bytes():
            return 0    # injected - nothing to do
    except OSError:
        return 0

    if not pending_valid(asar):
        stage_install(runtime, asar, dry)
    else:
        log("[OK] pending install already staged")

    if watcher_alive(runtime):
        log("[OK] finalize watcher already alive")
    elif spawn_watcher(runtime, dry):
        log("[OK] finalize watcher armed (swaps in on next ZCode exit)")
    else:
        log("[FAIL] could not arm finalize watcher - install stays staged")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime-dir", default="")
    ap.add_argument("--asar", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    runtime = Path(args.runtime_dir) if args.runtime_dir else Path(
        r"C:\Users\doing\.zcode\zcode-token-usage-statusbar")
    asar = Path(args.asar) if args.asar else Path(
        r"D:\Users\doing\AppData\Local\Programs\ZCode\resources\app.asar")
    return heal(runtime, asar, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
