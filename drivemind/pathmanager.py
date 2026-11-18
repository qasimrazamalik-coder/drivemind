"""Path Manager: move Desktop, Downloads, Documents, Pictures and Videos off drive C:.

On Windows this does what Explorer's Properties > Location > Move does: the files are
moved, then the Known Folder is re-pointed (SHSetKnownFolderPath) so every app follows.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Optional

from .config import Settings
from .paths import user_folders
from .plan import Op, Plan
from .planner import build_action

MOVABLE = ["Desktop", "Downloads", "Documents", "Pictures", "Videos", "Music"]


def folder_report(home: Optional[Path] = None) -> List[Dict]:
    from .cleaner import path_size
    rows = []
    for name, p in user_folders(home).items():
        rows.append({"name": name, "path": str(p), "exists": p.exists(),
                     "size": path_size(p) if p.exists() else 0, "drive": p.anchor or "/"})
    return rows


def plan_relocate(settings: Settings, target_root: Path, names: Optional[List[str]] = None,
                  home: Optional[Path] = None) -> Plan:
    target_root = Path(target_root)
    plan = Plan(title=f"Move user folders to {target_root}", kind="folders")
    folders = user_folders(home)
    for name in names or MOVABLE:
        src = folders.get(name)
        if not src or not src.exists():
            continue
        dst = target_root / name
        if src.resolve() == dst.resolve():
            continue
        from .cleaner import path_size
        size = path_size(src)
        try:
            free = shutil.disk_usage(target_root.anchor or target_root).free
        except OSError:
            free = None
        reason = f"{name} ({src}) moves to {dst}; Windows and apps are pointed to the new place"
        if free is not None and free < size * 1.1:
            plan.notes.append(f"Not enough free space on {target_root.anchor} for {name}.")
            continue
        plan.actions.append(build_action(settings, Op.RELOCATE_FOLDER, src, dst, size, name, reason, 1.0,
                                         "move_user_folders"))
    return plan
