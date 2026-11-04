# -*- coding: utf-8 -*-
"""
Busy-retry patcher with time-window gate (打更人 429 守护).

Patches resources\\glm\\zcode.cjs so that start-plan busy errors
(provider codes 3008/3009/3010, HTTP 429) are retried ENDLESSLY with a
backoff table capped at 60s - inside the configured time window. Outside the
window the lookup yields void 0 and the turn fails fast (stock behaviour).

Sites (idempotent; minified variable names captured via regex):
  1+2. delay tables [1e3,2e3] -> 10 entries (1s..60s)
       main-turn admission retry (0-based) / goal-verification retry (1-based)
  3.   main-turn lookup -> gated Math.min clamp (first-turn guard <0 included)
  4.   goal-verification lookup -> gated Math.min clamp

The gate is an inline IIFE with the window baked in as a literal ("00:00-24:00"
= all day) - zero runtime file I/O. Re-running with a different --window
updates the baked literal in place.

Window sources (later wins): nightwatch.json "busy_retry_window"
("all_day" | "night" | "HH:MM-HH:MM")  <  --window CLI.

Usage:
    python busy_retry_patch.py --zcode-exe "D:\\...\\ZCode.exe" [--window all_day]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "nightwatch.json"

PROVIDER_SET = 'new Set(["account:bigmodel-start-plan","account:zai-start-plan"])'
TABLE_BODY = "1e3,2e3,5e3,1e4,15e3,3e4,3e4,45e3,6e4,6e4"
NEW_TABLE = f"[{TABLE_BODY}]"
ORIG_BODY = "1e3,2e3"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def resolve_window(cli_value: str | None, cfg: dict) -> str:
    spec = cli_value or cfg.get("busy_retry_window") or "all_day"
    if spec == "all_day":
        return "00:00-24:00"
    if spec == "night":
        return "-".join(cfg.get("window", ["23:00", "09:00"]))
    if spec == "off":
        return "off"
    if re.fullmatch(r"\d{1,2}:\d{2}-\d{1,2}:\d{2}", spec):
        return spec
    raise ValueError(f"unknown window spec: {spec}")


def gate_js(window: str) -> str:
    """Inline IIFE: true inside the window, false outside. Baked literal."""
    return (
        '(function(){var w="' + window + '";try{var p=w.split("-"),s=p[0].split(":"),'
        'e2=p[1].split(":"),d=new Date(),t=d.getHours()*60+d.getMinutes(),'
        "a=(+s[0])*60+(+s[1]),b=(+e2[0])*60+(+e2[1]);"
        "if(a<=b)return t>=a&&t<=b;return t>=a||t<=b}catch(e){return true}})()"
    )


# --- site 1/2: delay tables (unchanged semantics from zcode-fixes patcher) ---
TABLE_SITES = [
    (
        "main-turn admission retry table",
        re.compile(re.escape(PROVIDER_SET) + r",([\w$]+)=\[[\d,e.]+\]"),
        re.compile(re.escape(PROVIDER_SET) + r",([\w$]+)=" + re.escape(NEW_TABLE)),
        PROVIDER_SET + r",\1=" + NEW_TABLE,
    ),
    (
        "goal-verification retry table",
        re.compile(r"([\w$]+)=\[[\d,e.]+\],([\w$]+)=" + re.escape(PROVIDER_SET)),
        re.compile(r"([\w$]+)=" + re.escape(NEW_TABLE) + r",([\w$]+)=" + re.escape(PROVIDER_SET)),
        r"\1=" + NEW_TABLE + r",\2=" + PROVIDER_SET,
    ),
]

# --- site 3: main-turn lookup, gated ---
# source forms: pristine (return TBL[...], turnNumber<=0) and
# capped (return TBL[Math.min(...)], turnNumber<=0 or <0)
L3O_PRISTINE = re.compile(
    r"function ([\w$]+)\(e\)\{if\(!\(e\.turnNumber<=0\)&&([\w$]+)\.has\(e\.providerId\)"
    r"&&([\w$]+)\(e\.error\)\)return ([\w$]+)\[e\.state\.streamRecoveryRetryCount\]\}"
)
L3O_CAPPED = re.compile(
    r"function ([\w$]+)\(e\)\{if\(!\(e\.turnNumber(?:<=|<)0\)&&([\w$]+)\.has\(e\.providerId\)"
    r"&&([\w$]+)\(e\.error\)\)return ([\w$]+)\[Math\.min\(e\.state\.streamRecoveryRetryCount,\4\.length-1\)\]\}"
)
L3O_FINAL_T = (
    "function @FN@(e){if(!(e.turnNumber<0)&&@PSET@.has(e.providerId)&&@CHK@(e.error))"
    "return @GATE@?@TBL@[Math.min(e.state.streamRecoveryRetryCount,@TBL@.length-1)]:void 0}"
)
L3O_DONE = re.compile(
    r"function ([\w$]+)\(e\)\{if\(!\(e\.turnNumber<0\)&&([\w$]+)\.has\(e\.providerId\)"
    r"&&([\w$]+)\(e\.error\)\)return \(function\(\)\{var w=\"([^\"]*)\";"
)

# --- site 4: goal-verification lookup, gated ---
U3O_PRISTINE = re.compile(
    r"let ([\w$]+)=([\w$]+)\[([\w$]+)-1\];"
    r"if\(e\.abortSignal\?\.aborted\|\|\1===void 0\|\|!([\w$]+)\(o,e\.model\.providerId\)\)throw o;"
)
U3O_CAPPED = re.compile(
    r"let ([\w$]+)=([\w$]+)\[Math\.min\(([\w$]+)-1,\2\.length-1\)\];"
    r"if\(e\.abortSignal\?\.aborted\|\|\1===void 0\|\|!([\w$]+)\(o,e\.model\.providerId\)\)throw o;"
)
U3O_FINAL_T = (
    "let @VAR@=@GATE@?@TBL@[Math.min(@IDX@-1,@TBL@.length-1)]:void 0;"
    "if(e.abortSignal?.aborted||@VAR@===void 0||!@CHK@(o,e.model.providerId))throw o;"
)
U3O_DONE = re.compile(
    r'let ([\w$]+)=\(function\(\)\{var w="([^"]*)".*?\}\)\(\)\?'
    r"([\w$]+)\[Math\.min\(([\w$]+)-1,\3\.length-1\)\]:void 0;"
    r"if\(e\.abortSignal\?\.aborted\|\|\1===void 0\|\|!([\w$]+)\(o,e\.model\.providerId\)\)throw o;"
)


def l3o_final(m, gate: str) -> str:
    return (
        L3O_FINAL_T.replace("@FN@", m.group(1))
        .replace("@PSET@", m.group(2))
        .replace("@CHK@", m.group(3))
        .replace("@TBL@", m.group(4))
        .replace("@GATE@", gate)
    )


def u3o_final(m, gate: str) -> str:
    return (
        U3O_FINAL_T.replace("@VAR@", m.group(1))
        .replace("@TBL@", m.group(2))
        .replace("@IDX@", m.group(3))
        .replace("@CHK@", m.group(4))
        .replace("@GATE@", gate)
    )


def apply_site(data: str, name: str, source_res, done_re, final_builder, window: str):
    """source_res: list of regexes accepting earlier forms (first match wins)."""
    done = list(done_re.finditer(data))
    if len(done) == 1:
        baked = done[0]
        gm = re.search(r'var w="([^"]*)"', baked.group(0))
        if gm is None:
            # table sites: patched form carries no window literal - nothing to swap
            return data, f"[SKIP] {name}: already patched", False
        current = gm.group(1)
        if current == window:
            return data, f"[SKIP] {name}: already gated to {window}", False
        new_data = (
            data[: baked.start()]
            + baked.group(0).replace(f'var w="{current}"', f'var w="{window}"', 1)
            + data[baked.end() :]
        )
        return new_data, f"[OK] {name}: window {current} -> {window}", True
    for rx in source_res:
        ms = list(rx.finditer(data))
        if len(ms) == 1:
            m = ms[0]
            new_data = data[: m.start()] + final_builder(m, gate_js(window)) + data[m.end() :]
            return new_data, f"[OK] {name}", True
        if len(ms) > 1:
            return data, f"[FAIL] {name}: {len(ms)} matches for one source form", False
    return data, (
        f"[FAIL] {name}: no known form found. Upstream may have changed - "
        "inspect: grep -o '.\\{40\\}zai-start-plan\".\\{60\\}' zcode.cjs"
    ), False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zcode-exe", dest="zcode_exe", default="")
    ap.add_argument("--window", default="")
    args = ap.parse_args()

    cfg = load_config()
    zcode_exe = args.zcode_exe or cfg.get("zcode_exe") or ""
    if not zcode_exe or not Path(zcode_exe).exists():
        print("[FAIL] ZCode.exe unknown - pass --zcode-exe or install first")
        return 1
    cjs = Path(zcode_exe).parent / "resources" / "glm" / "zcode.cjs"
    if not cjs.exists():
        print(f"[FAIL] zcode.cjs not found: {cjs}")
        return 1

    try:
        window = resolve_window(args.window, cfg)
    except ValueError as e:
        print(f"[FAIL] {e}")
        return 1
    if window == "off":
        print("[SKIP] busy-retry guard is off (config) - nothing to patch")
        return 0

    data = cjs.read_text(encoding="utf-8", errors="ignore")
    changed = False
    statuses = []

    # nested-array self-heal (legacy buggy write)
    nested = f"[[{TABLE_BODY}]]"
    if nested in data:
        data = data.replace(nested, NEW_TABLE)
        changed = True
        statuses.append("[OK] repaired nested-array damage")

    for name, rx, done_rx, repl in TABLE_SITES:
        data, s, c = apply_site(
            data, name, [rx], done_rx, lambda m, g, repl=repl: m.expand(repl), window,
        )
        statuses.append(s)
        changed |= c

    data, s, c = apply_site(
        data, "main-turn busy retry (gated)", [L3O_CAPPED, L3O_PRISTINE], L3O_DONE,
        lambda m, g: l3o_final(m, g), window,
    )
    statuses.append(s)
    changed |= c

    data, s, c = apply_site(
        data, "goal-verification busy retry (gated)", [U3O_CAPPED, U3O_PRISTINE], U3O_DONE,
        lambda m, g: u3o_final(m, g), window,
    )
    statuses.append(s)
    changed |= c

    for s in statuses:
        print(s)
    if any(s.startswith("[FAIL]") for s in statuses):
        return 1
    if not changed:
        return 0

    backup = cjs.with_suffix(f".cjs.bak-{date.today():%Y%m%d}")
    if not backup.exists():
        shutil.copy2(cjs, backup)
        print(f"[OK] backup written: {backup.name}")

    with cjs.open("w", encoding="utf-8", newline="") as fh:
        fh.write(data)

    check = cjs.read_text(encoding="utf-8", errors="ignore")
    ok = check.count(NEW_TABLE) == 2 and f'var w="{window}"' in check
    if not ok:
        print("[FAIL] patch applied but verification failed")
        return 1

    node = shutil.which("node")
    if node:
        proc = subprocess.run([node, "--check", str(cjs)], capture_output=True, text=True)
        if proc.returncode != 0:
            print("[FAIL] node --check rejected the patched bundle:")
            print(proc.stderr[:500])
            return 1
        print("[OK] node --check passed")

    print(f"[OK] busy-retry guard active, window {window} (endless retry, 60s cap)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
