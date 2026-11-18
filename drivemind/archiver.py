"""Git-safe project archiver: zips projects you have not touched for months.

- The zip holds the whole project, including .git, so no history is lost.
  Only regenerable folders (node_modules, .venv, build ...) are left out.
- Projects with uncommitted changes, stashes or commits that were never pushed are
  never archived automatically: they always wait for you, with the reason shown.
- The original folder goes to the quarantine, so Undo puts it back exactly.
"""

from __future__ import annotations

import os
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .config import Decision, Settings
from .devjunk import DEV_JUNK_NAMES, find_projects, is_dev_junk_path, last_activity
from .plan import Action, Op, Plan, Status


SKIP_IN_ZIP = {"node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".gradle", ".turbo",
               ".parcel-cache", ".next", ".nuxt", ".expo"}


def _git(project: Path, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def git_state(project: Path) -> Dict:
    """Is it safe to put this project away? Reads git without changing anything."""
    if not (project / ".git").exists():
        return {"git": False, "safe": True, "warnings": []}
    warnings: List[str] = []
    status = _git(project, "status", "--porcelain")
    if status is None:
        return {"git": True, "safe": False, "warnings": ["git could not read this repository"]}
    if status:
        warnings.append(f"{len(status.splitlines())} uncommitted change(s)")
    stash = _git(project, "stash", "list")
    if stash:
        warnings.append(f"{len(stash.splitlines())} stash(es)")
    has_commits = _git(project, "rev-parse", "HEAD") is not None
    upstream = _git(project, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if has_commits and upstream is None:
        remotes = _git(project, "remote")
        warnings.append("never pushed (no remote)" if not remotes else "branch has no upstream — may not be pushed")
    elif upstream:
        ahead = _git(project, "rev-list", "--count", "@{u}..HEAD")
        if ahead and ahead != "0":
            warnings.append(f"{ahead} commit(s) not pushed")
    return {"git": True, "safe": not warnings, "warnings": warnings}


def find_inactive(roots: Iterable[Path], idle_days: float, now: Optional[float] = None) -> List[Dict]:
    now = now or time.time()
    out = []
    for p in find_projects(roots):
        last = last_activity(p)
        if not last:
            continue
        idle = (now - last) / 86400
        if idle >= idle_days:
            size = _source_size(p)
            out.append({"path": str(p), "name": p.name, "idle_days": round(idle), "size": size, **git_state(p)})
    out.sort(key=lambda r: r["idle_days"], reverse=True)
    return out


def _source_size(project: Path) -> int:
    total = 0
    for dirpath, dirnames, files in os.walk(project):
        dirnames[:] = [d for d in dirnames if d not in DEV_JUNK_NAMES]
        for n in files:
            try:
                total += os.lstat(os.path.join(dirpath, n)).st_size
            except OSError:
                pass
    return total


def default_archive_root(settings: Settings) -> Path:
    if settings.organize_root:
        return Path(settings.organize_root) / "Archive" / "Projects"
    return Path.home() / "DriveMind Archive" / "Projects"


def plan_archive(settings: Settings, roots: Iterable[Path], archive_root: Optional[Path] = None,
                 now: Optional[float] = None) -> Plan:
    archive_root = Path(archive_root or default_archive_root(settings))
    plan = Plan(title=f"Archive projects idle {settings.archive_after_days}+ days", kind="archive")
    stamp = time.strftime("%Y-%m-%d")
    for p in find_inactive(roots, settings.archive_after_days, now):
        dst = archive_root / f"{p['name']} ({stamp}).zip"
        base = settings.gate("archive_inactive_projects", 0.95)
        if p["warnings"]:
            # never automatic: the zip keeps everything, but you should know before it goes away
            decision = Decision.NO if base == Decision.NO else Decision.ASK
            reason = f"idle {p['idle_days']} days — careful: {', '.join(p['warnings'])}"
        else:
            decision = base
            reason = f"idle {p['idle_days']} days" + (" — git clean and pushed" if p["git"] else " — not a git repo")
        plan.actions.append(Action(op=Op.ARCHIVE, src=p["path"], dst=str(dst), size=p["size"], category="Archive",
                                   reason=reason + ("; zipped with its full git history" if p["git"] else "; zipped")
                                   + ", original kept in quarantine",
                                   confidence=0.95, option="archive_inactive_projects", decision=decision,
                                   status=Status.SKIPPED if decision == Decision.NO else Status.PENDING))
    return plan


def zip_project(src: Path, dst: Path) -> int:
    """Zip a project (minus regenerable folders) and verify the archive. Returns file count."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".zip.part")
    count = 0
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for dirpath, dirnames, files in os.walk(src):
            # leave out only dependency/cache folders the project's own files prove are regenerable;
            # build/dist/bin may hold hand-made files, so they always go into the zip
            dirnames[:] = [d for d in dirnames
                           if not (d in SKIP_IN_ZIP and is_dev_junk_path(Path(dirpath, d)))]
            for n in files:
                full = Path(dirpath, n)
                if full.is_symlink():
                    continue
                z.write(full, Path(src.name) / full.relative_to(src))
                count += 1
    with zipfile.ZipFile(tmp) as z:
        bad = z.testzip()
        if bad is not None or len(z.infolist()) != count:
            tmp.unlink(missing_ok=True)
            raise OSError(f"archive check failed ({bad or 'file count mismatch'})")
    tmp.replace(dst)
    return count
