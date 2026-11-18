"""Path safety: protected locations, cloud placeholders, long paths, user folders."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

IS_WINDOWS = sys.platform == "win32"

# Windows file attributes (from winnt.h) used to avoid touching cloud-only files.
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
CLOUD_ATTRS = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS

# Folder names that mark "this is someone's project, move it whole, never split it".
PROJECT_MARKERS = {
    ".git", "package.json", "pyproject.toml", "requirements.txt", "setup.py", "Cargo.toml",
    "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "pubspec.yaml", "composer.json",
    "Gemfile", "*.sln", "*.csproj", "CMakeLists.txt", "Makefile", "app.json", "default.project.json",
}


def _windows_protected() -> List[Path]:
    env = os.environ
    sysroot = Path(env.get("SystemRoot", r"C:\Windows"))
    roots = [
        sysroot,
        Path(env.get("ProgramFiles", r"C:\Program Files")),
        Path(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(env.get("ProgramData", r"C:\ProgramData")),
        Path(r"C:\$Recycle.Bin"),
        Path(r"C:\System Volume Information"),
        Path(r"C:\Recovery"),
        Path(r"C:\Boot"),
    ]
    return roots


def _posix_protected() -> List[Path]:
    return [Path(p) for p in ("/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/proc",
                               "/sbin", "/sys", "/usr", "/var/lib", "/System", "/Library")]


def protected_roots(extra: Iterable[str] = ()) -> List[Path]:
    roots = _windows_protected() if IS_WINDOWS else _posix_protected()
    roots += [Path(e) for e in extra if e]
    return [_norm(r) for r in roots]


def _norm(p: Path) -> Path:
    try:
        return Path(os.path.normcase(os.path.abspath(p)))
    except Exception:
        return p


def is_within(child: Path, parent: Path) -> bool:
    c, p = _norm(child), _norm(parent)
    return c == p or p in c.parents


def is_protected(path: Path, extra: Iterable[str] = ()) -> bool:
    """True for system folders, app installs and anything inside a .git directory."""
    p = _norm(path)
    if ".git" in p.parts:
        return True
    from .config import data_dir  # local import: avoid cycle
    if is_within(p, data_dir()):
        return True
    return any(is_within(p, root) for root in protected_roots(extra))


def is_cloud_placeholder(st: os.stat_result) -> bool:
    """OneDrive / Google Drive online-only files: reading them would download them."""
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & CLOUD_ATTRS)


def is_link(st: os.stat_result) -> bool:
    attrs = getattr(st, "st_file_attributes", 0)
    return stat.S_ISLNK(st.st_mode) or bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def long_path(p: Path) -> str:
    """Windows paths over 260 characters need the \\\\?\\ prefix for file APIs."""
    s = str(p)
    if IS_WINDOWS and len(s) >= 240 and not s.startswith("\\\\?\\"):
        s = os.path.abspath(s)
        return "\\\\?\\UNC\\" + s[2:] if s.startswith("\\\\") else "\\\\?\\" + s
    return s


def looks_like_project(folder: Path) -> bool:
    try:
        names = set(os.listdir(folder))
    except OSError:
        return False
    for marker in PROJECT_MARKERS:
        if marker.startswith("*"):
            if any(n.endswith(marker[1:]) for n in names):
                return True
        elif marker in names:
            return True
    return False


def user_folders(home: Optional[Path] = None) -> Dict[str, Path]:
    """Current location of the user's main folders (Known Folders on Windows)."""
    explicit = home is not None
    home = home or Path.home()
    folders = {
        "Desktop": home / "Desktop",
        "Downloads": home / "Downloads",
        "Documents": home / "Documents",
        "Pictures": home / "Pictures",
        "Videos": home / "Videos",
        "Music": home / "Music",
    }
    if IS_WINDOWS and not explicit and os.environ.get("DRIVEMIND_TESTING") != "1":
        try:
            from .winapi import get_known_folder
            for name in list(folders):
                real = get_known_folder(name)
                if real:
                    folders[name] = Path(real)
        except Exception:
            pass
    return folders


def unique_destination(dest: Path) -> Path:
    """invoice.pdf -> invoice (2).pdf when the name is taken."""
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    n = 2
    while True:
        candidate = dest.with_name(f"{stem} ({n}){suffix}")
        if not candidate.exists():
            return candidate
        n += 1
