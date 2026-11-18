"""Organizer: turns a messy folder into a reviewed plan.

Decision chain for every file, first confident answer wins:
    1. user rules            (deterministic, confidence 1.0)
    2. habit learner          (learned from your past approvals)
    3. file-type classifier   (extension + name patterns)
    4. local AI (Ollama)      (only for files the classifier is unsure about)
"""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .ai import OllamaClient
from .classify import classify, destination_folder, smart_name, version_key
from .config import Decision, Settings
from .learner import HabitModel
from .paths import is_protected, is_within, looks_like_project
from .plan import Action, Op, Plan, Status
from .rules import Rule, first_match, load_rules
from .scanner import FileInfo

SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store", "icon\r"}
TEMP_SUFFIXES = {".crdownload", ".part", ".partial", ".download", ".tmp"}


def file_hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _same_content(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return file_hash(a) == file_hash(b)
    except OSError:
        return False


def _entries(source: Path) -> List[os.DirEntry]:
    try:
        with os.scandir(source) as it:
            return list(it)
    except OSError:
        return []


def plan_organize(source: Path, root: Path, settings: Settings, preset: str = "developer",
                  use_ai: Optional[bool] = None, rules: Optional[List[Rule]] = None,
                  ai_client: Optional[OllamaClient] = None) -> Plan:
    """Plan moves for the top level of `source` (e.g. Desktop or Downloads) into `root`."""
    source, root = Path(source).resolve(), Path(root).resolve()
    plan = Plan(title=f"Organize {source.name or source} into {root}", kind="organize")
    rules = load_rules() if rules is None else rules
    habits = HabitModel.from_db() if settings.decision("learn_from_choices") != Decision.NO else HabitModel()
    exclusions = settings.exclusions

    if is_protected(source, exclusions):
        plan.notes.append(f"{source} is a protected location; nothing will be moved.")
        return plan

    files: List[FileInfo] = []
    for e in _entries(source):
        p = Path(e.path)
        if e.name.lower() in SKIP_NAMES or e.name.startswith("~$"):
            continue
        if is_within(root, p):
            continue  # never move the organize root into itself
        if is_protected(p, exclusions):
            continue
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        if e.is_symlink():
            continue
        if e.is_dir(follow_symlinks=False):
            if looks_like_project(p):
                dst = root / destination_folder(preset, "Projects") / e.name
                if not is_within(p, root / destination_folder(preset, "Projects")):
                    plan.actions.append(_action(settings, Op.MOVE, p, dst, _dir_size(p), "Projects",
                                                "project folder (code/project markers found) — moved whole", 0.97,
                                                "organize_moves"))
            continue
        if p.suffix.lower() in TEMP_SUFFIXES:
            continue  # unfinished downloads are handled by the temp cleaner
        files.append(FileInfo(p, st.st_size, st.st_mtime, st.st_atime))

    # ---- decide a category / destination for every file ----------------
    decided: Dict[Path, tuple] = {}
    unsure: List[FileInfo] = []
    for f in files:
        r = first_match(rules, f)
        if r:
            dest_dir = Path(r.destination) if Path(r.destination).is_absolute() else root / r.destination
            decided[f.path] = ("Rule", dest_dir, 1.0, f"matched rule: {r.name}")
            continue
        guess = habits.predict(f.path.name)
        if guess and guess[1] >= 0.7:
            decided[f.path] = ("Learned", Path(guess[0]), guess[1], "similar to files you moved there before")
            continue
        c = classify(f.path)
        if c.confidence < 0.6:
            unsure.append(f)
        decided[f.path] = (c.category, root / destination_folder(preset, c.category, c.topic), c.confidence, c.reason)

    # Local Ollama keeps everything on the PC, so it is used whenever it is running
    # (use_ai=None) unless the caller turns it off. Only file names are sent.
    if unsure and use_ai is not False:
        client = ai_client or OllamaClient(settings.ollama_url, settings.ollama_model)
        if use_ai or client.available():
            guesses = client.classify([f.path.name for f in unsure])
            for f in unsure:
                g = guesses.get(f.path.name)
                if g and g.confidence > decided[f.path][2]:
                    decided[f.path] = (g.category, root / destination_folder(preset, g.category, g.topic),
                                       g.confidence, f"AI: {g.reason}")

    # ---- version stacking: newest copy keeps the main slot --------------
    groups: Dict[tuple, List[FileInfo]] = defaultdict(list)
    versioned = {"Documents", "Spreadsheets", "Presentations", "Design", "Code", "Rule", "Learned"}
    for f in files:
        if decided[f.path][0] in versioned:  # photos named "image (2).png" are not versions
            groups[(str(decided[f.path][1]), version_key(f.path))].append(f)
    older_versions = set()
    for (_, _), members in groups.items():
        if len(members) > 1:
            members.sort(key=lambda x: x.mtime, reverse=True)
            older_versions.update(m.path for m in members[1:])

    # ---- build actions ---------------------------------------------------
    taken: set = set()
    for f in files:
        category, dest_dir, conf, reason = decided[f.path]
        name = f.path.name
        rename_reason = ""
        if settings.decision("smart_rename") != Decision.NO:
            nice = smart_name(f.path)
            if nice:
                name, rename_reason = nice, f"; renamed from {f.path.name}"
        if f.path in older_versions:
            dest_dir = dest_dir / "_versions"
            reason += "; older version of a newer file"
        dst = dest_dir / name
        if dst == f.path:
            continue
        if dst.exists() and _same_content(f.path, dst):
            plan.actions.append(_action(settings, Op.QUARANTINE, f.path, None, f.size, "Duplicates",
                                        f"exact copy already in {dest_dir}", 0.99, "delete_duplicates"))
            continue
        dst = _free_name(dst, taken)
        taken.add(str(dst).lower())
        plan.actions.append(_action(settings, Op.MOVE, f.path, dst, f.size, category,
                                    reason + rename_reason, conf, "organize_moves"))
    plan.notes.append(f"{len(files)} files and {sum(1 for a in plan.actions if a.category == 'Projects')} "
                      f"project folders checked in {source}.")
    return plan


def _free_name(dst: Path, taken: set) -> Path:
    candidate, n = dst, 2
    while candidate.exists() or str(candidate).lower() in taken:
        candidate = dst.with_name(f"{dst.stem} ({n}){dst.suffix}")
        n += 1
    return candidate


def _dir_size(p: Path) -> int:
    total = 0
    for dirpath, _, names in os.walk(p):
        for n in names:
            try:
                total += os.lstat(os.path.join(dirpath, n)).st_size
            except OSError:
                pass
    return total


def _action(settings: Settings, op: Op, src: Path, dst: Optional[Path], size: int, category: str,
            reason: str, confidence: float, option: str) -> Action:
    decision = settings.gate(option, confidence)
    return Action(op=op, src=str(src), dst=str(dst) if dst else None, size=size, category=category,
                  reason=reason, confidence=round(confidence, 3), option=option, decision=decision,
                  status=Status.SKIPPED if decision == Decision.NO else Status.PENDING)


def build_action(settings: Settings, op: Op, src: Path, dst: Optional[Path], size: int, category: str,
                 reason: str, confidence: float, option: str) -> Action:
    """Public helper so the cleaners create actions through the same gate."""
    return _action(settings, op, src, dst, size, category, reason, confidence, option)


def iter_plan_paths(plan: Plan) -> Iterable[str]:
    for a in plan.actions:
        yield a.src
