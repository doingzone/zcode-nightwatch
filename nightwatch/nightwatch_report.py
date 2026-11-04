# -*- coding: utf-8 -*-
"""
Nightwatch effectiveness report (战报).

Aggregates real records so the user can see what the night-defense stack
actually saved:

  1. 429 自动挽回 — busy-retry events from ZCode daily logs (client patch
     layer: each "Main turn retrying / Goal completion verification retrying"
     line is an interruption the endless-retry patch absorbed);
  2. 429 未挽回 — sessions whose turn died to busy errors (tasks-index
     lastError, mostly from before the patch existed);
  3. 应用级挽回 — watchdog saves from nightwatch.log (crash relaunches,
     hang restarts) plus routine check counts;
  4. patch presence check — so numbers are read in the right context.

Usage:
    python nightwatch_report.py [--days 7] [--md [path]]
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "nightwatch.json"
NW_LOG = HERE / "nightwatch.log"

BUSY_CODES = {"3008", "3009", "3010"}
SIG_BUSY_RETRY = "Main turn retrying after Start Plan admission busy"
SIG_VERIFY_RETRY = "Goal completion verification retrying after Start Plan busy"
SIG_BUSY_EXHAUSTED = "Start Plan is busy and automatic model stream recovery"
SIG_GENERIC_RETRY = "Model request retry scheduled"
RE_LIMITED = re.compile(r'"reason":"(rate_limited|provider_overloaded)"')
TS_BRACKET_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")   # ZCode logs: [ts] ...
TS_PLAIN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")       # nightwatch.log: ts ...


def line_ts(line: str) -> str | None:
    m = TS_BRACKET_RE.match(line) or TS_PLAIN_RE.match(line)
    return m.group(1) if m else None


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def zcode_data_dir(cfg: dict) -> Path:
    raw = cfg.get("zcode_data_dir") or Path(os.environ.get("USERPROFILE", "")) / ".zcode"
    return Path(str(raw))


def scan_zcode_logs(logs_dir: Path, days: int) -> dict:
    """One pass per daily log file; count patch-layer events."""
    since = datetime.now() - timedelta(days=days)
    out = {
        "busy_retry": 0, "verify_retry": 0, "exhausted": 0,
        "generic_limited": 0, "first": None, "last": None, "files": 0,
        "dir_missing": not logs_dir.is_dir(),
    }
    if not logs_dir.is_dir():
        return out
    for f in sorted(logs_dir.glob("*.log")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", f.stem)
        if not m:
            continue
        try:
            fday = datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            continue
        if fday < since.replace(hour=0, minute=0, second=0, microsecond=0):
            continue
        out["files"] += 1
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            hit = None
            if SIG_BUSY_RETRY in line:
                out["busy_retry"] += 1; hit = True
            elif SIG_VERIFY_RETRY in line:
                out["verify_retry"] += 1; hit = True
            elif SIG_BUSY_EXHAUSTED in line:
                out["exhausted"] += 1; hit = True
            elif SIG_GENERIC_RETRY in line and RE_LIMITED.search(line):
                out["generic_limited"] += 1; hit = True
            if hit:
                ts = line_ts(line)
                if ts:
                    if out["first"] is None:
                        out["first"] = ts
                    out["last"] = ts
    return out


def scan_unsaved(index_path: Path, days: int) -> list:
    """Tasks whose lastError was a busy 429 death — the 'not saved' column."""
    since = datetime.now() - timedelta(days=days)
    rows = []
    if not index_path.exists():
        return rows
    tmp = Path(tempfile.mkdtemp(prefix="nightwatch-report-"))
    try:
        for suffix in ("", "-wal", "-shm"):
            src = Path(str(index_path) + suffix)
            if src.exists():
                shutil.copy2(src, tmp / ("tasks-index.sqlite" + suffix))
        db = sqlite3.connect(str(tmp / "tasks-index.sqlite"))
        db.row_factory = sqlite3.Row
        for row in db.execute("SELECT task_id, title, updated_at, meta_json FROM tasks"):
            meta = row["meta_json"]
            if not meta or "Start Plan is busy" not in meta and "3009" not in meta and "3008" not in meta and "3010" not in meta:
                continue
            try:
                m = json.loads(meta)
            except json.JSONDecodeError:
                continue
            le = m.get("lastError") or {}
            attr = le.get("attribution") or {}
            code = str(attr.get("providerErrorCode") or "")
            if code not in BUSY_CODES and "Start Plan is busy" not in str(le.get("message", "")):
                continue
            try:
                dt = datetime.fromtimestamp(row["updated_at"] / 1000)
            except (TypeError, OSError, ValueError):
                continue
            if dt < since:
                continue
            rows.append({"date": dt.strftime("%m-%d %H:%M"), "title": row["title"] or row["task_id"][:24], "code": code})
        db.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def scan_watchdog_log(days: int) -> dict:
    since = datetime.now() - timedelta(days=days)
    out = {"relaunch": 0, "restart": 0, "checks": 0, "reapplied": 0, "events": []}
    if not NW_LOG.exists():
        return out
    for line in NW_LOG.read_text(encoding="utf-8", errors="ignore").splitlines():
        ts = line_ts(line)
        if not ts:
            continue
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if dt < since:
            continue
        if "alive (" in line:
            out["checks"] += 1
        elif "patch reapplied" in line:
            out["reapplied"] += 1
            out["events"].append(f"{ts[5:]}  换了宅子补丁被扫了 → 自动补回")
        elif "not running -> starting" in line:
            out["relaunch"] += 1
            out["events"].append(f"{ts[5:]}  三更天,ZCode 没了 → 点灯拉起")
        elif "killed hung" in line:
            out["restart"] += 1
            out["events"].append(f"{ts[5:]}  装死被识破 → 强制拍醒")
        elif "unresponsive" in line:
            out["events"].append(f"{ts[5:]}  有装死嫌疑,再盯一轮")
    return out


def patch_present(cfg: dict) -> bool | None:
    exe = cfg.get("zcode_exe")
    if not exe:
        return None
    cjs = Path(str(exe)).parent / "resources" / "glm" / "zcode.cjs"
    if not cjs.exists():
        return None
    try:
        return "Math.min(e.state.streamRecoveryRetryCount" in cjs.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def fmt_ts(ts: str | None) -> str:
    return ts[5:] if ts else "-"


def main() -> int:
    args = sys.argv[1:]
    # Force UTF-8 bytes regardless of console codepage (cmd pipes default to
    # the ANSI codepage on zh-CN Windows, which garbles the Chinese report).
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    days = int(args[args.index("--days") + 1]) if "--days" in args else 7
    md_path = None
    if "--md" in args:
        i = args.index("--md")
        md_path = args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("--") else str(HERE / "nightwatch-report.md")

    cfg = load_config()
    logs_dir = zcode_data_dir(cfg) / "v2" / "logs"
    index = zcode_data_dir(cfg) / "v2" / "tasks-index.sqlite"

    logs = scan_zcode_logs(logs_dir, days)
    unsaved = scan_unsaved(index, days)
    nw = scan_watchdog_log(days)
    patch = patch_present(cfg)

    saved_api = logs["busy_retry"] + logs["verify_retry"] + logs["generic_limited"]
    saved_app = nw["relaunch"] + nw["restart"]
    mode_raw = cfg.get("busy_retry_window") or "all_day"
    if mode_raw == "all_day":
        mode = "全天"
    elif mode_raw == "night":
        mode = "夜间(" + "-".join(cfg.get("window", ["23:00", "09:00"])) + ")"
    elif mode_raw == "off":
        mode = "已关闭"
    else:
        mode = mode_raw
    patch_txt = "是" if patch else ("否" if patch is False else "未知")
    lines = []
    lines.append(f"=== 打更人战报(近 {days} 天,{datetime.now():%Y-%m-%d %H:%M} 生成)===")
    lines.append("")
    lines.append(f"[客户端补丁层] 429 守护时段: {mode} | busy-retry 补丁在场: {patch_txt}")
    if logs.get("dir_missing"):
        lines.append(f"  [提示] 未找到 ZCode 日志目录 {logs_dir} —— 检查 nightwatch.json 的 zcode_data_dir")
    lines.append(f"  429 忙碌重试(主回合): {logs['busy_retry']} 次")
    lines.append(f"  429 忙碌重试(目标校验): {logs['verify_retry']} 次")
    lines.append(f"  通用层限流重试(rate_limited/overloaded): {logs['generic_limited']} 次")
    lines.append(f"  ⇒ API 层挽回的中断尝试合计: {saved_api} 次(每次重试 = 一次原本会弹窗终止的报错被自动消化)")
    if logs["first"]:
        lines.append(f"  事件时间跨度: {fmt_ts(logs['first'])} ~ {fmt_ts(logs['last'])}")
    lines.append(f"  429 导致的回合死亡(未挽回): {logs['exhausted']} 例 / tasks 索引记录 {len(unsaved)} 例")
    for r in unsaved[:5]:
        lines.append(f"    - {r['date']} [{r['code']}] {r['title'][:40]}")
    lines.append("")
    lines.append(f"[应用守护层] 巡更: {nw['checks']} 次")
    lines.append(f"  点灯拉起: {nw['relaunch']} 次;拍醒重启: {nw['restart']} 次;补丁自动重打: {nw['reapplied']} 次")
    for e in nw["events"][:10]:
        lines.append(f"    - {e}")
    lines.append("")
    lines.append(f"=== 合计挽回: API 层 {saved_api} 次 + 应用层 {saved_app} 次 = {saved_api + saved_app} 次 ===")
    if not saved_api and not saved_app:
        lines.append("(窗口期内未发生需要挽回的中断——没有消息就是好消息)")
    report = "\n".join(lines)

    print(report)
    if md_path:
        Path(md_path).write_text(report, encoding="utf-8")
        print(f"[md written] {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
