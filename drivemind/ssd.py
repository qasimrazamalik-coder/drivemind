"""SSD / disk health from the drive's own reliability counters (SMART).

Windows: PowerShell Get-PhysicalDisk + Get-StorageReliabilityCounter (no extra software).
Some counters (wear, temperature) need DriveMind to run as administrator; when Windows
does not report them, DriveMind says so instead of guessing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import Dict, List, Optional

PS = r"""
Get-PhysicalDisk | ForEach-Object {
  $r = $null; try { $r = $_ | Get-StorageReliabilityCounter -ErrorAction Stop } catch {}
  [pscustomobject]@{
    Name = $_.FriendlyName; Media = [string]$_.MediaType; Bus = [string]$_.BusType
    Health = [string]$_.HealthStatus; SizeGB = [math]::Round($_.Size / 1GB)
    Wear = $r.Wear; Temp = $r.Temperature; TempMax = $r.TemperatureMax
    ReadErrors = $r.ReadErrorsTotal; WriteErrors = $r.WriteErrorsTotal; PowerOnHours = $r.PowerOnHours
  }
} | ConvertTo-Json -Depth 3
"""


def _read_windows() -> Optional[str]:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", PS],
                           capture_output=True, text=True, timeout=60)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def parse(raw: Optional[str]) -> List[Dict]:
    if not raw or not raw.strip():
        return []
    data = json.loads(raw)
    rows = data if isinstance(data, list) else [data]
    return [assess(r) for r in rows]


def assess(d: Dict) -> Dict:
    """Plain-language verdict from the raw counters."""
    notes: List[str] = []
    status = "good"

    def worse(s: str):
        nonlocal status
        order = {"good": 0, "watch": 1, "critical": 2}
        if order[s] > order[status]:
            status = s

    health = (d.get("Health") or "").lower()
    if health and health not in ("healthy", "0"):
        worse("critical")
        notes.append(f"Windows reports the disk as {d.get('Health')} — back up now")
    wear = d.get("Wear")
    if isinstance(wear, (int, float)):
        if wear >= 80:
            worse("critical")
            notes.append(f"{wear}% of its write life is used — plan a replacement")
        elif wear >= 50:
            worse("watch")
            notes.append(f"{wear}% of its write life is used")
        else:
            notes.append(f"{wear}% of its write life used")
    temp = d.get("Temp")
    if isinstance(temp, (int, float)) and temp:
        if temp >= 70:
            worse("watch")
            notes.append(f"running hot: {temp}°C (keep vents clear, avoid long heavy loads)")
        else:
            notes.append(f"{temp}°C")
    errs = (d.get("ReadErrors") or 0) + (d.get("WriteErrors") or 0)
    if errs:
        worse("watch")
        notes.append(f"{errs} read/write errors recorded")
    measured = any(isinstance(d.get(k), (int, float)) for k in ("Wear", "Temp"))
    if not measured:
        notes.append("wear and temperature not reported — run DriveMind as administrator to read them")
    return {"name": d.get("Name") or "Disk", "media": d.get("Media") or "", "bus": d.get("Bus") or "",
            "size_gb": d.get("SizeGB"), "health": d.get("Health") or "unknown", "wear": wear, "temp": temp,
            "power_on_hours": d.get("PowerOnHours"), "status": status, "notes": notes}


def disk_health() -> List[Dict]:
    if sys.platform == "win32":
        try:
            return parse(_read_windows())
        except ValueError:
            return []
    if shutil.which("smartctl"):
        return []  # Linux/macOS: smartctl support can be added; Windows is the target
    return []
