"""Phone pairing: each paired phone gets its own secret token.

Only a SHA-256 hash of each token is stored. The phone talks to the /m API over the
home Wi-Fi with `Authorization: Bearer <token>`; a lost phone is cut off by removing it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import socket
import time
from pathlib import Path
from typing import Dict, List, Optional

from .config import data_dir

DEFAULT_PORT = 7878


def _path() -> Path:
    return data_dir() / "devices.json"


def _load() -> List[Dict]:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(rows: List[Dict]) -> None:
    tmp = _path().with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    tmp.replace(_path())


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def lan_ip() -> str:
    """This PC's address on the local network (no packet is actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def pair(name: str = "Phone", port: int = DEFAULT_PORT) -> Dict:
    token = secrets.token_urlsafe(24)
    dev_id = secrets.token_hex(4)
    rows = _load()
    rows.append({"id": dev_id, "name": name[:40], "hash": _hash(token), "created": time.time(), "last_seen": None})
    _save(rows)
    host = lan_ip()
    url = f"drivemind://pair?host={host}&port={port}&token={token}&id={dev_id}"
    return {"id": dev_id, "host": host, "port": port, "token": token, "url": url,
            "code": f"{host}:{port}#{token}", "qr_svg": qr_svg(url)}


def qr_svg(text: str) -> str:
    try:
        import segno
    except ImportError:
        return ""
    return segno.make(text, error="m").svg_inline(scale=6, dark="#0e1013", light="#ffffff", border=2)


def verify(token: Optional[str]) -> Optional[Dict]:
    if not token:
        return None
    h = _hash(token)
    rows = _load()
    for row in rows:
        if hmac.compare_digest(row["hash"], h):
            if not row.get("last_seen") or time.time() - row["last_seen"] > 60:
                row["last_seen"] = time.time()
                _save(rows)
            return row
    return None


def list_devices() -> List[Dict]:
    return [{k: v for k, v in r.items() if k != "hash"} for r in _load()]


def remove(dev_id: str) -> bool:
    rows = _load()
    keep = [r for r in rows if r["id"] != dev_id]
    _save(keep)
    return len(keep) != len(rows)


def any_paired() -> bool:
    return bool(_load())
