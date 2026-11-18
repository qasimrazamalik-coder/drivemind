"""Dev-aware cleaner: regenerable folders in projects you have not touched for a while.

Every item carries the one command that brings it back (npm i, pip install ...).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from .paths import looks_like_project

# name -> (kind, marker files that confirm it is regenerable, restore command)
JUNK: Dict[str, tuple] = {
    "node_modules": ("deps", {"package.json"}, "npm install"),
    ".venv": ("deps", {"pyproject.toml", "requirements.txt", "setup.py"}, "python -m venv .venv && pip install -r requirements.txt"),
    "venv": ("deps", {"pyproject.toml", "requirements.txt", "setup.py"}, "python -m venv venv && pip install -r requirements.txt"),
    "__pycache__": ("build", set(), "created automatically"),
    ".pytest_cache": ("build", set(), "created automatically"),
    "dist": ("build", {"package.json", "pyproject.toml", "setup.py"}, "rebuild with your build command"),
    "build": ("build", {"package.json", "pyproject.toml", "setup.py", "build.gradle", "build.gradle.kts", "CMakeLists.txt"}, "rebuild with your build command"),
    ".next": ("build", {"package.json"}, "npm run build"),
    ".nuxt": ("build", {"package.json"}, "npm run build"),
    ".turbo": ("build", {"package.json"}, "created automatically"),
    ".parcel-cache": ("build", {"package.json"}, "created automatically"),
    ".expo": ("build", {"app.json", "package.json"}, "created automatically by Expo"),
    ".gradle": ("build", {"build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}, "gradle build"),
    "target": ("build", {"Cargo.toml", "pom.xml"}, "cargo build / mvn package"),
    "bin": ("build", {"*.csproj"}, "dotnet build"),
    "obj": ("build", {"*.csproj"}, "dotnet build"),
}
DEV_JUNK_NAMES: Set[str] = set(JUNK)
SOURCE_SKIP = DEV_JUNK_NAMES | {".git", ".idea", ".vscode"}


def _has_marker(project: Path, markers: Set[str]) -> bool:
    if not markers:
        return True
    try:
        names = os.listdir(project)
    except OSError:
        return False
    for m in markers:
        if m.startswith("*"):
            if any(n.endswith(m[1:]) for n in names):
                return True
        elif m in names:
            return True
    return False


def last_activity(project: Path, cap: int = 20000) -> float:
    """Newest modification time of the project's own files (ignoring regenerable folders)."""
    newest, seen = 0.0, 0
    for dirpath, dirnames, filenames in os.walk(project):
        dirnames[:] = [d for d in dirnames if d not in SOURCE_SKIP]
        for n in filenames:
            try:
                newest = max(newest, os.lstat(os.path.join(dirpath, n)).st_mtime)
            except OSError:
                pass
            seen += 1
            if seen >= cap:
                return newest
    return newest


def _size(p: Path) -> int:
    total = 0
    for dirpath, _, files in os.walk(p):
        for n in files:
            try:
                total += os.lstat(os.path.join(dirpath, n)).st_size
            except OSError:
                pass
    return total


def find_projects(roots: Iterable[Path], max_depth: int = 4) -> List[Path]:
    found: List[Path] = []
    for root in roots:
        root = Path(root)
        stack = [(root, 0)]
        while stack:
            d, depth = stack.pop()
            if looks_like_project(d):
                found.append(d)
                continue  # a project's subfolders are part of it
            if depth >= max_depth:
                continue
            try:
                with os.scandir(d) as it:
                    for e in it:
                        if e.is_dir(follow_symlinks=False) and e.name not in SOURCE_SKIP and not e.name.startswith("."):
                            stack.append((Path(e.path), depth + 1))
            except OSError:
                pass
    return found


def find_dev_junk(roots: Iterable[Path], stale_days: float = 60, kinds: Optional[Set[str]] = None,
                  now: Optional[float] = None) -> List[Dict]:
    now = now or time.time()
    out: List[Dict] = []
    for project in find_projects(roots):
        idle = (now - last_activity(project)) / 86400
        if idle < stale_days:
            continue
        for name, (kind, markers, restore) in JUNK.items():
            if kinds and kind not in kinds:
                continue
            p = project / name
            if p.is_dir() and not p.is_symlink() and _has_marker(project, markers):
                size = _size(p)
                if size:
                    out.append({"project": str(project), "path": str(p), "name": name, "kind": kind,
                                "size": size, "idle_days": round(idle, 1), "restore": restore})
    out.sort(key=lambda r: r["size"], reverse=True)
    return out


def plan_dev_junk(settings, roots: Iterable[Path]):
    """Plan removal of regenerable dependency and build folders in stale projects."""
    from .plan import Op, Plan
    from .planner import build_action
    plan = Plan(title="Clean old project dependencies and builds", kind="devjunk")
    for j in find_dev_junk(roots, settings.stale_project_days):
        # dependencies regenerate exactly; build outputs might hold hand-made files -> quarantine (undoable)
        op = Op.DELETE_CACHE if j["kind"] == "deps" or j["name"] in ("__pycache__", ".pytest_cache") else Op.QUARANTINE
        plan.actions.append(build_action(
            settings, op, Path(j["path"]), None, j["size"], j["name"],
            f"'{Path(j['project']).name}' untouched {j['idle_days']:.0f} days — restore with: {j['restore']}",
            0.95, "clean_dev_junk"))
    return plan


def is_dev_junk_path(path: Path) -> bool:
    """Executor whitelist: a known regenerable folder directly inside a real project."""
    path = Path(path)
    if path.name not in JUNK:
        return False
    _, markers, _ = JUNK[path.name]
    return looks_like_project(path.parent) and _has_marker(path.parent, markers)
