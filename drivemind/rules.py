"""User rules: deterministic, instant, no AI at run time.

A rule can be written as JSON or as a plain sentence that is compiled once:
    "anything with invoice from Downloads goes to Work/Invoices"
    ".apk files go to Installers/Android"
    "screenshots older than 90 days go to Archive/Screenshots"
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from .config import data_dir
from .scanner import FileInfo


class RuleMatch(BaseModel):
    extensions: List[str] = Field(default_factory=list)      # [".pdf", ".docx"]
    name_contains: List[str] = Field(default_factory=list)   # any of these words
    source_contains: str = ""                                # e.g. "Downloads"
    older_than_days: Optional[float] = None
    larger_than_mb: Optional[float] = None


class Rule(BaseModel):
    name: str
    match: RuleMatch
    destination: str          # relative to the organize root, or an absolute path
    enabled: bool = True

    def matches(self, f: FileInfo) -> bool:
        m = self.match
        name = f.path.name.lower()
        if m.extensions and f.ext not in [e.lower() if e.startswith(".") else "." + e.lower() for e in m.extensions]:
            return False
        if m.name_contains and not any(w.lower() in name for w in m.name_contains):
            return False
        if m.source_contains and m.source_contains.lower() not in str(f.path.parent).lower():
            return False
        if m.older_than_days is not None and (time.time() - f.mtime) / 86400 < m.older_than_days:
            return False
        if m.larger_than_mb is not None and f.size < m.larger_than_mb * 1024 * 1024:
            return False
        return True


def rules_path() -> Path:
    return data_dir() / "rules.json"


def load_rules() -> List[Rule]:
    p = rules_path()
    if not p.exists():
        return []
    try:
        return [Rule.model_validate(r) for r in json.loads(p.read_text(encoding="utf-8"))]
    except Exception:
        return []


def save_rules(rules: List[Rule]) -> None:
    rules_path().write_text(json.dumps([r.model_dump() for r in rules], indent=2), encoding="utf-8")


def first_match(rules: List[Rule], f: FileInfo) -> Optional[Rule]:
    for r in rules:
        if r.enabled and r.matches(f):
            return r
    return None


_DEST = re.compile(r"\b(?:goes?|go|move[sd]?|put|send)\s+(?:them\s+)?(?:to|into|in)\s+(.+)$", re.I)
_EXT = re.compile(r"(?<![\w])\.([a-z0-9]{1,6})\b", re.I)
_WITH = re.compile(r"\b(?:with|containing|named|called)\s+[\"']?([\w\- ]+?)[\"']?(?=\s+(?:from|in|older|larger|bigger|goes?|go|move|put|send)\b|$)", re.I)
_FROM = re.compile(r"\bfrom\s+(?:my\s+|the\s+)?([\w\- ]+?)(?=\s+(?:older|larger|bigger|goes?|go|move|put|send)\b|$)", re.I)
_OLDER = re.compile(r"older than\s+(\d+(?:\.\d+)?)\s*(day|week|month|year)s?", re.I)
_LARGER = re.compile(r"(?:larger|bigger) than\s+(\d+(?:\.\d+)?)\s*(kb|mb|gb)", re.I)
_KIND = {"screenshots": "screenshot", "invoices": "invoice", "receipts": "receipt"}


def parse_rule(text: str) -> Rule:
    """Compile a plain-English rule. Raises ValueError when no destination is given."""
    t = text.strip().rstrip(".")
    dm = _DEST.search(t)
    if not dm:
        raise ValueError("Say where the files should go, e.g. '... go to Work/Invoices'")
    dest = dm.group(1).strip().strip("\"'").replace("\\", "/")
    head = t[:dm.start()]
    m = RuleMatch()
    m.extensions = ["." + e.lower() for e in _EXT.findall(head)]
    w = _WITH.search(head)
    if w:
        m.name_contains = [w.group(1).strip()]
    for plural, word in _KIND.items():
        if re.search(rf"\b{plural}\b", head, re.I) and not m.name_contains:
            m.name_contains = [word]
    f = _FROM.search(head)
    if f:
        m.source_contains = f.group(1).strip()
    o = _OLDER.search(head)
    if o:
        mult = {"day": 1, "week": 7, "month": 30, "year": 365}[o.group(2).lower()]
        m.older_than_days = float(o.group(1)) * mult
    l = _LARGER.search(head)
    if l:
        mult = {"kb": 1 / 1024, "mb": 1, "gb": 1024}[l.group(2).lower()]
        m.larger_than_mb = float(l.group(1)) * mult
    if not (m.extensions or m.name_contains or m.source_contains or m.older_than_days or m.larger_than_mb):
        raise ValueError("Say which files: a type (.pdf), a word ('with invoice'), a folder ('from Downloads') or an age")
    return Rule(name=t[:60], match=m, destination=dest)
