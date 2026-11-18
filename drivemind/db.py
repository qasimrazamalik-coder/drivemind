"""SQLite storage: drive snapshots (growth + forecast), scans, and the action journal."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from .config import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    drive TEXT NOT NULL,
    total INTEGER NOT NULL,
    used INTEGER NOT NULL,
    free INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_snap_drive_ts ON snapshots(drive, ts);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    root TEXT NOT NULL,
    total_size INTEGER NOT NULL,
    file_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_dirs (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    size INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_scan_dirs ON scan_dirs(scan_id, path);

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,          -- proposed | applied | undone | discarded
    json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    plan_id TEXT,
    op TEXT NOT NULL,              -- move | rename | quarantine | mkdir | delete
    src TEXT,
    dst TEXT,
    size INTEGER DEFAULT 0,
    reason TEXT,
    undone INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_journal_src ON journal(src);
CREATE INDEX IF NOT EXISTS ix_journal_dst ON journal(dst);

CREATE TABLE IF NOT EXISTS notices (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    level TEXT NOT NULL,           -- info | watch | critical
    title TEXT NOT NULL,
    body TEXT,
    plan_id TEXT,
    read INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    ext TEXT,
    name TEXT,
    category TEXT,
    destination TEXT,
    accepted INTEGER NOT NULL
);
"""

_local = threading.local()


def db_path() -> Path:
    return data_dir() / "drivemind.db"


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    """One connection per thread (FastAPI runs handlers in a thread pool)."""
    target = str(path or db_path())
    cache = getattr(_local, "conns", None)
    if cache is None:
        cache = _local.conns = {}
    conn = cache.get(target)
    if conn is None:
        conn = sqlite3.connect(target, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        cache[target] = conn
    return conn


def close_all() -> None:
    cache = getattr(_local, "conns", {}) or {}
    for c in cache.values():
        c.close()
    cache.clear()
