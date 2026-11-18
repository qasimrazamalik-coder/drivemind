"""Developer data that quietly fills drive C: — WSL, Docker, Android SDK/emulators, Gradle,
Ollama models, Steam games — with its size and the exact, supported way to move it.

DriveMind does not move these itself: each tool has its own supported mover, and doing it
by hand can break the tool. It shows the size, the steps, and commands you can copy.
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .cleaner import env_map, path_size

ITEMS = [
    {
        "id": "wsl", "name": "WSL Linux distros",
        "find": ["{LOCALAPPDATA}/Packages/*/LocalState/ext4.vhdx", "{LOCALAPPDATA}/wsl/*/ext4.vhdx"],
        "steps": [
            "Close every WSL window and app that uses Linux.",
            "Run: wsl --shutdown",
            "Run: wsl --list --verbose   (note the distro name, e.g. Ubuntu)",
            "Run: wsl --manage Ubuntu --move D:\\WSL\\Ubuntu   (WSL 2.0+)",
            "Older WSL: wsl --export Ubuntu D:\\WSL\\ubuntu.tar, then wsl --unregister Ubuntu, then "
            "wsl --import Ubuntu D:\\WSL\\Ubuntu D:\\WSL\\ubuntu.tar",
        ],
        "compact": True,
    },
    {
        "id": "docker", "name": "Docker Desktop disk",
        "find": ["{LOCALAPPDATA}/Docker/wsl/disk/docker_data.vhdx", "{LOCALAPPDATA}/Docker/wsl/data/ext4.vhdx",
                 "{LOCALAPPDATA}/Docker/wsl/main/ext4.vhdx"],
        "steps": [
            "Free space inside Docker first: docker system prune  (removes stopped containers and unused images)",
            "Docker Desktop > Settings > Resources > Advanced > Disk image location > choose D:\\Docker",
            "Apply & restart — Docker moves the disk itself.",
        ],
        "compact": True,
    },
    {
        "id": "avd", "name": "Android emulators (AVD)",
        "find": ["{USERPROFILE}/.android/avd"],
        "steps": [
            "Close Android Studio and all emulators.",
            "Move the folder {USERPROFILE}\\.android\\avd to D:\\Android\\avd",
            "Run: setx ANDROID_AVD_HOME D:\\Android\\avd",
            "Edit each D:\\Android\\avd\\*.ini file: change path= to the new folder.",
        ],
    },
    {
        "id": "sdk", "name": "Android SDK",
        "find": ["{LOCALAPPDATA}/Android/Sdk"],
        "steps": [
            "Close Android Studio.",
            "Move {LOCALAPPDATA}\\Android\\Sdk to D:\\Android\\Sdk",
            "Run: setx ANDROID_HOME D:\\Android\\Sdk",
            "Android Studio > Settings > Languages & Frameworks > Android SDK > Edit location > D:\\Android\\Sdk",
        ],
    },
    {
        "id": "gradle", "name": "Gradle home (caches, wrappers)",
        "find": ["{USERPROFILE}/.gradle"],
        "steps": ["Close Android Studio / IDEs.", "Move {USERPROFILE}\\.gradle to D:\\Dev\\gradle",
                  "Run: setx GRADLE_USER_HOME D:\\Dev\\gradle"],
    },
    {
        "id": "ollama", "name": "Ollama AI models",
        "find": ["{USERPROFILE}/.ollama/models"],
        "steps": ["Quit Ollama from the tray.", "Move {USERPROFILE}\\.ollama\\models to D:\\AI\\ollama-models",
                  "Run: setx OLLAMA_MODELS D:\\AI\\ollama-models", "Start Ollama again."],
    },
    {
        "id": "steam", "name": "Steam games",
        "find": ["{PROGRAMFILESX86}/Steam/steamapps/common"],
        "steps": ["Steam > Settings > Storage > add a library on D:",
                  "Select a game > Move — Steam moves it safely."],
    },
    {
        "id": "nuget", "name": "NuGet packages (.NET)",
        "find": ["{USERPROFILE}/.nuget/packages"],
        "steps": ["Run: setx NUGET_PACKAGES D:\\Dev\\nuget", "Move the folder, or let it re-download on next build."],
    },
]


def _vals(env=None, home=None) -> Dict[str, str]:
    v = env_map(env, home)
    e = os.environ if env is None else env
    v["PROGRAMFILESX86"] = e.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    return v


def compact_script(vhdx: str) -> str:
    """diskpart script that shrinks a WSL/Docker virtual disk after files were deleted inside it."""
    return (f'select vdisk file="{vhdx}"\nattach vdisk readonly\ncompact vdisk\ndetach vdisk\nexit\n')


def report(env=None, home=None, windows: Optional[bool] = None) -> List[Dict]:
    win = sys.platform == "win32" if windows is None else windows
    if not win:
        return []
    vals = _vals(env, home)
    out = []
    for item in ITEMS:
        found = []
        for tpl in item["find"]:
            found += [Path(p) for p in glob.glob(tpl.format(**vals))]
        if not found:
            continue
        size = sum(path_size(p) for p in found)
        steps = [s.format(**vals) for s in item["steps"]]
        row = {"id": item["id"], "name": item["name"], "size": size, "paths": [str(p) for p in found], "steps": steps}
        if item.get("compact"):
            row["compact"] = {
                "why": "These virtual disks grow but never shrink by themselves, even after you delete files inside.",
                "how": "Run 'wsl --shutdown', then save the script as compact.txt and run 'diskpart /s compact.txt' "
                       "in an administrator terminal.",
                "scripts": [compact_script(str(p)) for p in found if str(p).endswith(".vhdx")],
            }
        out.append(row)
    out.sort(key=lambda r: r["size"], reverse=True)
    return out
