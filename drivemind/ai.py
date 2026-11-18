"""Optional local LLM (Ollama) for files the rules and the habit learner cannot place.

Privacy: only file NAMES, sizes and extensions are sent, and only to the local
Ollama server unless the user turns on cloud AI. The model must answer with JSON
matching a schema; anything malformed is discarded and the deterministic
classifier result is kept.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional

from .classify import EXT_CATEGORY

CATEGORIES = sorted(set(EXT_CATEGORY.values()) | {"Screenshots", "Recordings", "Projects", "Other"})

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "topic": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["name", "category", "confidence", "reason"],
            },
        }
    },
    "required": ["items"],
}

SYSTEM = (
    "You sort files on a Windows PC. For each file name, pick the best category from the list "
    "and an optional short topic folder (one or two words, Title Case, e.g. 'Finance', 'Thesis', "
    "'Client Acme'). Confidence is 0..1; use below 0.6 when the name gives little information. "
    "Reason is under 12 words. Never invent files. Answer only JSON."
)


@dataclass
class AIGuess:
    category: str
    topic: Optional[str]
    confidence: float
    reason: str


class OllamaClient:
    def __init__(self, url: str = "http://127.0.0.1:11434", model: str = "qwen3:4b", timeout: float = 60):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=1.5) as r:
                tags = json.load(r)
            names = {m.get("name", "") for m in tags.get("models", [])}
            return any(n == self.model or n.startswith(self.model.split(":")[0]) for n in names)
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def _chat(self, prompt: str) -> Optional[dict]:
        body = json.dumps({
            "model": self.model,
            "stream": False,
            "format": SCHEMA,
            "options": {"temperature": 0.1},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(self.url + "/api/chat", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                content = json.load(r)["message"]["content"]
            return json.loads(content)
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            return None

    def classify(self, names: List[str], batch: int = 40) -> Dict[str, AIGuess]:
        out: Dict[str, AIGuess] = {}
        for i in range(0, len(names), batch):
            chunk = names[i:i + batch]
            prompt = "Categories: " + ", ".join(CATEGORIES) + "\nFiles:\n" + "\n".join(chunk)
            data = self._chat(prompt)
            for item in (data or {}).get("items", []):
                name = item.get("name")
                cat = item.get("category")
                if name not in chunk or cat not in CATEGORIES:
                    continue  # schema-valid but wrong: discard
                conf = item.get("confidence", 0)
                conf = max(0.0, min(1.0, float(conf))) if isinstance(conf, (int, float)) else 0.0
                topic = (item.get("topic") or "").strip()[:40] or None
                if topic:
                    topic = "".join(c for c in topic if c not in '<>:"/\\|?*').strip() or None
                out[name] = AIGuess(cat, topic, conf, str(item.get("reason", ""))[:120])
        return out

    def explain_folder(self, path: str, sample_names: List[str], size_human: str) -> Optional[str]:
        """'What is this folder?' — plain-language answer, used by the Explorer menu."""
        body = json.dumps({
            "model": self.model, "stream": False, "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": "Explain in 2-3 short sentences which app likely created this "
                 "Windows folder, what it holds, and whether deleting it is safe. Say 'not sure' if unclear."},
                {"role": "user", "content": f"Folder: {path}\nSize: {size_human}\nSome files: {', '.join(sample_names[:25])}"},
            ],
        }).encode()
        req = urllib.request.Request(self.url + "/api/chat", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.load(r)["message"]["content"].strip()
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            return None
