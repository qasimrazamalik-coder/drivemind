"""Weekly report and the large-file finder.

Weekly report: what DriveMind did for you in the last N days (from the undo journal) and
how the system drive changed (from the daily snapshots). Nothing is estimated.

Large files: the biggest files in your folders, with when you last opened them, so you can
decide what to let go. Removing one is always a question for you: it goes to quarantine
(30 days to change your mind), and no mode, not even Autopilot, does it on its own.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from . import db
from .config import Settings
from .paths import is_protected
from .plan import Op, Plan
from .planner import build_action
from .scanner import iter_files

FREEING_OPS = ("quarantine", "delete_cache")
# Archiving a project zips it and quarantines the original. The zip still takes space, so like the
# plan summary, neither the archive row nor that quarantine row counts as freed.
ARCHIVE_ORIGINAL = "original kept after archiving"
SKIP_DIRS = {"node_modules", ".git", "AppData", "$Recycle.Bin", "System Volume Information", "Windows",
             "Program Files", "Program Files (x86)", "ProgramData"}
LARGE_OPTION = "quarantine_large_files"  # never in a mode preset, so it always asks


def weekly(days: int = 7, drive: Optional[str] = None) -> Dict:
    since = time.time() - days * 86400
    conn = db.connect()
    rows = conn.execute("SELECT plan_id, op, dst, size, reason FROM journal WHERE ts >= ? AND undone = 0", (since,)).fetchall()
    freeing = [r for r in rows if r["op"] in FREEING_OPS and r["reason"] != ARCHIVE_ORIGINAL]
    freed = sum(r["size"] or 0 for r in freeing)
    moves = [r for r in rows if r["op"] == "move"]
    folders = Counter(Path(r["dst"]).parent.name for r in moves if r["dst"])
    growth = None
    if drive is None:
        from .disk import system_drive
        drive = system_drive()
    first = conn.execute("SELECT used FROM snapshots WHERE drive=? AND ts >= ? ORDER BY ts ASC LIMIT 1",
                         (drive, since)).fetchone()
    last = conn.execute("SELECT used FROM snapshots WHERE drive=? ORDER BY ts DESC LIMIT 1", (drive,)).fetchone()
    if first and last:
        growth = int(last["used"]) - int(first["used"])
    return {
        "days": days,
        "drive": drive,
        "freed_bytes": int(freed),
        "moved_files": len(moves),
        "cleaned_files": len(freeing),
        "plans_applied": len({r["plan_id"] for r in rows if r["plan_id"]}),
        "growth_bytes": growth,
        "top_categories": [{"name": n, "files": c} for n, c in folders.most_common(5)],
    }


def weekly_text(r: Dict) -> str:
    from .scanner import human
    parts = []
    if r["freed_bytes"]:
        parts.append(f"freed {human(r['freed_bytes'])}")
    if r["moved_files"]:
        parts.append(f"organized {r['moved_files']} files")
    if not parts:
        parts.append("had nothing to clean")
    if r["growth_bytes"] is not None:
        verb = "grew by" if r["growth_bytes"] >= 0 else "shrank by"
        parts.append(f"drive {r['drive']} {verb} {human(abs(r['growth_bytes']))}")
    return f"This week DriveMind {', '.join(parts)}."


def large_files(roots: Iterable[Path], min_bytes: int = 500 * 1024 * 1024, limit: int = 50,
                settings: Optional[Settings] = None) -> List[Dict]:
    """The biggest files under `roots`, largest first, skipping system and protected folders."""
    settings = settings or Settings.load()
    seen, out = set(), []
    for root in roots:
        for f in iter_files(Path(root), skip_dir=lambda p: p.name in SKIP_DIRS or p.name.startswith(".")):
            if f.size < min_bytes or str(f.path) in seen or is_protected(f.path, settings.exclusions):
                continue
            seen.add(str(f.path))
            out.append({"path": str(f.path), "name": f.path.name, "size": f.size, "mtime": f.mtime,
                        "last_used": max(f.mtime, f.atime), "ext": f.ext})
    out.sort(key=lambda x: x["size"], reverse=True)
    return out[:limit]


def plan_large(paths: Iterable[str], settings: Optional[Settings] = None) -> Plan:
    """Quarantine the files you picked. Every step waits for your approval."""
    settings = settings or Settings.load()
    plan = Plan(title="Let go of large files", kind="large")
    for p in paths:
        path = Path(p)
        if not path.is_file() or is_protected(path, settings.exclusions):
            plan.notes.append(f"Skipped {p}: not a file DriveMind may touch")
            continue
        a = build_action(settings, Op.QUARANTINE, path, None, path.stat().st_size, "Large files",
                         "you picked it in Large files; kept in quarantine for 30 days", 1.0, LARGE_OPTION)
        plan.actions.append(a)
    return plan
