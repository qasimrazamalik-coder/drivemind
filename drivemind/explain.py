"""'What is this folder?' — known-folder knowledge first, local AI second."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

from .scanner import human

# (who made it, what it holds, safe to delete?)
KNOWN: Dict[str, tuple] = {
    "node_modules": ("npm / Node.js", "JavaScript packages installed for a project", "Yes — run `npm install` to get it back"),
    ".venv": ("Python", "a project's virtual environment", "Yes — recreate it and reinstall requirements"),
    "venv": ("Python", "a project's virtual environment", "Yes — recreate it and reinstall requirements"),
    "__pycache__": ("Python", "compiled bytecode", "Yes — Python recreates it"),
    ".gradle": ("Gradle (Android / Java)", "build cache and downloaded dependencies", "Yes — next build re-downloads"),
    ".android": ("Android Studio", "emulator images (avd), SDK settings and caches", "Partly — avd holds emulators you may still use"),
    ".expo": ("Expo (React Native)", "local Expo state and cache", "Yes"),
    ".next": ("Next.js", "build output", "Yes — `npm run build` recreates it"),
    "dist": ("a build tool", "build output", "Usually — rebuild with the project's build command"),
    "build": ("a build tool", "build output", "Usually — rebuild with the project's build command"),
    "target": ("Rust (cargo) or Maven", "build output", "Yes — rebuild"),
    "temp": ("Windows and apps", "temporary files", "Yes — files in use are skipped"),
    "tmp": ("apps", "temporary files", "Usually yes"),
    "cache": ("an app", "cached data the app can re-download", "Usually yes, with the app closed"),
    "code cache": ("a Chromium-based app", "compiled script cache", "Yes, with the app closed"),
    "crashdumps": ("Windows Error Reporting", "crash memory dumps", "Yes unless you are debugging a crash"),
    "winsxs": ("Windows", "Windows component store (shared with system files)", "NO — use Disk Cleanup or DISM, never delete by hand"),
    "softwaredistribution": ("Windows Update", "update downloads and history", "Only the Download subfolder, after updates finish"),
    "installer": ("Windows Installer", "files needed to repair or uninstall apps", "NO — apps may fail to update or uninstall"),
    "package cache": ("Visual Studio / installers", "setup packages for repair and uninstall", "Risky — some apps need them to update"),
    "$windows.~bt": ("Windows upgrade", "leftover upgrade files", "Yes, via Disk Cleanup"),
    "windows.old": ("Windows upgrade", "your previous Windows installation", "Yes via Disk Cleanup — ends the option to roll back"),
    "docker": ("Docker Desktop", "images, containers and the WSL disk", "Only via Docker: `docker system prune`"),
    "wsl": ("Windows Subsystem for Linux", "Linux distributions' virtual disks", "NO — export the distro first"),
    ".ollama": ("Ollama", "downloaded AI models", "Yes, but each model is a large re-download"),
    "huggingface": ("Hugging Face", "downloaded AI models and datasets", "Yes, but large re-downloads"),
    "steamapps": ("Steam", "installed games", "Uninstall games from Steam instead"),
    "onedrive": ("OneDrive", "files synced with your cloud", "NO — deleting here deletes in the cloud too"),
    "prefetch": ("Windows", "app launch optimization data", "Not worth it — apps start slower for a while"),
}


def explain(path: Path, use_ai: bool = True, ai_client=None) -> Dict:
    path = Path(path)
    name = path.name.lower()
    size = 0
    samples = []
    for dirpath, dirnames, files in os.walk(path):
        for n in files:
            try:
                size += os.lstat(os.path.join(dirpath, n)).st_size
            except OSError:
                pass
            if len(samples) < 25:
                samples.append(n)
        if size > 50 * 1024 ** 3:
            break
    out = {"path": str(path), "size": size, "size_human": human(size)}
    hit: Optional[tuple] = KNOWN.get(name)
    if not hit:
        for key, val in KNOWN.items():
            if key in [p.lower() for p in path.parts]:
                hit = val
                out["matched_parent"] = key
                break
    if hit:
        out.update({"source": "known", "made_by": hit[0], "holds": hit[1], "safe_to_delete": hit[2]})
        return out
    if use_ai:
        from .ai import OllamaClient
        client = ai_client or OllamaClient()
        if client.available():
            text = client.explain_folder(str(path), samples, human(size))
            if text:
                out.update({"source": "ai", "answer": text})
                return out
    out.update({"source": "none", "answer": "Not sure what made this folder. Look at the file types inside "
                "before deleting anything.", "sample_files": samples[:10]})
    return out
