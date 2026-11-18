"""Thin ctypes wrappers for the Windows APIs DriveMind needs.

Every function here is a no-op that returns None/False off Windows, so the rest of
the engine (and the tests) run on any OS.
"""

from __future__ import annotations

import sys
import uuid
from typing import Optional

IS_WINDOWS = sys.platform == "win32"

# Known Folder IDs (KNOWNFOLDERID) from the Windows SDK.
KNOWN_FOLDER_IDS = {
    "Desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "Downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "Documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "Pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "Videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
    "Music": "4BD8D571-6D19-48D3-BE97-422220080E43",
}

if IS_WINDOWS:  # pragma: no cover - exercised on Windows only
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        def __init__(self, guid_str: str):
            super().__init__()
            u = uuid.UUID(guid_str)
            self.Data1, self.Data2, self.Data3 = u.fields[0], u.fields[1], u.fields[2]
            for i, b in enumerate(u.bytes[8:]):
                self.Data4[i] = b

    _shell32 = ctypes.windll.shell32
    _ole32 = ctypes.windll.ole32


def get_known_folder(name: str) -> Optional[str]:
    if not IS_WINDOWS or name not in KNOWN_FOLDER_IDS:
        return None
    path_ptr = ctypes.c_wchar_p()  # pragma: no cover
    hr = _shell32.SHGetKnownFolderPath(ctypes.byref(GUID(KNOWN_FOLDER_IDS[name])), 0, None,
                                       ctypes.byref(path_ptr))
    try:
        return path_ptr.value if hr == 0 else None
    finally:
        _ole32.CoTaskMemFree(path_ptr)


def set_known_folder(name: str, new_path: str) -> bool:
    """Point a user folder (Desktop, Downloads, ...) at a new location, as Explorer's
    Properties > Location > Move does. Files must already be moved by the caller."""
    if not IS_WINDOWS or name not in KNOWN_FOLDER_IDS:
        return False
    hr = _shell32.SHSetKnownFolderPath(ctypes.byref(GUID(KNOWN_FOLDER_IDS[name])), 0, None,  # pragma: no cover
                                       ctypes.c_wchar_p(new_path))
    return hr == 0


def free_space(path: str) -> Optional[tuple]:
    import shutil
    try:
        u = shutil.disk_usage(path)
        return u.total, u.used, u.free
    except OSError:
        return None


def is_on_battery() -> bool:
    """True when running on battery, so heavy jobs can wait for the charger."""
    if not IS_WINDOWS:
        try:
            for p in ("/sys/class/power_supply/AC/online", "/sys/class/power_supply/ACAD/online"):
                with open(p) as f:
                    return f.read().strip() == "0"
        except OSError:
            return False
        return False

    class SYSTEM_POWER_STATUS(ctypes.Structure):  # pragma: no cover
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]

    s = SYSTEM_POWER_STATUS()  # pragma: no cover
    if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
        return s.ACLineStatus == 0
    return False


def is_fullscreen_app_running() -> bool:
    """Rough check for a fullscreen game: the foreground window covers the whole monitor."""
    if not IS_WINDOWS:
        return False
    user32 = ctypes.windll.user32  # pragma: no cover
    hwnd = user32.GetForegroundWindow()
    if not hwnd or hwnd in (user32.GetDesktopWindow(), user32.GetShellWindow()):
        return False
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return rect.left <= 0 and rect.top <= 0 and rect.right >= w and rect.bottom >= h


def send_to_recycle_bin(path: str) -> bool:
    """Move a file to the Recycle Bin (used when quarantine expires)."""
    if not IS_WINDOWS:
        return False

    class SHFILEOPSTRUCTW(ctypes.Structure):  # pragma: no cover
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", ctypes.c_uint), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16),
                    ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR)]

    FO_DELETE, FOF_ALLOWUNDO, FOF_NOCONFIRMATION, FOF_SILENT = 3, 0x40, 0x10, 0x4  # pragma: no cover
    op = SHFILEOPSTRUCTW(None, FO_DELETE, path + "\0", None,
                         FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT, False, None, None)
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0
