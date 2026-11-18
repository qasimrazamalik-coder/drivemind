"""Find files by what they say, not only by name.

Uses SQLite's built-in full-text index (FTS5, BM25 ranking), so it needs no extra
software and stays on the PC. Indexes file names plus the text inside documents:
txt/md/csv/code, Word (.docx), Excel (.xlsx), PowerPoint (.pptx) and PDF (if pypdf is
installed). Queries understand file types and dates:

    "dubai invoice march"        -> words + files changed in March
    "contract pdf 2026"          -> PDFs from 2026 mentioning 'contract'
"""

from __future__ import annotations

import os
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from . import db
from .scanner import iter_files

SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(path UNINDEXED, name, body, tokenize='unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS files_meta (path TEXT PRIMARY KEY, mtime REAL, size INTEGER, ext TEXT, rowid_fts INTEGER);
"""
TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".log", ".ini", ".yaml", ".yml",
            ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".sql", ".java", ".kt", ".cs", ".php", ".go", ".rs",
            ".c", ".cpp", ".h", ".dart", ".lua", ".sh", ".ps1", ".bat", ".tex", ".rtf", ".srt"}
OFFICE = {".docx": ("word/document.xml",), ".xlsx": ("xl/sharedStrings.xml",), ".pptx": ("ppt/slides/",)}
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".next", "build", "dist", "AppData", ".cache"}
MAX_TEXT = 200_000
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
TYPE_WORDS = {"pdf": [".pdf"], "word": [".docx", ".doc"], "docx": [".docx"], "excel": [".xlsx", ".xls", ".csv"],
              "sheet": [".xlsx", ".xls", ".csv"], "slides": [".pptx", ".ppt"], "pptx": [".pptx"],
              "image": [".jpg", ".jpeg", ".png", ".webp", ".heic"], "photo": [".jpg", ".jpeg", ".png", ".heic"],
              "video": [".mp4", ".mkv", ".mov"], "zip": [".zip", ".rar", ".7z"], "txt": [".txt"], "code": [".py", ".js", ".ts"]}
_TAG = re.compile(r"<[^>]+>")


def _conn():
    conn = db.connect()
    conn.executescript(SCHEMA)
    return conn


def name_words(name: str) -> str:
    """'Invoice_DubaiClient-March2026.pdf' -> 'Invoice Dubai Client March 2026 pdf'."""
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    s = re.sub(r"([A-Za-z])(\d)", r"\1 \2", s)
    s = re.sub(r"(\d)([A-Za-z])", r"\1 \2", s)
    return re.sub(r"[_\-.()\[\]]+", " ", s)


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    try:
        if ext in TEXT_EXT:
            with open(path, "rb") as f:
                return f.read(MAX_TEXT).decode("utf-8", errors="ignore")
        if ext in OFFICE:
            parts = []
            with zipfile.ZipFile(path) as z:
                for n in z.namelist():
                    if any(n.startswith(prefix) or n == prefix for prefix in OFFICE[ext]) and n.endswith(".xml"):
                        parts.append(_TAG.sub(" ", z.read(n)[:MAX_TEXT].decode("utf-8", errors="ignore")))
            return " ".join(parts)[:MAX_TEXT]
        if ext == ".pdf":
            try:
                from pypdf import PdfReader  # optional: pip install pypdf
            except ImportError:
                return ""
            out, reader = [], PdfReader(str(path))
            for page in reader.pages[:30]:
                out.append(page.extract_text() or "")
                if sum(map(len, out)) > MAX_TEXT:
                    break
            return " ".join(out)[:MAX_TEXT]
    except Exception:
        return ""
    return ""


def build_index(roots: Iterable[Path], max_file_mb: float = 50) -> Dict:
    """Index new and changed files; drop files that no longer exist. Safe to run often."""
    conn = _conn()
    known = {r["path"]: (r["mtime"], r["size"], r["rowid_fts"]) for r in conn.execute("SELECT * FROM files_meta")}
    seen, added, updated = set(), 0, 0
    t0 = time.time()
    for root in roots:
        for f in iter_files(Path(root), skip_dir=lambda p: p.name in SKIP_DIRS):
            key = str(f.path)
            seen.add(key)
            old = known.get(key)
            if old and old[0] == f.mtime and old[1] == f.size:
                continue
            body = extract_text(f.path) if f.size <= max_file_mb * 1024 * 1024 else ""
            if old:
                conn.execute("DELETE FROM files_fts WHERE rowid=?", (old[2],))
                updated += 1
            else:
                added += 1
            cur = conn.execute("INSERT INTO files_fts(path, name, body) VALUES (?,?,?)",
                               (key, name_words(f.path.name), body))
            conn.execute("INSERT OR REPLACE INTO files_meta(path, mtime, size, ext, rowid_fts) VALUES (?,?,?,?,?)",
                         (key, f.mtime, f.size, f.ext, cur.lastrowid))
    root_strs = [str(Path(r)) for r in roots]
    removed = 0
    for path, (_, _, rid) in known.items():
        if path not in seen and any(path.startswith(r) for r in root_strs):
            conn.execute("DELETE FROM files_fts WHERE rowid=?", (rid,))
            conn.execute("DELETE FROM files_meta WHERE path=?", (path,))
            removed += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) AS n FROM files_meta").fetchone()["n"]
    return {"added": added, "updated": updated, "removed": removed, "total": total, "seconds": round(time.time() - t0, 2)}


def parse_query(q: str) -> Dict:
    words, exts, month, year = [], [], None, None
    for raw in re.findall(r"[\w\-]+", q.lower()):
        if raw in MONTHS:
            month = MONTHS[raw]
        elif re.fullmatch(r"(19|20)\d\d", raw):
            year = int(raw)
        elif raw in TYPE_WORDS:
            exts += TYPE_WORDS[raw]
        elif raw.startswith(".") or raw in {"file", "files", "the", "a", "an", "of", "from", "in", "my", "for", "with"}:
            continue
        else:
            words.append(raw.replace("-", " "))
    return {"words": words, "exts": exts, "month": month, "year": year}


def search(q: str, limit: int = 30) -> List[Dict]:
    conn = _conn()
    p = parse_query(q)
    rows = []
    if p["words"]:
        match = " AND ".join(f'"{w}"*' for w in p["words"])
        sql = ("SELECT files_fts.path AS path, bm25(files_fts, 0.0, 8.0, 1.0) AS score, "
               "snippet(files_fts, 2, '[', ']', ' … ', 12) AS snip, m.mtime, m.size, m.ext "
               "FROM files_fts JOIN files_meta m ON m.rowid_fts = files_fts.rowid "
               "WHERE files_fts MATCH ? ORDER BY score LIMIT ?")
        rows = conn.execute(sql, (match, limit * 5)).fetchall()
    elif p["exts"] or p["month"] or p["year"]:
        rows = conn.execute("SELECT path, 0 AS score, '' AS snip, mtime, size, ext FROM files_meta "
                            "ORDER BY mtime DESC LIMIT ?", (5000,)).fetchall()
    out = []
    for r in rows:
        if p["exts"] and r["ext"] not in p["exts"]:
            continue
        dt = datetime.fromtimestamp(r["mtime"])
        if p["month"] and dt.month != p["month"]:
            continue
        if p["year"] and dt.year != p["year"]:
            continue
        if not Path(r["path"]).exists():
            continue
        out.append({"path": r["path"], "name": Path(r["path"]).name, "size": r["size"], "mtime": r["mtime"],
                    "snippet": (r["snip"] or "").strip()})
        if len(out) >= limit:
            break
    return out


def default_roots() -> List[Path]:
    from .paths import user_folders
    return [p for k, p in user_folders().items() if k != "Music" and p.exists()]
