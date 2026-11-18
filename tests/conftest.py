import os
import sys
import time
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own DriveMind data folder and a fake home directory."""
    home = tmp_path / "home"
    for d in ("Desktop", "Downloads", "Documents", "Pictures", "Videos", "Music"):
        (home / d).mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("DRIVEMIND_HOME", str(tmp_path / "dmdata"))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    monkeypatch.setenv("DRIVEMIND_TESTING", "1")
    (tmp_path / "tmpdir").mkdir()
    # Windows cache locations point into the fake home too
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("TEMP", str(tmp_path / "tmpdir"))
    monkeypatch.setenv("TMP", str(tmp_path / "tmpdir"))
    # C:\Windows and C:\ProgramData hold real temp files and crash reports on a Windows
    # runner. Point DriveMind's lookups at the sandbox; the process env keeps the real
    # SystemRoot, which Python itself needs on Windows.
    from drivemind import cleaner
    real_env_map = cleaner.env_map

    def sandboxed_env_map(env=None, home=None):
        m = real_env_map(env, home)
        m["SYSTEMROOT"] = str(tmp_path / "Windows")
        m["PROGRAMDATA"] = str(tmp_path / "ProgramData")
        return m
    monkeypatch.setattr(cleaner, "env_map", sandboxed_env_map)
    from drivemind import db
    db.close_all()
    yield home
    db.close_all()


def make(path: Path, content: bytes = b"x", age_days: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if age_days:
        t = time.time() - age_days * 86400
        os.utime(path, (t, t))
    return path


WIN = sys.platform == "win32"


def cache_dir(home: Path, which: str) -> Path:
    """Where a cache lives on this OS inside the fake home."""
    local = home / "AppData" / "Local"
    return {
        "pip": local / "pip" / "Cache" if WIN else home / ".cache" / "pip",
        "npm": local / "npm-cache" if WIN else home / ".npm" / "_cacache",
    }[which]
