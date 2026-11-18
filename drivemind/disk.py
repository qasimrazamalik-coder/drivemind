"""Disk Guardian: drive list, health score, free-space snapshots, growth and forecast."""

from __future__ import annotations

import os
import shutil
import string
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import db
from .scanner import ScanResult


@dataclass
class DriveStatus:
    drive: str
    total: int
    used: int
    free: int
    free_percent: float
    score: int
    status: str            # good | watch | critical
    days_to_full: Optional[float] = None
    trend: str = "learning"  # learning (not enough history) | stable | filling

    def to_dict(self) -> Dict:
        return asdict(self)


def list_drives() -> List[str]:
    if sys.platform == "win32":
        return [f"{c}:\\" for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")]
    drives = ["/"]
    home = str(Path.home())
    try:
        if os.stat(home).st_dev != os.stat("/").st_dev:
            drives.append(home)
    except OSError:
        pass
    return drives


def system_drive() -> str:
    if sys.platform == "win32":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return "/"


def health_score(free_percent: float) -> int:
    """0-100. SSDs slow down and Windows updates fail when free space runs low."""
    points = [(0, 0), (5, 20), (10, 45), (15, 60), (20, 75), (30, 100)]
    if free_percent >= 30:
        return 100
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= free_percent <= x1:
            return round(y0 + (y1 - y0) * (free_percent - x0) / (x1 - x0))
    return 0


def status_for(free_percent: float, alert_percent: float = 15.0) -> str:
    if free_percent < max(5.0, alert_percent / 2):
        return "critical"
    if free_percent < alert_percent:
        return "watch"
    return "good"


def drive_status(drive: str, alert_percent: float = 15.0) -> Optional[DriveStatus]:
    try:
        u = shutil.disk_usage(drive)
    except OSError:
        return None
    usable = u.used + u.free  # like `df`: space reserved for the system is not counted
    free_pct = 100.0 * u.free / usable if usable else 0.0
    days = forecast_days_to_full(drive)
    return DriveStatus(drive, u.total, u.used, u.free, round(free_pct, 1),
                       health_score(free_pct), status_for(free_pct, alert_percent),
                       days, "filling" if days else trend_state(drive))


def record_snapshot(drive: str, min_interval_s: float = 3600) -> bool:
    """Store free-space history (at most one row per hour per drive)."""
    conn = db.connect()
    last = conn.execute("SELECT ts FROM snapshots WHERE drive=? ORDER BY ts DESC LIMIT 1", (drive,)).fetchone()
    now = time.time()
    if last and now - last["ts"] < min_interval_s:
        return False
    try:
        u = shutil.disk_usage(drive)
    except OSError:
        return False
    conn.execute("INSERT INTO snapshots(ts, drive, total, used, free) VALUES (?,?,?,?,?)",
                 (now, drive, u.total, u.used, u.free))
    conn.commit()
    return True


def forecast_days_to_full(drive: str, window_days: float = 30) -> Optional[float]:
    """Least-squares trend of used space; days until the drive is full at that rate."""
    conn = db.connect()
    since = time.time() - window_days * 86400
    rows = conn.execute("SELECT ts, used, total FROM snapshots WHERE drive=? AND ts>=? ORDER BY ts",
                        (drive, since)).fetchall()
    if len(rows) < 3 or rows[-1]["ts"] - rows[0]["ts"] < 86400:
        return None
    xs = [(r["ts"] - rows[0]["ts"]) / 86400 for r in rows]
    ys = [r["used"] for r in rows]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx  # bytes per day
    if slope <= 0:
        return None
    free_now = rows[-1]["total"] - rows[-1]["used"]
    return round(free_now / slope, 1)


def trend_state(drive: str) -> str:
    rows = db.connect().execute("SELECT MIN(ts) AS a, MAX(ts) AS b, COUNT(*) AS n FROM snapshots WHERE drive=?",
                                (drive,)).fetchone()
    if not rows or rows["n"] < 3 or (rows["b"] - rows["a"]) < 86400:
        return "learning"
    return "stable"


def save_scan(res: ScanResult, keep_dirs: int = 500) -> int:
    conn = db.connect()
    cur = conn.execute("INSERT INTO scans(ts, root, total_size, file_count) VALUES (?,?,?,?)",
                       (time.time(), str(res.root), res.total_size, res.file_count))
    scan_id = cur.lastrowid
    conn.executemany("INSERT INTO scan_dirs(scan_id, path, size) VALUES (?,?,?)",
                     [(scan_id, p, s) for p, s in res.top_dirs(keep_dirs, min_depth=1)])
    conn.commit()
    return scan_id


def growth(root: str, n: int = 15) -> List[Dict]:
    """What grew between the last two scans of this folder."""
    conn = db.connect()
    scans = conn.execute("SELECT id, ts FROM scans WHERE root=? ORDER BY ts DESC LIMIT 2", (root,)).fetchall()
    if len(scans) < 2:
        return []
    new_id, old_id = scans[0]["id"], scans[1]["id"]
    old = {r["path"]: r["size"] for r in conn.execute("SELECT path, size FROM scan_dirs WHERE scan_id=?", (old_id,))}
    new = {r["path"]: r["size"] for r in conn.execute("SELECT path, size FROM scan_dirs WHERE scan_id=?", (new_id,))}
    rows = []
    for path in set(old) | set(new):
        delta = new.get(path, 0) - old.get(path, 0)
        if delta:
            rows.append({"path": path, "before": old.get(path, 0), "after": new.get(path, 0), "delta": delta})
    # report the deepest folder that explains the change, not every ancestor
    rows.sort(key=lambda r: r["delta"], reverse=True)
    return rows[:n]
