"""Live sync: every change on the PC becomes an event the dashboard and the phone see at once.

Clients long-poll `/api/events?since=N` (or `/m/events` from the phone). The call returns as
soon as something newer than N happens, or after `timeout` seconds with no events. Plain
HTTP keeps it working everywhere: browsers, Android without extra libraries, flaky Wi-Fi.

Events are small hints ("plans changed", "status changed"), not data: clients re-fetch what
they show. The log keeps the last few hundred events in memory; a client that fell further
behind gets `reset: true` and simply reloads everything.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional

KINDS = {"status", "plans", "notices", "settings", "scan", "jobs", "devices", "index"}
_MAX = 500
_log: Deque[Dict] = deque(maxlen=_MAX)
_seq = 0
_cond = threading.Condition()
_boot = f"{int(time.time())}"  # changes on restart, so clients know their cursor is stale


def publish(kind: str, **data) -> int:
    """Record an event and wake every waiting client. Safe from any thread."""
    global _seq
    with _cond:
        _seq += 1
        _log.append({"seq": _seq, "ts": time.time(), "kind": kind, **data})
        _cond.notify_all()
        return _seq


def current() -> int:
    with _cond:
        return _seq


def since(cursor: int, timeout: float = 25.0, boot: Optional[str] = None) -> Dict:
    """Events after `cursor`, waiting up to `timeout` seconds for the first one."""
    timeout = max(0.0, min(timeout, 55.0))
    deadline = time.time() + timeout
    with _cond:
        if boot is not None and boot != _boot:
            return {"boot": _boot, "seq": _seq, "events": [], "reset": True}
        while _seq <= cursor:
            left = deadline - time.time()
            if left <= 0:
                break
            _cond.wait(left)
        oldest = _log[0]["seq"] if _log else _seq + 1
        reset = cursor < oldest - 1 and cursor < _seq
        items: List[Dict] = [e for e in _log if e["seq"] > cursor]
        return {"boot": _boot, "seq": _seq, "events": items[-100:], "reset": reset}


# Which change a request makes, judged from its path. Used by the API middleware so every
# write is published without touching each handler.
_RULES = [
    ("/plans/", "plans"), ("/plans", "plans"), ("/tidy", "plans"), ("/journal/", "plans"),
    ("/settings", "settings"), ("/notices", "notices"), ("/rules", "settings"),
    ("/startup", "status"), ("/devices", "devices"), ("/pair", "devices"), ("/claim", "devices"),
    ("/search/index", "index"), ("/scan", "scan"), ("/tag-temp", "status"),
]


def kind_for(path: str) -> Optional[str]:
    p = path[2:] if path.startswith("/m/") else path[4:] if path.startswith("/api/") else path
    p = "/" + p.lstrip("/")
    for prefix, kind in _RULES:
        if p.startswith(prefix):
            return kind
    return None
