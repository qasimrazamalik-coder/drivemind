"""DriveMind as an MCP server, so AI agents (Claude Code, Claude Desktop, Codex, Cursor)
can look after your drive with the same safety rules as the app.

    claude mcp add drivemind -- python -m drivemind mcp

Safety: agents can read anything and PROPOSE plans, but they cannot approve changes.
`apply_plan` only runs actions your Yes / Ask / No settings already allow (or that you
approved in the dashboard or on your phone). Every change is journaled and undoable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

try:  # MCP SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # MCP SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore

INSTRUCTIONS = (
    "DriveMind organizes files, cleans caches and temp junk, and watches disk space on the user's Windows PC. "
    "Read freely. To change anything: create a plan (plan_*), show the user its summary, and call apply_plan. "
    "apply_plan never approves 'ask' actions — the user approves those in the DriveMind dashboard or phone app."
)

mcp = _Server("drivemind", instructions=INSTRUCTIONS)


def _summary(plan) -> Dict:
    return {"plan_id": plan.id, "title": plan.title, "summary": plan.summary(), "notes": plan.notes,
            "actions": [{"id": a.id, "op": a.op.value, "src": a.src, "dst": a.dst, "size": a.size,
                         "reason": a.reason, "decision": a.decision.value, "status": a.status.value}
                        for a in plan.actions[:100]]}


@mcp.tool()
def drive_status() -> List[Dict]:
    """Free space, health score (0-100) and days-until-full for every drive."""
    from .config import Settings
    from .disk import drive_status as ds, list_drives
    s = Settings.load()
    return [x.to_dict() for x in (ds(d, s.low_space_percent) for d in list_drives()) if x]


@mcp.tool()
def scan_folder(path: str, top: int = 15) -> Dict:
    """What is taking space under a folder: biggest subfolders, largest files, file types, age breakdown."""
    from .scanner import scan
    r = scan(Path(path), top_n=top)
    return {"root": str(r.root), "total_size": r.total_size, "file_count": r.file_count,
            "biggest_folders": [{"path": p, "size": s} for p, s in r.top_children(top)],
            "largest_files": [{"path": str(f.path), "size": f.size} for f in r.largest_files[:top]],
            "categories": {k: {"count": v[0], "size": v[1]} for k, v in r.categories.items()},
            "ages": {k: {"count": v[0], "size": v[1]} for k, v in r.age_buckets.items()},
            "stale_large": [{"path": str(f.path), "size": f.size} for f in r.stale_large[:10]]}


@mcp.tool()
def search_files(query: str, limit: int = 15) -> List[Dict]:
    """Find files by content, name, type and date, e.g. 'dubai invoice march' or 'contract pdf 2026'."""
    from .search import search
    return search(query, limit)


@mcp.tool()
def where_is_file(name: str) -> List[Dict]:
    """Where did DriveMind move a file? Searches the journal of every move."""
    from .executor import where_is
    return where_is(name)


@mcp.tool()
def explain_folder(path: str) -> Dict:
    """Which app made a folder, what it holds, and whether it is safe to delete."""
    from .explain import explain
    return explain(Path(path))


@mcp.tool()
def cache_report() -> List[Dict]:
    """Every cache DriveMind knows, its size, and the user's Yes/Ask/No choice for it."""
    from .cleaner import cache_report as cr
    from .config import Settings
    return cr(Settings.load())


@mcp.tool()
def plan_cleanup(kind: str, roots: Optional[List[str]] = None) -> Dict:
    """Create (not apply) a cleanup plan. kind: caches | temp | dev | duplicates | archive."""
    from .config import Settings
    from .paths import user_folders
    s = Settings.load()
    rs = [Path(r) for r in roots] if roots else None
    uf = user_folders()
    default_projects = [p for p in (uf["Desktop"], uf["Documents"], Path.home() / "Projects", Path.home() / "source") if p.exists()]
    if kind == "caches":
        from .cleaner import plan_cache_clean
        p = plan_cache_clean(s)
    elif kind == "temp":
        from .cleaner import plan_temp_clean
        p = plan_temp_clean(s, roots=rs)
    elif kind == "dev":
        from .devjunk import plan_dev_junk
        p = plan_dev_junk(s, rs or default_projects)
    elif kind == "duplicates":
        from .duplicates import plan_duplicates
        p = plan_duplicates(s, rs or [x for x in uf.values() if x.exists()])
    elif kind == "archive":
        from .archiver import plan_archive
        p = plan_archive(s, rs or default_projects)
    else:
        raise ValueError("kind must be caches, temp, dev, duplicates or archive")
    p.save()
    return _summary(p)


@mcp.tool()
def plan_organize(source: str, root: str, preset: str = "developer") -> Dict:
    """Create (not apply) a plan to organize a folder (e.g. Desktop) into root. Presets: developer, student,
    freelancer, by_type, minimal, johnny_decimal."""
    from .config import Settings
    from .planner import plan_organize as po
    p = po(Path(source), Path(root), Settings.load(), preset=preset)
    p.save()
    return _summary(p)


@mcp.tool()
def get_plan(plan_id: str) -> Dict:
    """Show a plan and the status of each action."""
    from .plan import Plan
    p = Plan.load(plan_id)
    if not p:
        raise ValueError("no such plan")
    return _summary(p)


@mcp.tool()
def apply_plan(plan_id: str) -> Dict:
    """Run the actions the user's settings already allow (Yes) or the user approved. Never approves anything."""
    from .config import Settings
    from .executor import apply_plan as ap
    from .plan import Plan
    p = Plan.load(plan_id)
    if not p:
        raise ValueError("no such plan")
    r = ap(p, Settings.load())
    waiting = p.summary()["waiting"]
    r["still_waiting_for_user"] = waiting
    if waiting:
        r["note"] = f"{waiting} action(s) need the user's approval in the DriveMind dashboard or phone app."
    return r


@mcp.tool()
def undo_plan(plan_id: str) -> Dict:
    """Undo everything a plan changed (cache deletions cannot come back)."""
    from .executor import undo_plan as up
    from .plan import Plan
    p = Plan.load(plan_id)
    if not p:
        raise ValueError("no such plan")
    return up(p)


@mcp.tool()
def ask_drivemind(question: str) -> Dict:
    """Ask DriveMind's assistant a question about the user's drive or files (answers from local data)."""
    from .chat import answer
    return answer(question)


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
