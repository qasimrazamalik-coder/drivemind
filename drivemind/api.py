"""Local API (127.0.0.1 only). The dashboard, CLI, tray and future Explorer menu all use it.

Mutating requests must carry the header `X-DriveMind: 1`: a web page on another site
cannot add custom headers to a cross-origin request without a CORS preflight, which this
server never grants, so random websites cannot drive DriveMind. The Host header is
checked to block DNS-rebinding attacks.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, db, jobs
from .advisor import advise
from .cleaner import cache_report, plan_cache_clean, plan_temp_clean, tag_temporary, temp_report
from .config import OPTION_INFO, Decision, Mode, Settings
from .devjunk import plan_dev_junk
from .disk import drive_status, growth, list_drives, record_snapshot, save_scan, system_drive
from .duplicates import plan_duplicates
from .executor import apply_plan, restore_entry, undo_plan, where_is
from .explain import explain
from .pathmanager import folder_report, plan_relocate
from .paths import user_folders
from .plan import Plan, Status
from .planner import plan_organize
from .rules import Rule, load_rules, parse_rule, save_rules
from .scanner import scan

WEB = Path(__file__).parent / "web"
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}

app = FastAPI(title="DriveMind", version=__version__)
_last_scan: Dict[str, Dict] = {}


@app.middleware("http")
async def local_only(request: Request, call_next):
    host = (request.headers.get("host") or "").split(":")[0]
    testing = os.environ.get("DRIVEMIND_TESTING") == "1" and host == "testserver"
    if host not in ALLOWED_HOSTS and not testing:
        return JSONResponse({"detail": "DriveMind only answers on localhost"}, status_code=403)
    if request.method in ("POST", "PUT", "DELETE") and request.headers.get("x-drivemind") != "1":
        return JSONResponse({"detail": "missing X-DriveMind header"}, status_code=403)
    return await call_next(request)


# ------------------------------------------------------------------ models ---
class ScanReq(BaseModel):
    root: str


class OrganizeReq(BaseModel):
    source: str
    root: str
    preset: str = "developer"
    use_ai: Optional[bool] = None


class RootsReq(BaseModel):
    roots: List[str] = []


class CleanReq(BaseModel):
    only: Optional[List[str]] = None


class FoldersReq(BaseModel):
    target: str
    names: Optional[List[str]] = None


class DecideReq(BaseModel):
    approve: List[str] = []
    reject: List[str] = []


class ApplyReq(BaseModel):
    ids: Optional[List[str]] = None


class ChoiceReq(BaseModel):
    key: str
    value: Decision


class ModeReq(BaseModel):
    mode: Mode


class RuleReq(BaseModel):
    text: str


class PathReq(BaseModel):
    path: str
    days: float = 7


# ------------------------------------------------------------------ status ---
@app.get("/api/status")
def status():
    s = Settings.load()
    drives = []
    for d in list_drives():
        record_snapshot(d)
        st = drive_status(d, s.low_space_percent)
        if st:
            drives.append(st.to_dict())
    unread = db.connect().execute("SELECT COUNT(*) AS n FROM notices WHERE read=0").fetchone()["n"]
    return {"version": __version__, "system_drive": system_drive(), "drives": drives, "unread_notices": unread,
            "user_folders": {k: str(v) for k, v in user_folders().items()}, "mode": s.mode.value}


@app.get("/api/advice")
def advice():
    return advise(Settings.load())


@app.get("/api/folders")
def folders():
    return folder_report()


# -------------------------------------------------------------------- scan ---
def _do_scan(root: str) -> Dict:
    res = scan(Path(root), top_n=40)
    save_scan(res)
    out = {
        "root": str(res.root), "total_size": res.total_size, "file_count": res.file_count,
        "dir_count": res.dir_count, "cloud_skipped": res.cloud_skipped, "errors": res.errors,
        "seconds": round(res.seconds, 2),
        "children": [{"path": p, "size": s} for p, s in res.top_children(20)],
        "top_dirs": [{"path": p, "size": s} for p, s in res.top_dirs(30, min_depth=2)],
        "largest_files": [{"path": str(f.path), "size": f.size, "mtime": f.mtime} for f in res.largest_files[:25]],
        "by_type": [{"ext": e, "size": s} for e, s in list(res.ext_sizes.items())[:15]],
        "growth": growth(str(res.root)),
        "finished": time.time(),
    }
    _last_scan[str(res.root)] = out
    _last_scan["__latest__"] = out
    return out


@app.post("/api/scan")
def start_scan(req: ScanReq):
    if not Path(req.root).exists():
        raise HTTPException(404, "folder not found")
    return {"job": jobs.submit("scan", _do_scan, req.root)}


@app.get("/api/scan/latest")
def latest_scan(root: Optional[str] = None):
    return _last_scan.get(root or "__latest__") or {}


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    return jobs.get(job_id)


# ---------------------------------------------------------------- settings ---
@app.get("/api/settings")
def get_settings():
    s = Settings.load()
    return {"settings": s.model_dump(), "options": OPTION_INFO}


@app.put("/api/settings/mode")
def set_mode(req: ModeReq):
    s = Settings.load()
    s.set_mode(req.mode)
    s.save()
    return s.model_dump()


@app.put("/api/settings/option")
def set_option(req: ChoiceReq):
    s = Settings.load()
    try:
        s.set_option(req.key, req.value)
    except KeyError as e:
        raise HTTPException(400, str(e))
    s.save()
    return s.model_dump()


@app.put("/api/settings/cache")
def set_cache_choice(req: ChoiceReq):
    s = Settings.load()
    s.cache_choices[req.key] = req.value
    s.save()
    return {"ok": True}


@app.put("/api/settings/temp")
def set_temp_choice(req: ChoiceReq):
    s = Settings.load()
    s.temp_choices[req.key] = req.value
    s.save()
    return {"ok": True}


@app.put("/api/settings")
def update_settings(patch: Dict):
    s = Settings.load()
    allowed = {"organize_root", "low_space_percent", "confidence_threshold", "quarantine_days", "temp_zone_days",
               "stale_project_days", "archive_after_days", "exclusions", "ollama_url", "ollama_model"}
    data = s.model_dump()
    for k, v in patch.items():
        if k in allowed:
            data[k] = v
    s = Settings.model_validate(data)
    s.save()
    return s.model_dump()


# ------------------------------------------------------------------- tables ---
@app.get("/api/caches")
def caches():
    return cache_report(Settings.load())


@app.get("/api/temp/rules")
def temp_rules():
    return temp_report(Settings.load())


# ------------------------------------------------------------------- plans ---
def _plan_out(p: Plan) -> Dict:
    d = p.model_dump()
    d["summary"] = p.summary()
    return d


@app.post("/api/plans/organize")
def new_organize(req: OrganizeReq):
    s = Settings.load()
    src = Path(req.source)
    if not src.is_dir():
        raise HTTPException(404, "source folder not found")
    p = plan_organize(src, Path(req.root), s, preset=req.preset, use_ai=req.use_ai)
    p.save()
    return _plan_out(p)


@app.post("/api/plans/clean")
def new_clean(req: CleanReq):
    p = plan_cache_clean(Settings.load(), only=req.only)
    p.save()
    return _plan_out(p)


@app.post("/api/plans/temp")
def new_temp(req: RootsReq):
    p = plan_temp_clean(Settings.load(), roots=[Path(r) for r in req.roots] or None)
    p.save()
    return _plan_out(p)


@app.post("/api/plans/duplicates")
def new_dupes(req: RootsReq):
    roots = [Path(r) for r in req.roots] or [p for p in user_folders().values() if p.exists()]
    p = plan_duplicates(Settings.load(), roots)
    p.save()
    return _plan_out(p)


@app.post("/api/plans/devjunk")
def new_devjunk(req: RootsReq):
    roots = [Path(r) for r in req.roots] or [p for p in (user_folders()["Desktop"], user_folders()["Documents"],
                                                         Path.home() / "Projects") if p.exists()]
    p = plan_dev_junk(Settings.load(), roots)
    p.save()
    return _plan_out(p)


@app.post("/api/plans/folders")
def new_folders(req: FoldersReq):
    p = plan_relocate(Settings.load(), Path(req.target), req.names)
    p.save()
    return _plan_out(p)


@app.get("/api/plans")
def plans():
    return Plan.recent(30)


def _load(plan_id: str) -> Plan:
    p = Plan.load(plan_id)
    if not p:
        raise HTTPException(404, "plan not found")
    return p


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str):
    return _plan_out(_load(plan_id))


@app.post("/api/plans/{plan_id}/decide")
def decide(plan_id: str, req: DecideReq):
    p = _load(plan_id)
    if req.approve:
        p.set_status(req.approve, Status.APPROVED)
    if req.reject:
        p.set_status(req.reject, Status.REJECTED)
        s = Settings.load()
        if s.decision("learn_from_choices") != Decision.NO and p.kind == "organize":
            from .learner import record
            for aid in req.reject:
                a = p.get(aid)
                if a and a.dst:
                    record(Path(a.src).name, a.category, str(Path(a.dst).parent), False)
    p.save()
    return _plan_out(p)


@app.post("/api/plans/{plan_id}/apply")
def apply(plan_id: str, req: ApplyReq):
    p = _load(plan_id)
    result = apply_plan(p, Settings.load(), req.ids)
    return {"result": result, "plan": _plan_out(p)}


@app.post("/api/plans/{plan_id}/undo")
def undo(plan_id: str):
    p = _load(plan_id)
    return {"result": undo_plan(p), "plan": _plan_out(p)}


# ----------------------------------------------------------------- journal ---
@app.get("/api/where")
def where(q: str):
    return where_is(q) if len(q) >= 2 else []


@app.post("/api/journal/{entry_id}/restore")
def restore(entry_id: int):
    back = restore_entry(entry_id)
    if not back:
        raise HTTPException(404, "nothing to restore")
    return {"restored_to": back}


# ------------------------------------------------------------------- rules ---
@app.get("/api/rules")
def rules():
    return [r.model_dump() for r in load_rules()]


@app.post("/api/rules")
def add_rule(req: RuleReq):
    try:
        r = parse_rule(req.text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    rs = load_rules()
    rs.append(r)
    save_rules(rs)
    return r.model_dump()


@app.delete("/api/rules/{index}")
def delete_rule(index: int):
    rs = load_rules()
    if not 0 <= index < len(rs):
        raise HTTPException(404, "no such rule")
    rs.pop(index)
    save_rules(rs)
    return {"ok": True}


# ------------------------------------------------------------------- tools ---
@app.post("/api/explain")
def explain_folder(req: PathReq):
    p = Path(req.path)
    if not p.exists():
        raise HTTPException(404, "folder not found")
    return explain(p)


@app.post("/api/tag-temp")
def tag_temp(req: PathReq):
    p = Path(req.path)
    if not p.exists():
        raise HTTPException(404, "not found")
    return {"expires": tag_temporary(p, req.days)}


@app.get("/api/notices")
def notices():
    rows = db.connect().execute("SELECT * FROM notices ORDER BY ts DESC LIMIT 50").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/notices/read")
def notices_read():
    conn = db.connect()
    conn.execute("UPDATE notices SET read=1 WHERE read=0")
    conn.commit()
    return {"ok": True}


# -------------------------------------------------------------------- web ---
if WEB.exists():
    app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")
