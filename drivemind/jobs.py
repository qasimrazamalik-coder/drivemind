"""Tiny background job runner so long scans never block the dashboard."""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="drivemind-job")
_jobs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def submit(kind: str, fn: Callable[..., Any], *args, **kwargs) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {"id": job_id, "kind": kind, "status": "running", "started": time.time(),
                         "result": None, "error": None, "progress": 0}

    def run():
        try:
            res = fn(*args, **kwargs)
            with _lock:
                _jobs[job_id].update(status="done", result=res, finished=time.time())
        except Exception as e:
            with _lock:
                _jobs[job_id].update(status="error", error=f"{type(e).__name__}: {e}",
                                     trace=traceback.format_exc()[-1500:], finished=time.time())

    _pool.submit(run)
    return job_id


def get(job_id: str) -> Dict[str, Any]:
    with _lock:
        return dict(_jobs.get(job_id, {"id": job_id, "status": "missing"}))


def progress(job_id: str, value: int) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["progress"] = value
