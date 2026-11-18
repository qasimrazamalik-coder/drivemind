"""Installed apps (with size and install date) and startup apps.

Startup apps are switched on/off exactly as Task Manager does it — through the
`StartupApproved` registry values — so the change is reversible and Windows shows the
same state in Task Manager > Startup apps. Only per-user (HKCU) entries are changed;
machine-wide ones need admin and are shown read-only.

The registry is read through a small `Reg` adapter so the logic is testable off Windows.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

UNINSTALL_KEYS = [
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
]
RUN_KEYS = [("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"),
            ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run")]
APPROVED = {"HKCU": r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
            "HKLM": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"}
ENABLED = bytes([2] + [0] * 11)
DISABLED_PREFIX = 3


class Reg:
    """Minimal registry adapter: real winreg on Windows, a dict in tests."""

    def __init__(self, fake: Optional[Dict[Tuple[str, str], Dict]] = None):
        self.fake = fake

    def subkeys(self, hive: str, path: str) -> List[str]:
        if self.fake is not None:
            pre = path + "\\"
            return sorted({k[1][len(pre):].split("\\")[0] for k in self.fake if k[0] == hive and k[1].startswith(pre)})
        import winreg  # type: ignore
        out = []
        try:
            with winreg.OpenKey(_hive(hive), path) as k:
                i = 0
                while True:
                    try:
                        out.append(winreg.EnumKey(k, i))
                    except OSError:
                        break
                    i += 1
        except OSError:
            pass
        return out

    def values(self, hive: str, path: str) -> Dict:
        if self.fake is not None:
            return dict(self.fake.get((hive, path), {}))
        import winreg  # type: ignore
        out = {}
        try:
            with winreg.OpenKey(_hive(hive), path) as k:
                i = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    out[name] = val
                    i += 1
        except OSError:
            pass
        return out

    def set_binary(self, hive: str, path: str, name: str, data: bytes) -> None:
        if self.fake is not None:
            self.fake.setdefault((hive, path), {})[name] = data
            return
        import winreg  # type: ignore
        with winreg.CreateKey(_hive(hive), path) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_BINARY, data)


def _hive(h: str):
    import winreg  # type: ignore
    return winreg.HKEY_LOCAL_MACHINE if h == "HKLM" else winreg.HKEY_CURRENT_USER


def _date(s) -> Optional[str]:
    try:
        return datetime.strptime(str(s), "%Y%m%d").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def installed_apps(reg: Optional[Reg] = None) -> List[Dict]:
    if reg is None:
        if sys.platform != "win32":
            return []
        reg = Reg()
    seen, out = set(), []
    for hive, base in UNINSTALL_KEYS:
        for sub in reg.subkeys(hive, base):
            v = reg.values(hive, f"{base}\\{sub}")
            name = (v.get("DisplayName") or "").strip()
            if not name or v.get("SystemComponent") == 1 or v.get("ParentKeyName") or name.lower() in seen:
                continue
            if name.startswith(("Update for", "Security Update", "Hotfix")):
                continue
            seen.add(name.lower())
            size_kb = v.get("EstimatedSize") or 0
            loc = (v.get("InstallLocation") or "").strip().strip('"')
            out.append({
                "name": name, "publisher": (v.get("Publisher") or "").strip(), "version": str(v.get("DisplayVersion") or ""),
                "size": int(size_kb) * 1024 if isinstance(size_kb, int) else 0, "installed": _date(v.get("InstallDate")),
                "location": loc, "drive": (loc[:2].upper() if len(loc) > 1 and loc[1] == ":" else ""), "scope": "all users" if hive == "HKLM" else "you",
            })
    out.sort(key=lambda a: a["size"], reverse=True)
    return out


def _startup_folder_items() -> List[Dict]:
    out = []
    folders = []
    if os.environ.get("APPDATA"):
        folders.append(Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup")
    if os.environ.get("ProgramData"):
        folders.append(Path(os.environ["ProgramData"]) / "Microsoft/Windows/Start Menu/Programs/StartUp")
    for f in folders:
        if f.is_dir():
            for item in f.iterdir():
                if item.name.lower() != "desktop.ini":
                    out.append({"name": item.stem, "command": str(item), "source": "Startup folder",
                                "hive": None, "enabled": True, "can_toggle": False})
    return out


def startup_apps(reg: Optional[Reg] = None, include_folders: bool = True) -> List[Dict]:
    if reg is None:
        if sys.platform != "win32":
            return []
        reg = Reg()
    out = []
    for hive, path in RUN_KEYS:
        approved = reg.values(hive, APPROVED[hive])
        for name, cmd in reg.values(hive, path).items():
            state = approved.get(name)
            enabled = not (isinstance(state, (bytes, bytearray)) and len(state) and state[0] % 2 == 1)
            out.append({"name": name, "command": str(cmd), "source": "Registry (you)" if hive == "HKCU" else "Registry (all users)",
                        "hive": hive, "enabled": enabled, "can_toggle": hive == "HKCU"})
    if include_folders:
        out += _startup_folder_items()
    return out


def set_startup(name: str, enabled: bool, reg: Optional[Reg] = None) -> bool:
    """Turn a per-user startup app on or off, the same way Task Manager does."""
    reg = reg or Reg()
    if name not in reg.values("HKCU", RUN_KEYS[0][1]):
        return False
    import struct
    import time
    data = ENABLED if enabled else bytes([DISABLED_PREFIX, 0, 0, 0]) + struct.pack("<Q", int((time.time() + 11644473600) * 1e7))
    reg.set_binary("HKCU", APPROVED["HKCU"], name, data)
    return True
