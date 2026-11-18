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


UNCLAIMED_TTL = 15 * 60  # a pairing no phone has used within 15 minutes is dropped


def _drop_unclaimed(rows: List[Dict], all_unclaimed: bool = False) -> List[Dict]:
    now = time.time()
    return [r for r in rows if r.get("last_seen") or (not all_unclaimed and now - r["created"] < UNCLAIMED_TTL)]


def pair(name: str = "Phone", port: int = DEFAULT_PORT) -> Dict:
    """A new pairing replaces any earlier one no phone has used yet, so they never pile up."""
    token = secrets.token_urlsafe(24)
    dev_id = secrets.token_hex(4)
    rows = _drop_unclaimed(_load(), all_unclaimed=True)
    _pins.clear()
    rows.append({"id": dev_id, "name": name[:40], "hash": _hash(token), "created": time.time(), "last_seen": None})
    _save(rows)
    host = lan_ip()
    url = f"drivemind://pair?host={host}&port={port}&token={token}&id={dev_id}"
    pin = _new_pin(token, dev_id)
    return {"id": dev_id, "host": host, "port": port, "token": token, "url": url,
            "code": f"{host}:{port}#{token}", "pin": pin, "pin_expires_in": PIN_TTL, "qr_svg": qr_svg(url)}


# ---- 6-digit pairing code -------------------------------------------------------------
# The phone finds the PC on the Wi-Fi by itself (see discover()), and the person types the
# 6 digits the PC shows. A code works once, for 5 minutes, and too many wrong guesses lock
# code pairing for a while, so the 1-in-a-million code cannot be brute-forced.
PIN_TTL = 300
MAX_FAILS = 8
LOCK_SECONDS = 300
_pins: Dict[str, Dict] = {}
_fails: List[float] = []


def _new_pin(token: str, dev_id: str) -> str:
    now = time.time()
    for k in [k for k, v in _pins.items() if v["expires"] < now]:
        del _pins[k]
    pin = f"{secrets.randbelow(1_000_000):06d}"
    while pin in _pins:
        pin = f"{secrets.randbelow(1_000_000):06d}"
    _pins[pin] = {"token": token, "id": dev_id, "expires": now + PIN_TTL}
    return pin


def pairing_open() -> bool:
    now = time.time()
    return any(v["expires"] > now for v in _pins.values())


def claim(pin: str) -> Optional[Dict]:
    """Swap a valid 6-digit code for the phone's token. None if wrong, expired or locked."""
    now = time.time()
    _fails[:] = [t for t in _fails if now - t < LOCK_SECONDS]
    if len(_fails) >= MAX_FAILS:
        raise PermissionError("Too many wrong codes. Wait 5 minutes and try again.")
    pin = "".join(ch for ch in str(pin) if ch.isdigit())
    entry = _pins.get(pin)
    if not entry or entry["expires"] < now:
        _fails.append(now)
        return None
    del _pins[pin]
    return {"token": entry["token"], "id": entry["id"]}


def discover_info(port: int = DEFAULT_PORT) -> Dict:
    """What an unpaired phone may learn while looking for PCs: a name, nothing secret."""
    import platform
    from . import __version__
    return {"app": "drivemind", "pc": platform.node()[:40], "port": port, "version": __version__,
            "pairing_open": pairing_open()}


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
    rows = _load()
    kept = _drop_unclaimed(rows)
    if len(kept) != len(rows):
        _save(kept)
    return [{k: v for k, v in r.items() if k != "hash"} for r in kept]


def remove(dev_id: str) -> bool:
    rows = _load()
    keep = [r for r in rows if r["id"] != dev_id]
    _save(keep)
    return len(keep) != len(rows)


def rename(dev_id: str, name: str) -> None:
    rows = _load()
    for r in rows:
        if r["id"] == dev_id and name.strip():
            r["name"] = name.strip()[:40]
    _save(rows)


def any_paired() -> bool:
    return bool(_load())
