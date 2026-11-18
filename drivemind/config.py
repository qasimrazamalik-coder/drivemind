"""User settings: one-tap modes plus Yes / Ask / No switches for every action.

Yes  -> DriveMind does it automatically and logs it.
Ask  -> DriveMind proposes it and waits for the user's tap.
No   -> DriveMind never does it.
"""

from __future__ import annotations

import json
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, Field


class Decision(str, Enum):
    YES = "yes"
    ASK = "ask"
    NO = "no"


class Mode(str, Enum):
    SAFE = "safe"
    BALANCED = "balanced"
    AUTOPILOT = "autopilot"
    CUSTOM = "custom"


Y, A, N = Decision.YES, Decision.ASK, Decision.NO

# Every switch DriveMind exposes, with a one-line description for the UI.
OPTION_INFO: Dict[str, str] = {
    "background_watch": "Watch Desktop and Downloads for new files",
    "low_space_alert": "Alert when C: drops below the free-space level",
    "weekly_cache_clean": "Clear caches marked Yes in the Cache Cleaner every week",
    "learn_from_choices": "Learn from your approvals and rejections",
    "weekly_report": "Weekly report with the top 3 fixes",
    "organize_moves": "Move files into organized folders",
    "sort_new_downloads": "Sort each new download into its folder",
    "smart_rename": "Rename unclear file names using their content",
    "archive_inactive_projects": "Zip projects untouched for 90+ days to the archive",
    "move_user_folders": "Move Desktop, Downloads, Documents, Pictures, Videos to another drive",
    "delete_duplicates": "Keep the best copy of duplicates, quarantine the rest",
    "clean_temp_junk": "Remove temporary junk marked Yes in Temporary files",
    "clean_dev_junk": "Remove node_modules, .venv and build folders in projects untouched for 60+ days",
    "desktop_zero": "Move leftover Desktop items to Inbox each night",
    "use_cloud_ai": "Send file names (never contents) to a cloud model",
    "phone_alerts": "Send alerts to your phone",
    "skip_quarantine": "Delete for good instead of the quarantine",
}

MODE_PRESETS: Dict[Mode, Dict[str, Decision]] = {
    Mode.SAFE: {
        "background_watch": A, "low_space_alert": Y, "weekly_cache_clean": A,
        "learn_from_choices": Y, "weekly_report": Y, "organize_moves": A,
        "sort_new_downloads": A, "smart_rename": A, "archive_inactive_projects": A,
        "move_user_folders": A, "delete_duplicates": A, "clean_temp_junk": A, "clean_dev_junk": A,
        "desktop_zero": N, "use_cloud_ai": N, "phone_alerts": N, "skip_quarantine": N,
    },
    Mode.BALANCED: {
        "background_watch": Y, "low_space_alert": Y, "weekly_cache_clean": Y,
        "learn_from_choices": Y, "weekly_report": Y, "organize_moves": A,
        "sort_new_downloads": A, "smart_rename": A, "archive_inactive_projects": A,
        "move_user_folders": A, "delete_duplicates": A, "clean_temp_junk": Y, "clean_dev_junk": A,
        "desktop_zero": N, "use_cloud_ai": N, "phone_alerts": N, "skip_quarantine": N,
    },
    Mode.AUTOPILOT: {
        "background_watch": Y, "low_space_alert": Y, "weekly_cache_clean": Y,
        "learn_from_choices": Y, "weekly_report": Y, "organize_moves": Y,
        "sort_new_downloads": Y, "smart_rename": Y, "archive_inactive_projects": Y,
        "move_user_folders": A, "delete_duplicates": Y, "clean_temp_junk": Y, "clean_dev_junk": Y,
        "desktop_zero": Y, "use_cloud_ai": N, "phone_alerts": N, "skip_quarantine": A,
    },
}

# Switches whose effect is permanent or leaves the PC: never "yes" without the user setting it.
LOCKED_IN_BALANCED = {"skip_quarantine"}


def data_dir() -> Path:
    """Where DriveMind keeps its settings, index, journal and quarantine."""
    override = os.environ.get("DRIVEMIND_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "DriveMind"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "drivemind"
    base.mkdir(parents=True, exist_ok=True)
    return base


class Settings(BaseModel):
    mode: Mode = Mode.BALANCED
    options: Dict[str, Decision] = Field(default_factory=lambda: dict(MODE_PRESETS[Mode.BALANCED]))
    # Per-item choices for the Cache Cleaner and Temporary files tables (id -> decision).
    cache_choices: Dict[str, Decision] = Field(default_factory=dict)
    temp_choices: Dict[str, Decision] = Field(default_factory=dict)
    # AI guesses below this confidence always wait for the user, whatever the mode.
    confidence_threshold: float = 0.8
    low_space_percent: float = 15.0
    quarantine_days: int = 30
    temp_zone_days: int = 7
    stale_project_days: int = 60
    archive_after_days: int = 90
    organize_root: str = ""
    # Folders DriveMind must never touch, beyond the built-in protected list.
    exclusions: List[str] = Field(default_factory=list)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"

    # ---- decisions -------------------------------------------------------
    def decision(self, option: str) -> Decision:
        return self.options.get(option, MODE_PRESETS[Mode.BALANCED].get(option, A))

    def set_mode(self, mode: Mode) -> None:
        if mode == Mode.CUSTOM:
            self.mode = Mode.CUSTOM
            return
        self.mode = mode
        self.options = dict(MODE_PRESETS[mode])

    def set_option(self, option: str, value: Decision) -> None:
        if option not in OPTION_INFO:
            raise KeyError(f"Unknown option: {option}")
        self.options[option] = value
        self.mode = Mode.CUSTOM if self.options != MODE_PRESETS.get(self.mode, {}) else self.mode

    def gate(self, option: str, confidence: float = 1.0) -> Decision:
        """Final decision for one proposed action, applying the confidence rule."""
        d = self.decision(option)
        if d == Decision.YES and confidence < self.confidence_threshold:
            return Decision.ASK
        return d

    # ---- persistence -----------------------------------------------------
    @classmethod
    def path(cls) -> Path:
        return data_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        p = cls.path()
        if p.exists():
            try:
                return cls.model_validate_json(p.read_text(encoding="utf-8"))
            except Exception:
                # A corrupt settings file must never stop the app; keep a copy and start fresh.
                p.rename(p.with_suffix(".corrupt.json"))
        return cls()

    def save(self) -> None:
        tmp = self.path().with_suffix(".tmp")
        tmp.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self.path())

    def export_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def import_json(cls, text: str) -> "Settings":
        return cls.model_validate(json.loads(text))
