"""Habit learner: learns where YOU put files from every approve / reject / manual move.

A small naive-Bayes style model over two features (file extension and name tokens),
trained online from the feedback table. It only speaks when it has enough evidence,
and its confidence feeds the same Yes / Ask / No gate as everything else.
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Optional, Tuple

from . import db

TOKEN = re.compile(r"[a-z]{3,}")
STOP = {"the", "and", "for", "copy", "final", "new", "file", "untitled", "document", "image", "img", "screenshot"}


def tokens(name: str):
    return [t for t in TOKEN.findall(Path(name).stem.lower()) if t not in STOP]


def record(name: str, category: str, destination: str, accepted: bool) -> None:
    conn = db.connect()
    conn.execute("INSERT INTO feedback(ts, ext, name, category, destination, accepted) VALUES (?,?,?,?,?,?)",
                 (time.time(), Path(name).suffix.lower(), name, category, destination, int(accepted)))
    conn.commit()


class HabitModel:
    def __init__(self) -> None:
        self.dest_count: Counter = Counter()
        self.ext_dest: Dict[str, Counter] = defaultdict(Counter)
        self.tok_dest: Dict[str, Counter] = defaultdict(Counter)
        self.rejected: Counter = Counter()      # (ext, dest) pairs the user said no to
        self.n = 0

    @classmethod
    def from_db(cls) -> "HabitModel":
        m = cls()
        for r in db.connect().execute("SELECT ext, name, destination, accepted FROM feedback"):
            if r["accepted"]:
                m.add(r["name"], r["destination"])
            else:
                m.rejected[(r["ext"], r["destination"])] += 1
        return m

    def add(self, name: str, destination: str) -> None:
        ext = Path(name).suffix.lower()
        self.dest_count[destination] += 1
        self.ext_dest[ext][destination] += 1
        for t in set(tokens(name)):
            self.tok_dest[t][destination] += 1
        self.n += 1

    def predict(self, name: str, min_samples: int = 3) -> Optional[Tuple[str, float]]:
        """(destination, confidence) or None when the model has not seen enough."""
        if self.n < min_samples:
            return None
        ext = Path(name).suffix.lower()
        toks = set(tokens(name))
        k = len(self.dest_count)
        scores = {}
        for dest, cnt in self.dest_count.items():
            if self.rejected[(ext, dest)] >= 2:
                continue
            s = math.log(cnt / self.n)
            s += math.log((self.ext_dest[ext][dest] + 1) / (cnt + k))
            for t in toks:
                if t in self.tok_dest:
                    s += math.log((self.tok_dest[t][dest] + 1) / (cnt + k))
            scores[dest] = s
        if not scores:
            return None
        mx = max(scores.values())
        exp = {d: math.exp(v - mx) for d, v in scores.items()}
        total = sum(exp.values())
        best = max(exp, key=exp.get)
        conf = exp[best] / total
        support = self.ext_dest[ext][best] + sum(self.tok_dest[t][best] for t in toks if t in self.tok_dest)
        if support < min_samples:
            return None
        return best, round(conf, 3)
