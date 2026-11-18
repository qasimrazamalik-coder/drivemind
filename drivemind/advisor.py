"""Advisor: the plain-language weekly report — the top fixes and the space each one frees."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .cleaner import cache_report
from .config import Settings
from .devjunk import find_dev_junk
from .disk import drive_status, system_drive
from .paths import user_folders
from .scanner import human


def advise(settings: Settings, project_roots: Optional[List[Path]] = None, limit: int = 3) -> Dict:
    tips: List[Dict] = []
    sysd = system_drive()
    st = drive_status(sysd, settings.low_space_percent)

    caches = [c for c in cache_report(settings) if not c["display_only"] and c["size"] > 0]
    cache_total = sum(c["size"] for c in caches)
    if cache_total > 200 * 1024 ** 2:
        biggest = max(caches, key=lambda c: c["size"])
        tips.append({"id": "caches", "frees": cache_total, "action": "clean_caches",
                     "title": f"Clear caches: {human(cache_total)}",
                     "detail": f"Largest is {biggest['name']} ({human(biggest['size'])})."})

    folders = user_folders()
    roots = project_roots or [p for p in (folders["Desktop"], folders["Documents"], Path.home() / "Projects",
                                          Path.home() / "source", Path.home() / "repos") if p.exists()]
    junk = find_dev_junk(roots, settings.stale_project_days)
    junk_total = sum(j["size"] for j in junk)
    if junk_total > 100 * 1024 ** 2:
        n_proj = len({j["project"] for j in junk})
        tips.append({"id": "devjunk", "frees": junk_total, "action": "clean_dev_junk",
                     "title": f"Remove old project dependencies: {human(junk_total)}",
                     "detail": f"node_modules / .venv / build folders in {n_proj} projects idle for "
                               f"{settings.stale_project_days}+ days. Each can be restored with one command."})

    if st and sysd.upper().startswith("C"):
        on_c = []
        from .cleaner import path_size
        for name in ("Desktop", "Downloads", "Videos", "Pictures"):
            p = folders.get(name)
            if p and p.exists() and str(p).upper().startswith("C"):
                on_c.append((name, path_size(p)))
        movable = sum(s for _, s in on_c)
        if movable > 1024 ** 3 and any(Path(f"{d}:\\").exists() for d in "DEF"):
            tips.append({"id": "folders", "frees": movable, "action": "move_user_folders",
                         "title": f"Move user folders to another drive: {human(movable)} off C:",
                         "detail": ", ".join(f"{n} {human(s)}" for n, s in on_c)})

    tips.sort(key=lambda t: t["frees"], reverse=True)
    return {
        "drive": st.to_dict() if st else None,
        "tips": tips[:limit],
        "total_possible": sum(t["frees"] for t in tips),
    }
