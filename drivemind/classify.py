"""Deterministic file classifier and the organize layouts (presets).

This is the fast path: it handles the large majority of files with no AI call.
The AI and the habit learner only step in for what this cannot place confidently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

EXT_CATEGORY: Dict[str, str] = {}


def _reg(cat: str, exts: str) -> None:
    for e in exts.split():
        EXT_CATEGORY["." + e] = cat


_reg("Documents", "pdf doc docx odt rtf txt md pages tex")
_reg("Spreadsheets", "xls xlsx xlsm ods csv tsv numbers")
_reg("Presentations", "ppt pptx odp key")
_reg("Images", "jpg jpeg png gif webp heic heif bmp tif tiff svg ico raw cr2 nef arw dng avif")
_reg("Videos", "mp4 mkv mov avi webm wmv flv m4v 3gp mts")
_reg("Audio", "mp3 wav m4a aac ogg opus flac wma amr")
_reg("Archives", "zip rar 7z tar gz tgz bz2 xz zst iso")
_reg("Installers", "exe msi msix msixbundle appx appxbundle apk aab xapk dmg pkg deb rpm")
_reg("Code", "py ipynb js mjs cjs ts tsx jsx html css scss json yaml yml xml sql sh ps1 bat java kt go rs c cpp h cs php rb dart swift lua luau")
_reg("Design", "psd ai fig xd sketch blend fbx obj glb gltf stl indd afdesign afphoto procreate")
_reg("Fonts", "ttf otf woff woff2")
_reg("Ebooks", "epub mobi azw3 djvu")
_reg("Torrents", "torrent")

# Name keywords that refine a category into a topic folder.
TOPIC_KEYWORDS = [
    ("Finance", r"invoice|receipt|bill|payment|bank|statement|salary|payslip|tax|quotation|quote"),
    ("CV", r"\bcv\b|resume|curriculum|cover[ _-]?letter"),
    ("Contracts", r"contract|agreement|\bnda\b|terms|proposal|offer[ _-]?letter"),
    ("Study", r"assignment|lecture|thesis|semester|quiz|exam|notes|slides|syllabus|research|paper|fyp"),
    ("IDs", r"passport|\bcnic\b|national[ _-]?id|license|licence|visa|emirates[ _-]?id"),
]

SCREENSHOT_RE = re.compile(r"^(screenshot|screen shot|screen_shot|capture|snip|snapshot|scr_)", re.I)
RECORDING_RE = re.compile(r"(screen ?recording|recording|obs|clip)", re.I)
CAMERA_RE = re.compile(r"^(?:IMG|VID|PXL|DSC|MVIMG)[_-]?(\d{8})[_-](\d{6})", re.I)
WHATSAPP_RE = re.compile(r"^(IMG|VID|AUD|PTT|DOC)-(\d{8})-WA(\d{4})", re.I)


@dataclass
class Classification:
    category: str
    topic: Optional[str]
    confidence: float
    reason: str


def classify(path: Path) -> Classification:
    name, ext = path.name, path.suffix.lower()
    stem = path.stem
    cat = EXT_CATEGORY.get(ext)
    if cat == "Images" and SCREENSHOT_RE.match(stem):
        return Classification("Screenshots", None, 0.97, "name looks like a screenshot")
    if cat == "Videos" and RECORDING_RE.search(stem):
        return Classification("Recordings", None, 0.85, "name looks like a screen recording")
    if cat in ("Documents", "Spreadsheets", "Presentations", "Images"):
        low = re.sub(r"[_\-.]+", " ", stem.lower())  # "Qasim_CV_2026" -> "qasim cv 2026"
        for topic, pattern in TOPIC_KEYWORDS:
            if re.search(pattern, low):
                return Classification(cat, topic, 0.9, f"file type {ext} and the word '{re.search(pattern, low).group(0)}' in the name")
    if cat:
        return Classification(cat, None, 0.95, f"file type {ext}")
    if not ext:
        return Classification("Other", None, 0.4, "no file extension")
    return Classification("Other", None, 0.5, f"unknown file type {ext}")


# ---------------------------------------------------------------- layouts ---
# Each preset maps a category (and optional topic) to a folder under the organize root.
PRESETS: Dict[str, Dict[str, str]] = {
    "developer": {
        "Projects": "Projects", "Code": "Projects/_snippets",
        "Documents": "Documents", "Documents/Finance": "Work/Finance", "Documents/CV": "Work/CV",
        "Documents/Contracts": "Work/Contracts", "Documents/Study": "Study", "Documents/IDs": "Personal/IDs",
        "Spreadsheets": "Work/Sheets", "Spreadsheets/Finance": "Work/Finance",
        "Presentations": "Work/Slides", "Presentations/Study": "Study",
        "Images": "Media/Images", "Images/IDs": "Personal/IDs", "Screenshots": "Media/Screenshots",
        "Videos": "Media/Videos", "Recordings": "Media/Recordings", "Audio": "Media/Audio",
        "Design": "Design", "Fonts": "Design/Fonts", "Archives": "Archives", "Installers": "Installers",
        "Ebooks": "Library", "Torrents": "Inbox", "Other": "Inbox",
    },
    "student": {
        "Projects": "Projects", "Code": "Projects/_snippets",
        "Documents": "Documents", "Documents/Study": "University", "Presentations": "University/Slides",
        "Spreadsheets": "Documents/Sheets", "Documents/CV": "Career", "Documents/IDs": "Personal/IDs",
        "Images": "Pictures", "Screenshots": "Pictures/Screenshots", "Videos": "Videos",
        "Recordings": "Videos/Recordings", "Audio": "Music", "Ebooks": "Books",
        "Archives": "Archives", "Installers": "Installers", "Other": "Inbox",
    },
    "freelancer": {
        "Projects": "Clients/_projects", "Documents": "Documents", "Documents/Finance": "Business/Invoices",
        "Documents/Contracts": "Business/Contracts", "Documents/CV": "Business/Profile",
        "Spreadsheets": "Business/Sheets", "Presentations": "Business/Pitches", "Design": "Clients/_design",
        "Images": "Media/Images", "Screenshots": "Media/Screenshots", "Videos": "Media/Videos",
        "Audio": "Media/Audio", "Archives": "Archives", "Installers": "Installers", "Other": "Inbox",
    },
    "by_type": {},       # every category gets a folder with its own name
    "minimal": {
        "Projects": "Projects", "Documents": "Documents", "Spreadsheets": "Documents",
        "Presentations": "Documents", "Ebooks": "Documents", "Images": "Media", "Screenshots": "Media",
        "Videos": "Media", "Recordings": "Media", "Audio": "Media", "Installers": "Installers",
        "Archives": "Archives", "Other": "Other",
    },
    "johnny_decimal": {
        "Projects": "10-19 Work/11 Projects", "Code": "10-19 Work/11 Projects/_snippets",
        "Documents": "20-29 Documents/21 General", "Documents/Finance": "20-29 Documents/22 Finance",
        "Documents/CV": "20-29 Documents/23 Career", "Documents/Contracts": "20-29 Documents/24 Contracts",
        "Documents/Study": "30-39 Study/31 Courses", "Documents/IDs": "20-29 Documents/25 IDs",
        "Spreadsheets": "20-29 Documents/26 Sheets", "Presentations": "20-29 Documents/27 Slides",
        "Images": "40-49 Media/41 Images", "Screenshots": "40-49 Media/42 Screenshots",
        "Videos": "40-49 Media/43 Videos", "Recordings": "40-49 Media/44 Recordings",
        "Audio": "40-49 Media/45 Audio", "Design": "40-49 Media/46 Design",
        "Archives": "90-99 System/91 Archives", "Installers": "90-99 System/92 Installers",
        "Other": "00-09 Inbox/01 Unsorted",
    },
}


def destination_folder(preset: str, category: str, topic: Optional[str] = None) -> str:
    layout = PRESETS.get(preset, PRESETS["developer"])
    if preset == "by_type":
        return f"{category}/{topic}" if topic else category
    if topic and f"{category}/{topic}" in layout:
        return layout[f"{category}/{topic}"]
    if category in layout:
        base = layout[category]
        return f"{base}/{topic}" if topic and preset != "minimal" else base
    return layout.get("Other", "Inbox")


# ---------------------------------------------------------- smart rename ---
def smart_name(path: Path) -> Optional[str]:
    """Readable name for camera / WhatsApp files; None when the name is already fine."""
    stem, ext = path.stem, path.suffix.lower()
    m = WHATSAPP_RE.match(stem)
    if m:
        kind = {"IMG": "photo", "VID": "video", "AUD": "audio", "PTT": "voice note", "DOC": "document"}[m.group(1).upper()]
        d = _date(m.group(2))
        return f"{d} WhatsApp {kind} {m.group(3)}{ext}" if d else None
    m = CAMERA_RE.match(stem)
    if m:
        d = _date(m.group(1))
        t = m.group(2)
        kind = "Video" if ext in (".mp4", ".mov", ".3gp") else "Photo"
        return f"{d} {t[:2]}.{t[2:4]}.{t[4:6]} {kind}{ext}" if d else None
    return None


def _date(yyyymmdd: str) -> Optional[str]:
    try:
        return datetime.strptime(yyyymmdd, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


# ------------------------------------------------------ version stacking ---
VERSION_WORDS = re.compile(r"(\b(final|finale|latest|new|updated|revised|copy|draft|edit(ed)?)\b|\bv\d+(\.\d+)*\b|\(\d+\)|-\s*copy|_\d+$)", re.I)


def version_key(path: Path) -> str:
    """'report final FINAL (2).docx' and 'report v3.docx' share the key 'report|.docx'."""
    s = path.stem.lower()
    for _ in range(4):
        s = VERSION_WORDS.sub(" ", s)
    s = re.sub(r"[\s_\-.]+", " ", s).strip()
    return f"{s}|{path.suffix.lower()}"
