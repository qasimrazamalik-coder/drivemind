"""Plan and Action: every change DriveMind makes is described here first.

Nothing touches the disk until a plan is applied, and only actions whose decision
is YES (from settings) or that the user approved are executed.
"""

from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from . import db
from .config import Decision


class Op(str, Enum):
    MOVE = "move"              # move/rename a file or folder (src -> dst)
    QUARANTINE = "quarantine"  # reversible delete: move into DriveMind's quarantine
    DELETE_CACHE = "delete_cache"  # remove regenerable cache contents (src folder or file)
    RELOCATE_FOLDER = "relocate_folder"  # move a Windows user folder (Desktop ...) to another drive


class Status(str, Enum):
    PENDING = "pending"        # waiting for the user (decision = ask)
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"        # decision = no
    DONE = "done"
    FAILED = "failed"
    UNDONE = "undone"


class Action(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    op: Op
    src: str
    dst: Optional[str] = None
    size: int = 0
    category: str = ""
    reason: str = ""
    confidence: float = 1.0
    option: str = "organize_moves"      # which settings switch governs this action
    decision: Decision = Decision.ASK
    status: Status = Status.PENDING
    error: Optional[str] = None

    @property
    def runnable(self) -> bool:
        return (self.decision == Decision.YES and self.status == Status.PENDING) or self.status == Status.APPROVED


class Plan(BaseModel):
    id: str = Field(default_factory=lambda: time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4])
    title: str
    kind: str                           # organize | clean | temp | duplicates | devjunk
    created: float = Field(default_factory=time.time)
    status: str = "proposed"
    actions: List[Action] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)

    def summary(self) -> Dict:
        by_status: Dict[str, int] = {}
        by_cat: Dict[str, Dict[str, int]] = {}
        for a in self.actions:
            by_status[a.status.value] = by_status.get(a.status.value, 0) + 1
            c = by_cat.setdefault(a.category or a.op.value, {"count": 0, "bytes": 0})
            c["count"] += 1
            c["bytes"] += a.size
        frees = sum(a.size for a in self.actions
                    if a.op in (Op.QUARANTINE, Op.DELETE_CACHE) and a.status not in (Status.REJECTED, Status.SKIPPED))
        return {
            "actions": len(self.actions),
            "bytes": sum(a.size for a in self.actions),
            "frees_bytes": frees,
            "auto": sum(1 for a in self.actions if a.decision == Decision.YES and a.status == Status.PENDING),
            "waiting": sum(1 for a in self.actions if a.decision == Decision.ASK and a.status == Status.PENDING),
            "by_status": by_status,
            "by_category": by_cat,
        }

    def get(self, action_id: str) -> Optional[Action]:
        return next((a for a in self.actions if a.id == action_id), None)

    def set_status(self, ids: List[str], status: Status) -> int:
        n = 0
        for a in self.actions:
            if (not ids or a.id in ids) and a.status in (Status.PENDING, Status.APPROVED, Status.REJECTED):
                a.status = status
                n += 1
        return n

    # ---- persistence -----------------------------------------------------
    def save(self) -> None:
        conn = db.connect()
        conn.execute("INSERT OR REPLACE INTO plans(id, ts, title, status, json) VALUES (?,?,?,?,?)",
                     (self.id, self.created, self.title, self.status, self.model_dump_json()))
        conn.commit()

    @classmethod
    def load(cls, plan_id: str) -> Optional["Plan"]:
        row = db.connect().execute("SELECT json FROM plans WHERE id=?", (plan_id,)).fetchone()
        return cls.model_validate_json(row["json"]) if row else None

    @classmethod
    def recent(cls, limit: int = 20) -> List[Dict]:
        rows = db.connect().execute("SELECT id, ts, title, status, json FROM plans ORDER BY ts DESC LIMIT ?",
                                    (limit,)).fetchall()
        out = []
        for r in rows:
            p = cls.model_validate_json(r["json"])
            out.append({"id": r["id"], "ts": r["ts"], "title": r["title"], "status": r["status"],
                        "kind": p.kind, "summary": p.summary()})
        return out
