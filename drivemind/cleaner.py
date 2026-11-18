"""Cache Cleaner and temp-junk finder.

Each cache and each temp-junk type has its own Yes / Ask / No switch (Settings.cache_choices /
Settings.temp_choices). The global switches weekly_cache_clean and clean_temp_junk act as a
ceiling: the stricter of the two always wins.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .config import Decision, Settings, data_dir
from .paths import is_protected, looks_like_project, user_folders
from .plan import Action, Op, Plan, Status
from .scanner import iter_files

IS_WINDOWS = sys.platform == "win32"
ORDER = {Decision.NO: 0, Decision.ASK: 1, Decision.YES: 2}


def stricter(a: Decision, b: Decision) -> Decision:
    return a if ORDER[a] <= ORDER[b] else b


# ------------------------------------------------------------ cache catalog ---
@dataclass
class CacheEntry:
    id: str
    name: str
    effect: str                       # what happens when it is cleared
    default: Decision
    win: List[str] = field(default_factory=list)     # path templates (glob allowed)
    posix: List[str] = field(default_factory=list)
    command: Optional[List[str]] = None              # cleared by a tool instead of file deletion
    apps: List[str] = field(default_factory=list)    # process names that must be closed
    display_only: bool = False                       # shown for size, never cleared by DriveMind
    admin: bool = False
    min_age_days: float = 0                          # only files unused this long (temp folders: 1 day)


Y, A, N = Decision.YES, Decision.ASK, Decision.NO

CATALOG: List[CacheEntry] = [
    CacheEntry("browser", "Browser cache (Chrome, Edge, Brave, Firefox)",
               "Pages load a bit slower once; cookies, passwords and history are kept", Y,
               win=["{LOCALAPPDATA}/Google/Chrome/User Data/*/Cache", "{LOCALAPPDATA}/Google/Chrome/User Data/*/Code Cache",
                    "{LOCALAPPDATA}/Microsoft/Edge/User Data/*/Cache", "{LOCALAPPDATA}/Microsoft/Edge/User Data/*/Code Cache",
                    "{LOCALAPPDATA}/BraveSoftware/Brave-Browser/User Data/*/Cache",
                    "{LOCALAPPDATA}/Mozilla/Firefox/Profiles/*/cache2"],
               posix=["{HOME}/.cache/google-chrome/*/Cache", "{HOME}/.cache/chromium/*/Cache",
                      "{HOME}/.cache/mozilla/firefox/*/cache2", "{HOME}/.cache/BraveSoftware/Brave-Browser/*/Cache"],
               apps=["chrome", "msedge", "brave", "firefox"]),
    # Only files untouched for a day: a running installer may still need newer ones.
    # Not offered on Linux/macOS, where the OS manages /tmp itself.
    CacheEntry("wintemp", "Windows temp", "Nothing — only files unused for a day; files in use are skipped", Y,
               win=["{TEMP}", "{SYSTEMROOT}/Temp"], min_age_days=1),
    CacheEntry("wupdate", "Windows Update download cache", "Nothing after updates finish", Y,
               win=["{SYSTEMROOT}/SoftwareDistribution/Download"], admin=True),
    CacheEntry("delivery", "Delivery Optimization cache", "Nothing", Y,
               win=["{SYSTEMROOT}/ServiceProfiles/NetworkService/AppData/Local/Microsoft/Windows/DeliveryOptimization/Cache"],
               admin=True),
    CacheEntry("thumbs", "Thumbnail cache", "Photo folders show blank icons until rebuilt", A,
               win=["{LOCALAPPDATA}/Microsoft/Windows/Explorer/thumbcache_*.db"],
               posix=["{HOME}/.cache/thumbnails"]),
    CacheEntry("prefetch", "Prefetch", "Apps and boot start slower for a while — not worth it", N,
               win=["{SYSTEMROOT}/Prefetch"], admin=True),
    CacheEntry("shaders", "GPU shader cache (DirectX, NVIDIA, AMD)", "Games stutter while shaders rebuild", A,
               win=["{LOCALAPPDATA}/D3DSCache", "{LOCALAPPDATA}/NVIDIA/DXCache", "{LOCALAPPDATA}/NVIDIA/GLCache",
                    "{LOCALAPPDATA}/AMD/DxCache"],
               posix=["{HOME}/.cache/mesa_shader_cache", "{HOME}/.nv/GLCache"]),
    CacheEntry("crashdumps", "Crash dumps and error reports", "Nothing unless you are debugging a crash", Y,
               win=["{LOCALAPPDATA}/CrashDumps", "{PROGRAMDATA}/Microsoft/Windows/WER/ReportArchive",
                    "{LOCALAPPDATA}/Microsoft/Windows/WER/ReportArchive", "{SYSTEMROOT}/MEMORY.DMP",
                    "{SYSTEMROOT}/Minidump"],
               posix=["/var/crash"]),
    CacheEntry("npm", "npm / Yarn / pnpm cache", "Next install downloads packages again", A,
               win=["{LOCALAPPDATA}/npm-cache", "{LOCALAPPDATA}/Yarn/Cache", "{LOCALAPPDATA}/pnpm/store"],
               posix=["{HOME}/.npm/_cacache", "{HOME}/.cache/yarn", "{HOME}/.local/share/pnpm/store"]),
    CacheEntry("pip", "pip cache", "Next install downloads again", Y,
               win=["{LOCALAPPDATA}/pip/Cache"], posix=["{HOME}/.cache/pip"]),
    CacheEntry("gradle", "Gradle and Android build caches", "Next Android build is slow once", A,
               win=["{USERPROFILE}/.gradle/caches", "{USERPROFILE}/.android/cache"],
               posix=["{HOME}/.gradle/caches", "{HOME}/.android/cache"]),
    CacheEntry("docker", "Docker build cache", "Next image build is slow once", A,
               command=["docker", "builder", "prune", "-f"]),
    CacheEntry("expo", "Expo / Metro cache", "Next bundle is slow once", Y,
               win=["{TEMP}/metro-*", "{TEMP}/haste-map-*", "{USERPROFILE}/.expo/cache"],
               posix=["{TMPDIR}/metro-*", "{TMPDIR}/haste-map-*", "{HOME}/.expo/cache"], min_age_days=1),
    CacheEntry("appcaches", "App caches of closed apps (VS Code, Discord, Teams, Slack, Spotify)",
               "Cleared only while the app is closed; settings and logins kept", Y,
               win=["{APPDATA}/Code/Cache", "{APPDATA}/Code/CachedData", "{APPDATA}/Code/Code Cache",
                    "{APPDATA}/discord/Cache", "{APPDATA}/discord/Code Cache", "{APPDATA}/Slack/Cache",
                    "{APPDATA}/Microsoft/Teams/Cache", "{LOCALAPPDATA}/Spotify/Data"],
               posix=["{HOME}/.config/Code/Cache", "{HOME}/.config/Code/CachedData", "{HOME}/.config/discord/Cache",
                      "{HOME}/.config/Slack/Cache", "{HOME}/.cache/spotify/Data"],
               apps=["code", "discord", "slack", "teams", "ms-teams", "spotify"]),
    CacheEntry("recycle", "Recycle Bin", "Those files are gone for good", A,
               command=["powershell", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"]
               if IS_WINDOWS else None, posix=["{HOME}/.local/share/Trash/files"]),
    CacheEntry("aimodels", "Local AI models (Ollama, Hugging Face)", "Multi-GB re-download — shown for size only", N,
               win=["{USERPROFILE}/.ollama/models", "{USERPROFILE}/.cache/huggingface"],
               posix=["{HOME}/.ollama/models", "{HOME}/.cache/huggingface"], display_only=True),
    CacheEntry("cookies", "Browser cookies and saved logins", "You are signed out everywhere — never in auto mode", N,
               display_only=True),
]
CATALOG_BY_ID = {c.id: c for c in CATALOG}


def env_map(env: Optional[Dict[str, str]] = None, home: Optional[Path] = None) -> Dict[str, str]:
    e = dict(os.environ if env is None else env)
    h = str(home or Path.home())
    return {
        "HOME": h,
        "USERPROFILE": e.get("USERPROFILE", h),
        "LOCALAPPDATA": e.get("LOCALAPPDATA", os.path.join(h, "AppData", "Local")),
        "APPDATA": e.get("APPDATA", os.path.join(h, "AppData", "Roaming")),
        "TEMP": e.get("TEMP", e.get("TMP", os.path.join(h, "AppData", "Local", "Temp"))),
        "TMPDIR": e.get("TMPDIR", "/tmp"),
        "SYSTEMROOT": e.get("SystemRoot", e.get("SYSTEMROOT", r"C:\Windows")),
        "PROGRAMDATA": e.get("ProgramData", e.get("PROGRAMDATA", r"C:\ProgramData")),
    }


def resolve_paths(entry: CacheEntry, env: Optional[Dict[str, str]] = None, home: Optional[Path] = None,
                  windows: Optional[bool] = None) -> List[Path]:
    win = IS_WINDOWS if windows is None else windows
    vals = env_map(env, home)
    out: List[Path] = []
    for tpl in (entry.win if win else entry.posix):
        pattern = tpl.format(**vals)
        for match in sorted(glob.glob(pattern)):
            p = Path(match)
            if p.exists():
                out.append(p)
    return out


def path_size(p: Path) -> int:
    if p.is_file():
        try:
            return p.stat().st_size
        except OSError:
            return 0
    total = 0
    for dirpath, _, files in os.walk(p):
        for n in files:
            try:
                total += os.lstat(os.path.join(dirpath, n)).st_size
            except OSError:
                pass
    return total


def running_processes() -> set:
    names = set()
    try:
        if IS_WINDOWS:
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                if line.startswith('"'):
                    names.add(line.split('","')[0].strip('"').lower().removesuffix(".exe"))
        else:
            for pid in os.listdir("/proc"):
                if pid.isdigit():
                    try:
                        with open(f"/proc/{pid}/comm") as f:
                            names.add(f.read().strip().lower())
                    except OSError:
                        pass
    except Exception:
        pass
    return names


def cache_report(settings: Settings, env=None, home=None, windows=None) -> List[Dict]:
    """Size and status of every cache, for the Cache Cleaner table."""
    running = running_processes()
    rows = []
    for c in CATALOG:
        paths = resolve_paths(c, env, home, windows)
        size = sum(path_size(p) for p in paths)
        open_apps = sorted(a for a in c.apps if a in running)
        rows.append({
            "id": c.id, "name": c.name, "effect": c.effect, "size": size,
            "paths": [str(p) for p in paths], "command": " ".join(c.command) if c.command else None,
            "default": c.default.value,
            "choice": settings.cache_choices.get(c.id, c.default).value if not c.display_only else "no",
            "display_only": c.display_only, "admin": c.admin, "apps_open": open_apps,
        })
    return rows


def entry_for_path(path: Path, env=None, home=None, windows=None) -> Optional[CacheEntry]:
    p = os.path.normcase(os.path.abspath(path))
    for c in CATALOG:
        for known in resolve_paths(c, env, home, windows):
            if os.path.normcase(os.path.abspath(known)) == p:
                return c
    return None


def is_known_cache_path(path: Path, env=None, home=None, windows=None) -> bool:
    """Whitelist check used by the executor before deleting anything as a cache."""
    p = os.path.normcase(os.path.abspath(path))
    for c in CATALOG:
        if c.display_only:
            continue
        for known in resolve_paths(c, env, home, windows):
            if os.path.normcase(os.path.abspath(known)) == p:
                return True
    return False


def plan_cache_clean(settings: Settings, only: Optional[Iterable[str]] = None, env=None, home=None,
                     windows=None, scheduled: bool = False) -> Plan:
    plan = Plan(title="Cache clean", kind="clean")
    ceiling = settings.decision("weekly_cache_clean") if scheduled else Decision.YES
    running = running_processes()
    wanted = set(only) if only else None
    for c in CATALOG:
        if wanted is not None and c.id not in wanted:
            continue
        choice = settings.cache_choices.get(c.id, c.default)
        if wanted is not None and c.id in wanted and choice == Decision.NO and not c.display_only:
            choice = Decision.ASK  # the user picked it by hand: propose it, never auto-run it
        decision = stricter(choice, ceiling)
        if c.display_only:
            decision = Decision.NO
        open_apps = [a for a in c.apps if a in running]
        if c.command:
            plan.actions.append(Action(op=Op.DELETE_CACHE, src="cmd:" + " ".join(c.command), size=0,
                                       category=c.id, reason=f"{c.name}: {c.effect}", option="weekly_cache_clean",
                                       decision=decision, status=_status(decision)))
            continue
        for p in resolve_paths(c, env, home, windows):
            size = path_size(p)
            if size == 0:
                continue
            reason = f"{c.name}: {c.effect}"
            d = decision
            if open_apps:
                d, reason = Decision.NO, reason + f" — skipped, {', '.join(open_apps)} is open"
            plan.actions.append(Action(op=Op.DELETE_CACHE, src=str(p), size=size, category=c.id, reason=reason,
                                       option="weekly_cache_clean", decision=d, status=_status(d)))
    return plan


def _status(d: Decision) -> Status:
    return Status.SKIPPED if d == Decision.NO else Status.PENDING


# -------------------------------------------------------------- temp junk ---
@dataclass
class TempRule:
    id: str
    name: str
    rule: str
    default: Decision


TEMP_RULES: List[TempRule] = [
    TempRule("unfinished", "Unfinished downloads (.crdownload, .part, .tmp)", "Older than 2 days", Y),
    TempRule("officelock", "Orphaned Office lock files (~$report.docx)", "The real file is closed", Y),
    TempRule("emptydirs", "Empty folders", "Anywhere outside system folders", Y),
    TempRule("installers", "Old installers (.exe, .msi) in Downloads", "Older than 14 days", A),
    TempRule("extractedzips", "Zip files already extracted", "Zip and its extracted folder both exist; keeps the folder", A),
    TempRule("backups", "Backup and swap files (.bak, .swp, ~ files)", "Older than 30 days", A),
    TempRule("biglogs", "Large log files", "Over 50 MB and older than 30 days", A),
    TempRule("buildout", "Build outputs (dist, build, .next, bin/obj)", "In projects untouched for 60+ days", A),
    TempRule("oldshots", "Old screenshots and screen recordings", "Older than 90 days — archived, not deleted", A),
    TempRule("windowsold", "Windows.old", "After a Windows upgrade; removing it ends rollback", N),
]
TEMP_BY_ID = {t.id: t for t in TEMP_RULES}
INSTALLER_EXT = {".exe", ".msi", ".msix", ".appx", ".apk"}
UNFINISHED_EXT = {".crdownload", ".part", ".partial", ".download", ".tmp"}
BACKUP_EXT = {".bak", ".swp", ".swo", ".old", ".orig"}
SCREENSHOT_PREFIXES = ("screenshot", "screen shot", "screen recording", "capture", "snip")


def temp_report(settings: Settings) -> List[Dict]:
    return [{"id": t.id, "name": t.name, "rule": t.rule, "default": t.default.value,
             "choice": settings.temp_choices.get(t.id, t.default).value} for t in TEMP_RULES]


def plan_temp_clean(settings: Settings, roots: Optional[List[Path]] = None, archive_root: Optional[Path] = None,
                    now: Optional[float] = None) -> Plan:
    from .devjunk import find_dev_junk
    now = now or time.time()
    folders = user_folders()
    roots = roots or [folders["Desktop"], folders["Downloads"], folders["Documents"]]
    roots = [r for r in roots if r.exists()]
    downloads = folders["Downloads"]
    archive_root = archive_root or (Path(settings.organize_root) / "Archive" if settings.organize_root
                                    else Path.home() / "DriveMind Archive")
    ceiling = settings.decision("clean_temp_junk")
    plan = Plan(title="Temporary files clean", kind="temp")

    def dec(rule_id: str) -> Decision:
        return stricter(settings.temp_choices.get(rule_id, TEMP_BY_ID[rule_id].default), ceiling)

    def add(rule_id: str, op: Op, src: Path, size: int, reason: str, dst: Optional[Path] = None):
        d = dec(rule_id)
        plan.actions.append(Action(op=op, src=str(src), dst=str(dst) if dst else None, size=size, category=rule_id,
                                   reason=reason, option="clean_temp_junk", decision=d, status=_status(d)))

    seen = set()
    for root in roots:
        if is_protected(root, settings.exclusions):
            continue
        for f in iter_files(root, skip_dir=lambda p: p.name in {"node_modules", ".git", ".venv", "venv"}):
            if str(f.path) in seen:
                continue
            seen.add(str(f.path))
            age = (now - f.mtime) / 86400
            name, ext = f.path.name, f.ext
            if ext in UNFINISHED_EXT and age > 2:
                add("unfinished", Op.QUARANTINE, f.path, f.size, f"unfinished download, {age:.0f} days old")
            elif name.startswith("~$") and age > 1:
                add("officelock", Op.QUARANTINE, f.path, f.size, "Office lock file left behind")
            elif ext in INSTALLER_EXT and _within(f.path, downloads) and age > 14:
                add("installers", Op.QUARANTINE, f.path, f.size, f"installer, {age:.0f} days old")
            elif (ext in BACKUP_EXT or name.endswith("~")) and age > 30:
                add("backups", Op.QUARANTINE, f.path, f.size, f"backup/swap file, {age:.0f} days old")
            elif ext == ".log" and f.size > 50 * 1024 * 1024 and age > 30:
                add("biglogs", Op.QUARANTINE, f.path, f.size, f"log file {f.size // (1024 * 1024)} MB, {age:.0f} days old")
            elif ext == ".zip" and (f.path.parent / f.path.stem).is_dir():
                add("extractedzips", Op.QUARANTINE, f.path, f.size, f"already extracted to {f.path.stem}/")
            elif name.lower().startswith(SCREENSHOT_PREFIXES) and age > 90:
                dst = archive_root / "Screenshots" / time.strftime("%Y", time.localtime(f.mtime)) / name
                add("oldshots", Op.MOVE, f.path, f.size, f"screenshot {age:.0f} days old — archived", dst)
        for d in _empty_dirs(root):
            add("emptydirs", Op.QUARANTINE, d, 0, "empty folder")

    for junk in find_dev_junk(roots, settings.stale_project_days, kinds={"build"}, now=now):
        add("buildout", Op.DELETE_CACHE, Path(junk["path"]), junk["size"],
            f"{junk['name']} in '{Path(junk['project']).name}', untouched {junk['idle_days']:.0f} days — {junk['restore']}")

    win_old = Path(os.environ.get("SystemDrive", "C:") + "\\Windows.old")
    if IS_WINDOWS and win_old.exists():
        plan.notes.append("Windows.old found — remove it with Disk Cleanup > 'Previous Windows installations' "
                          "(needs admin; ends the option to roll back).")
    _add_temp_zone(plan, settings, now, add)
    return plan


def _within(p: Path, parent: Path) -> bool:
    try:
        p.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _empty_dirs(root: Path) -> List[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        p = Path(dirpath)
        if p == root or ".git" in p.parts or looks_like_project(p.parent):
            continue
        if not filenames and not any((p / d) not in out and (p / d).exists() for d in dirnames):
            out.append(p)
    # keep only the top-most empty folders (their children go with them)
    tops = [d for d in out if not any(o != d and o in d.parents for o in out)]
    return tops


# ---------------------------------------------------- temp zone + expiry ---
def temp_zone() -> Path:
    if IS_WINDOWS and Path("D:\\").exists():
        z = Path("D:\\Temp")
    else:
        z = Path.home() / "DriveMind Temp"
    return z


def expiry_path() -> Path:
    return data_dir() / "expiry.json"


def load_expiry() -> Dict[str, float]:
    try:
        return json.loads(expiry_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def tag_temporary(path: Path, days: float) -> float:
    """Right-click 'Temporary for N days'. Returns the expiry timestamp."""
    tags = load_expiry()
    expires = time.time() + days * 86400
    tags[str(Path(path).resolve())] = expires
    expiry_path().write_text(json.dumps(tags, indent=2), encoding="utf-8")
    return expires


def _add_temp_zone(plan: Plan, settings: Settings, now: float, add) -> None:
    zone = temp_zone()
    if zone.exists():
        for f in iter_files(zone):
            age = (now - f.mtime) / 86400
            if age > settings.temp_zone_days:
                add("unfinished", Op.QUARANTINE, f.path, f.size, f"in Temp Zone for {age:.0f} days")
    tags = load_expiry()
    for p, exp in tags.items():
        if exp <= now and Path(p).exists():
            add("unfinished", Op.QUARANTINE, Path(p), path_size(Path(p)), "temporary tag expired")
