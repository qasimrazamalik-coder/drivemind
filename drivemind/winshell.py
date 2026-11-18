"""Windows integration: Explorer right-click menu and start-with-Windows.

Everything is written under HKEY_CURRENT_USER, so no admin rights are needed and
`drivemind shell uninstall` removes it all.
"""

from __future__ import annotations

import sys
from typing import List

MENU_ROOT = r"Software\Classes\Directory\shell\DriveMind"
MENU_BG = r"Software\Classes\Directory\Background\shell\DriveMind"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

ENTRIES = [
    ("1explain", "What is this folder?", "explain \"{p}\""),
    ("2organize", "Organize with DriveMind (preview)", "organize \"{p}\" --dry-run"),
    ("3temp7", "Mark as temporary for 7 days", "tag-temp \"{p}\" --days 7"),
]


def _python(windowless: bool = False) -> str:
    exe = sys.executable
    if windowless and exe.lower().endswith("python.exe"):
        exe = exe[:-10] + "pythonw.exe"
    return f'"{exe}"'


def install_menu() -> List[str]:
    if sys.platform != "win32":
        raise RuntimeError("The Explorer menu is Windows-only")
    import winreg  # type: ignore
    done = []
    for base, placeholder in ((MENU_ROOT, "%V"), (MENU_BG, "%V")):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, "DriveMind")
            winreg.SetValueEx(k, "SubCommands", 0, winreg.REG_SZ, "")
        for key, label, args in ENTRIES:
            sub = f"{base}\\shell\\{key}"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub) as k:
                winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, label)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub + "\\command") as k:
                cmd = f'cmd /k {_python()} -m drivemind {args.format(p=placeholder)}'
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
            done.append(label)
    return done


def _delete_tree(root, path: str) -> None:
    import winreg  # type: ignore
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    child = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(root, f"{path}\\{child}")
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def uninstall_menu() -> None:
    if sys.platform != "win32":
        return
    import winreg  # type: ignore
    _delete_tree(winreg.HKEY_CURRENT_USER, MENU_ROOT)
    _delete_tree(winreg.HKEY_CURRENT_USER, MENU_BG)


def set_autostart(on: bool, port: int = 7878) -> None:
    """Start the guardian (no browser window) when Windows starts."""
    if sys.platform != "win32":
        raise RuntimeError("Autostart is Windows-only")
    import winreg  # type: ignore
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if on:
            winreg.SetValueEx(k, "DriveMind", 0, winreg.REG_SZ,
                              f"{_python(windowless=True)} -m drivemind serve --no-browser --port {port}")
        else:
            try:
                winreg.DeleteValue(k, "DriveMind")
            except FileNotFoundError:
                pass
