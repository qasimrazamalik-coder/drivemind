"""Duplicate finder: size -> first 64 KB hash -> full hash. Keeps the best copy.

Cloud online-only files are never read (the scanner skips them), so this never
triggers OneDrive downloads.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

from .config import Settings
from .paths import is_protected
from .plan import Op, Plan
from .planner import build_action
from .scanner import FileInfo, iter_files

COPY_MARK = re.compile(r"(\(\d+\)|\bcopy\b|- copy| \d$)", re.I)
MESSY_PARTS = {"downloads", "desktop", "temp", "tmp", "inbox"}


def _hash(path: Path, limit: int = 0) -> str:
    h = hashlib.blake2b(digest_size=20)
    read = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20 if not limit else min(1 << 16, limit - read))
            if not b:
                break
            h.update(b)
            read += len(b)
            if limit and read >= limit:
                break
    return h.hexdigest()


def find_duplicates(roots: Iterable[Path], min_size: int = 1024,
                    skip_names: Iterable[str] = ("node_modules", ".git", ".venv", "venv")) -> List[List[FileInfo]]:
    skip = set(skip_names)
    by_size: Dict[int, List[FileInfo]] = defaultdict(list)
    seen = set()
    for root in roots:
        for f in iter_files(Path(root), skip_dir=lambda p: p.name in skip):
            key = str(f.path).lower()
            if f.size >= min_size and key not in seen:
                seen.add(key)
                by_size[f.size].append(f)
    groups: List[List[FileInfo]] = []
    for size, files in by_size.items():
        if len(files) < 2:
            continue
        by_head: Dict[str, List[FileInfo]] = defaultdict(list)
        for f in files:
            try:
                by_head[_hash(f.path, 1 << 16)].append(f)
            except OSError:
                pass
        for same_head in by_head.values():
            if len(same_head) < 2:
                continue
            if size <= 1 << 16:
                groups.append(same_head)
                continue
            by_full: Dict[str, List[FileInfo]] = defaultdict(list)
            for f in same_head:
                try:
                    by_full[_hash(f.path)].append(f)
                except OSError:
                    pass
            groups.extend(g for g in by_full.values() if len(g) > 1)
    groups.sort(key=lambda g: g[0].size * (len(g) - 1), reverse=True)
    return groups


def keeper_score(f: FileInfo) -> tuple:
    """Lower is better: organized location, clean name, short path, oldest copy."""
    parts = {p.lower() for p in f.path.parts}
    messy = len(parts & MESSY_PARTS)
    copy = 1 if COPY_MARK.search(f.path.stem) else 0
    return (messy, copy, len(f.path.parts), f.mtime)


def plan_duplicates(settings: Settings, roots: List[Path], min_size: int = 1024) -> Plan:
    plan = Plan(title="Remove duplicate files", kind="duplicates")
    for group in find_duplicates(roots, min_size):
        group = [f for f in group if not is_protected(f.path, settings.exclusions)]
        if len(group) < 2:
            continue
        group.sort(key=keeper_score)
        keep = group[0]
        for f in group[1:]:
            plan.actions.append(build_action(settings, Op.QUARANTINE, f.path, None, f.size, "Duplicates",
                                             f"identical to {keep.path}", 0.99, "delete_duplicates"))
    return plan
