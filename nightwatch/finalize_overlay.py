# -*- coding: utf-8 -*-
"""
Finish the status-bar overlay install and bring ZCode back.

Usage:
    python finalize_overlay.py            # wait for ZCode to exit, swap, relaunch
    python finalize_overlay.py --kill     # close ZCode first, then swap and relaunch
    python finalize_overlay.py --no-relaunch

Why this exists: the overlay lives inside resources/app.asar, which ZCode
locks while running. The swap can therefore only happen during a client
exit - and the background watcher is a one-shot process that dies with a
machine reboot. This script makes the whole dance a single command:

    1. wait (or trigger) the client's exit
    2. atomically swap the staged package in
    3. relaunch ZCode, now with the status bar

Requires a staged install: app.asar.zusage.tmp + .json record next to the
asar. Use overlay_heal.py to stage one.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
HERE = Path(__file__).resolve().parent
PROC_NAME = "ZCode.exe"
MARKER = b"inject-main.cjs"


def zcode_pids() -> set:
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {PROC_NAME}", "/FO", "CSV", "/NH"],
        capture_output=True, timeout=30, creationflags=NO_WINDOW)
    text = out.stdout.decode("utf-8", errors="replace")
    pids = set()
    for line in text.splitlines():
        if PROC_NAME.lower() in line.lower() and '"' in line:
            try:
                pids.add(int(line.split('","')[1]))
            except (ValueError, IndexError):
                pass
    return pids


def runtime_dir() -> Path:
    cfg = HERE / "nightwatch.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8-sig"))
            if data.get("overlay_runtime_dir"):
                return Path(data["overlay_runtime_dir"])
        except (json.JSONDecodeError, OSError):
            pass
    return Path(r"C:\Users\doing\.zcode\zcode-token-usage-statusbar")


def zcode_exe() -> str:
    cfg = HERE / "nightwatch.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8-sig"))
            if data.get("zcode_exe"):
                return str(data["zcode_exe"])
        except (json.JSONDecodeError, OSError):
            pass
    return r"D:\Users\doing\AppData\Local\Programs\ZCode\ZCode.exe"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kill", action="store_true", help="close ZCode first")
    ap.add_argument("--no-relaunch", action="store_true", help="do not relaunch ZCode")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    rt = runtime_dir()
    exe = zcode_exe()
    asar = Path(exe).parent / "resources" / "app.asar"
    if not asar.exists():
        print(f"[FAIL] asar not found: {asar}")
        return 1
    if MARKER in asar.read_bytes():
        print("[OK] overlay already injected - nothing to do")
        if not args.no_relaunch:
            os.startfile(exe)
            print(f"[OK] relaunched {exe}")
        return 0

    tmp = asar.with_name(asar.name + ".zusage.tmp")
    rec = asar.with_name(asar.name + ".zusage.tmp.json")
    if not (tmp.exists() and rec.exists()):
        print("[FAIL] no staged install found - run overlay_heal.py first")
        return 1

    if args.kill:
        print("[..] closing ZCode ...")
        subprocess.run(["taskkill", "/IM", PROC_NAME, "/F"], capture_output=True,
                       creationflags=NO_WINDOW)

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        if not zcode_pids():
            break
        time.sleep(1)
    else:
        print("[FAIL] ZCode still running - timed out")
        return 1

    sys.path.insert(0, str(rt))
    try:
        import patch_install as pi
    except Exception as e:                        # noqa: BLE001
        print(f"[FAIL] cannot import patch_install: {e}")
        return 1
    try:
        pi.set_target(asar)
        verified = {}
        ok = pi.finalize_tmp(operation="install", client_closed=lambda: True,
                             verified=verified)
    except Exception as e:                        # noqa: BLE001
        print(f"[FAIL] finalize failed: {e!r}")
        return 1
    if not ok:
        print("[FAIL] finalize_tmp returned False")
        return 1

    injected = MARKER in asar.read_bytes()
    print(f"[OK] overlay swapped in (injection marker present = {injected})")
    if not args.no_relaunch:
        os.startfile(exe)
        print(f"[OK] relaunched {exe}")
    return 0 if injected else 1


if __name__ == "__main__":
    sys.exit(main())
