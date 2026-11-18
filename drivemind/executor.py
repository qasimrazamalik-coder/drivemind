"""Executor: applies approved actions, journals every change, and undoes plans.

Guarantees:
- only runnable actions (decision YES, or approved by the user) are executed;
- protected paths are re-checked at execution time;
- deletes go to the quarantine (reversible) unless the user set skip_quarantine = yes;
- every completed step is written to the journal before the next one starts,
  so "Undo" and "Where did my file go?" always work, even after a crash.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from . import db, learner
from .config import Decision, Settings, data_dir
from .paths import is_protected, long_path, unique_destination
from .plan import Action, Op, Plan, Status


def quarantine_dir() -> Path:
    q = data_dir() / "quarantine"
    q.mkdir(parents=True, exist_ok=True)
    return q


def _journal(plan_id: str, op: str, src: str, dst: Optional[str], size: int, reason: str) -> None:
    conn = db.connect()
    conn.execute("INSERT INTO journal(ts, plan_id, op, src, dst, size, reason) VALUES (?,?,?,?,?,?,?)",
                 (time.time(), plan_id, op, src, dst, size, reason))
    conn.commit()


def _move(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst = unique_destination(dst)
    shutil.move(long_path(src), long_path(dst))
    return dst


def _has_room(dst: Path, size: int) -> bool:
    probe = dst
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free > size + 50 * 1024 * 1024
    except OSError:
        return True


def apply_plan(plan: Plan, settings: Settings, only_ids: Optional[List[str]] = None) -> Dict:
    done = failed = 0
    freed = 0
    for a in plan.actions:
        if only_ids and a.id not in only_ids:
            continue
        if not a.runnable:
            continue
        try:
            _apply_one(plan, a, settings)
            a.status, a.error = Status.DONE, None
            done += 1
            if a.op in (Op.QUARANTINE, Op.DELETE_CACHE):
                freed += a.size
        except Exception as e:  # file in use, permission denied, disk full ...
            a.status, a.error = Status.FAILED, f"{type(e).__name__}: {e}"
            failed += 1
    if done:
        plan.status = "applied"
    plan.save()
    return {"done": done, "failed": failed, "freed_bytes": freed}


def _apply_one(plan: Plan, a: Action, settings: Settings) -> None:
    if a.op == Op.DELETE_CACHE:
        _clear_cache(plan, a)
        return
    src = Path(a.src)
    if is_protected(src, settings.exclusions):
        raise PermissionError("protected location")
    if a.op == Op.RELOCATE_FOLDER:
        _relocate(plan, a)
        return
    if a.op == Op.ARCHIVE:
        from .archiver import zip_project
        if not src.is_dir():
            raise FileNotFoundError(a.src)
        dst = unique_destination(Path(a.dst))
        if not _has_room(dst, a.size):
            raise OSError("not enough free space for the archive")
        zip_project(src, dst)
        a.dst = str(dst)
        _journal(plan.id, "archive", a.src, str(dst), a.size, a.reason)
        qdst = _move(src, quarantine_dir() / plan.id / _flatten(src))
        _journal(plan.id, "quarantine", a.src, str(qdst), a.size, "original kept after archiving")
        return
    if a.op == Op.MOVE:
        if not src.exists():
            raise FileNotFoundError(a.src)
        dst = Path(a.dst)
        if is_protected(dst, settings.exclusions):
            raise PermissionError("destination is protected")
        if not _has_room(dst, a.size):
            raise OSError("not enough free space at the destination")
        final = _move(src, dst)
        a.dst = str(final)
        _journal(plan.id, "move", a.src, a.dst, a.size, a.reason)
        if settings.decision("learn_from_choices") != Decision.NO and plan.kind == "organize":
            learner.record(src.name, a.category, str(final.parent), True)
    elif a.op == Op.QUARANTINE:
        if not src.exists():
            raise FileNotFoundError(a.src)
        if settings.decision("skip_quarantine") == Decision.YES:
            if src.is_dir():
                shutil.rmtree(long_path(src))
            else:
                os.remove(long_path(src))
            _journal(plan.id, "delete", a.src, None, a.size, a.reason)
            return
        qdst = quarantine_dir() / plan.id / _flatten(src)
        final = _move(src, qdst)
        a.dst = str(final)
        _journal(plan.id, "quarantine", a.src, a.dst, a.size, a.reason)


def _clear_cache(plan: Plan, a: Action) -> None:
    """Caches and build outputs regenerate themselves, so they are removed directly —
    but only paths on the cache catalog or real dev-junk folders are ever accepted."""
    from .cleaner import is_known_cache_path
    from .devjunk import is_dev_junk_path
    if a.src.startswith("cmd:"):
        import shlex
        import subprocess
        cmd = a.src[4:]
        from .cleaner import CATALOG
        allowed = {" ".join(c.command) for c in CATALOG if c.command}
        if cmd not in allowed:
            raise PermissionError("command is not on the cache catalog")
        args = cmd.split(" ") if sys.platform == "win32" else shlex.split(cmd)
        r = subprocess.run(args, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip()[:200] or f"exit code {r.returncode}")
        _journal(plan.id, "delete_cache", a.src, None, 0, a.reason)
        return
    src = Path(a.src)
    if not (is_known_cache_path(src) or is_dev_junk_path(src)):
        raise PermissionError("not a known cache or build folder")
    if is_dev_junk_path(src):
        a.size = _tree_size(src)
        shutil.rmtree(long_path(src), ignore_errors=True)
    else:
        from .cleaner import entry_for_path
        entry = entry_for_path(src)
        a.size = _remove_contents(src, min_age_s=(entry.min_age_days if entry else 1) * 86400)
    _journal(plan.id, "delete_cache", a.src, None, a.size, a.reason)


def _tree_size(p: Path) -> int:
    total = 0
    for dirpath, _, files in os.walk(p):
        for n in files:
            try:
                total += os.lstat(os.path.join(dirpath, n)).st_size
            except OSError:
                pass
    return total


def _relocate(plan: Plan, a: Action) -> None:
    """Move a user folder's contents to the new place, then re-point the Known Folder."""
    from .winapi import set_known_folder
    src, dst = Path(a.src), Path(a.dst)
    if not _has_room(dst, a.size):
        raise OSError("not enough free space at the destination")
    dst.mkdir(parents=True, exist_ok=True)
    for child in list(src.iterdir()):
        if child.name.lower() == "desktop.ini":
            continue
        final = _move(child, dst / child.name)
        _journal(plan.id, "move", str(child), str(final), 0, f"part of moving {a.category}")
    if set_known_folder(a.category, str(dst)):
        _journal(plan.id, "known_folder", str(src), str(dst), 0, a.category)


def _flatten(src: Path) -> str:
    drive = src.drive.replace(":", "") or "root"
    rest = [p for p in src.parts[1:]]
    return str(Path(drive, *rest)) if rest else drive


def _remove_contents(path: Path, min_age_s: float = 0) -> int:
    """Delete what is inside a cache folder (or a single cache file).
    Skips locked files, files newer than min_age_s, and DriveMind's own data."""
    freed = 0
    cutoff = time.time() - min_age_s
    own = os.path.normcase(str(data_dir()))
    if path.is_file():
        try:
            size = path.stat().st_size
            path.unlink()
            return size
        except OSError:
            return 0
    if not path.is_dir():
        return 0
    for dirpath, dirnames, filenames in os.walk(path, topdown=False):
        if os.path.normcase(dirpath).startswith(own):
            continue
        for n in filenames:
            fp = os.path.join(dirpath, n)
            try:
                st = os.lstat(fp)
                if min_age_s and max(st.st_mtime, st.st_atime) > cutoff:
                    continue  # recently used: an app may still need it
                os.remove(long_path(Path(fp)))
                freed += st.st_size
            except OSError:
                pass  # in use: skip, never force
        for d in dirnames:
            try:
                os.rmdir(long_path(Path(dirpath, d)))
            except OSError:
                pass
    return freed


def undo_plan(plan: Plan) -> Dict:
    """Reverse every journaled step of a plan, newest first."""
    conn = db.connect()
    rows = conn.execute("SELECT * FROM journal WHERE plan_id=? AND undone=0 ORDER BY id DESC", (plan.id,)).fetchall()
    restored = skipped = 0
    for r in rows:
        if r["op"] == "archive":
            try:
                Path(r["dst"]).unlink()  # the folder comes back from quarantine in the next step
            except OSError:
                pass
            conn.execute("UPDATE journal SET undone=1 WHERE id=?", (r["id"],))
            continue
        if r["op"] == "known_folder":
            from .winapi import set_known_folder
            set_known_folder(r["reason"], r["src"])
            conn.execute("UPDATE journal SET undone=1 WHERE id=?", (r["id"],))
            restored += 1
            continue
        if r["op"] in ("move", "quarantine") and r["dst"] and Path(r["dst"]).exists():
            back = _move(Path(r["dst"]), Path(r["src"]))
            conn.execute("UPDATE journal SET undone=1 WHERE id=?", (r["id"],))
            restored += 1
            if r["op"] == "move" and plan.kind == "organize":
                learner.record(Path(r["src"]).name, "", str(Path(r["dst"]).parent), False)
            del back
        else:
            skipped += 1  # cache deletes and permanent deletes cannot come back
    conn.commit()
    for a in plan.actions:
        if a.status == Status.DONE and a.op != Op.DELETE_CACHE:
            a.status = Status.UNDONE
    plan.status = "undone"
    plan.save()
    _remove_empty_dirs(plan)
    return {"restored": restored, "not_reversible": skipped}


def _remove_empty_dirs(plan: Plan) -> None:
    for a in plan.actions:
        if a.dst:
            parent = Path(a.dst).parent
            for _ in range(4):
                try:
                    parent.rmdir()  # only succeeds when empty
                except OSError:
                    break
                parent = parent.parent


def where_is(query: str, limit: int = 20) -> List[Dict]:
    """'Where did my file go?' — search the journal by file name or path."""
    like = f"%{query}%"
    rows = db.connect().execute(
        "SELECT ts, plan_id, op, src, dst, size, reason, undone FROM journal "
        "WHERE src LIKE ? OR dst LIKE ? ORDER BY ts DESC LIMIT ?", (like, like, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["exists_now"] = bool(r["dst"]) and Path(r["dst"]).exists()
        out.append(d)
    return out


def restore_entry(journal_id: int) -> Optional[str]:
    """Move one journaled file back to where it came from."""
    conn = db.connect()
    r = conn.execute("SELECT * FROM journal WHERE id=?", (journal_id,)).fetchone()
    if not r or not r["dst"] or not Path(r["dst"]).exists():
        return None
    back = _move(Path(r["dst"]), Path(r["src"]))
    conn.execute("UPDATE journal SET undone=1 WHERE id=?", (journal_id,))
    conn.commit()
    return str(back)


def purge_quarantine(days: int) -> Dict:
    """Quarantined items older than `days` go to the Recycle Bin (Windows) or are deleted."""
    from .winapi import send_to_recycle_bin
    cutoff = time.time() - days * 86400
    purged = 0
    freed = 0
    for plan_dir in quarantine_dir().iterdir():
        try:
            if plan_dir.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue
        size = sum(f.stat().st_size for f in plan_dir.rglob("*") if f.is_file())
        if not send_to_recycle_bin(str(plan_dir)):
            shutil.rmtree(plan_dir, ignore_errors=True)
        purged += 1
        freed += size
    return {"purged_batches": purged, "freed_bytes": freed}
