"""DriveMind assistant: a RAG chatbot over your drive and your files.

1. Route: common questions go straight to DriveMind's own tools (space, cleaning,
   finding files, duplicates, disk health, startup) — English or Roman Urdu.
2. Retrieve: for anything else, the most relevant passages are pulled from the local
   full-text index of your documents (see search.py).
3. Generate: if a local model is running (Ollama), it writes the answer using ONLY those
   facts and passages, citing them as [1], [2]. Without a model, DriveMind answers from
   the same facts directly, so the assistant always works and never invents files.

Nothing leaves the PC: retrieval is local and the model is local.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from .config import Settings
from .scanner import human

INTENTS = [
    ("space", r"\b(space|full|storage|eating|taking|big(gest)?|largest|jagah|bhar|kya bhara|disk usage|free)\b"),
    ("clean", r"\b(clean|cache|junk|temp|clear|saaf|safai|free up)\b"),
    ("find", r"\b(find|where|search|locate|kahan|kidhar|dhoond|dhundo|look for)\b"),
    ("dupes", r"\b(duplicate|copies|copy|same file|dubara)\b"),
    ("health", r"\b(health|ssd|smart|wear|temperature|failing|disk health)\b"),
    ("startup", r"\b(startup|start up|boot|slow start|on start)\b"),
    ("projects", r"\b(project|node_modules|venv|archive|old code)\b"),
]


def route(q: str) -> str:
    low = q.lower()
    for name, pattern in INTENTS:
        if re.search(pattern, low):
            return name
    return "rag"


def _drive_facts(settings: Settings) -> Dict:
    from .disk import drive_status, system_drive
    st = drive_status(system_drive(), settings.low_space_percent)
    return st.to_dict() if st else {}


def _keywords(q: str) -> str:
    stop = {"find", "where", "search", "locate", "my", "the", "a", "is", "are", "file", "files", "kahan", "hai",
            "mera", "meri", "mere", "ki", "ka", "ke", "what", "which", "show", "me", "please", "for", "about",
            "did", "i", "put", "go", "dhoond", "dhundo", "look", "do", "have", "any", "tell"}
    return " ".join(w for w in re.findall(r"[\w\-]+", q.lower()) if w not in stop)


def gather(q: str, intent: str, settings: Settings) -> Dict:
    """Facts + sources for the answer. Every item here is real data from this PC."""
    facts: List[str] = []
    sources: List[Dict] = []
    actions: List[Dict] = []
    d = _drive_facts(settings) if intent in ("space", "clean", "health", "rag") else {}
    if d:
        facts.append(f"Drive {d['drive']}: {human(d['free'])} free of {human(d['used'] + d['free'])} "
                     f"({d['free_percent']}% free, health {d['score']}/100, status {d['status']}).")
    if intent == "space":
        from .api import last_scan
        sc = last_scan()
        if sc:
            facts.append("Biggest folders in the last scan of " + sc["root"] + ": " +
                         "; ".join(f"{Path(c['path']).name} {human(c['size'])}" for c in sc["children"][:6]) + ".")
            if sc.get("stale_large"):
                facts.append(f"{len(sc['stale_large'])} files over 100 MB were not opened for 6+ months, e.g. " +
                             ", ".join(f"{Path(f['path']).name} ({human(f['size'])})" for f in sc["stale_large"][:3]) + ".")
        else:
            actions.append({"label": "Scan the drive", "kind": "view", "target": "home"})
        from .advisor import advise
        for t in advise(settings)["tips"]:
            facts.append(f"Fix: {t['title']} — {t['detail']}")
    elif intent == "clean":
        from .cleaner import cache_report
        rows = [r for r in cache_report(settings) if r["size"] and not r["display_only"]]
        total = sum(r["size"] for r in rows)
        facts.append(f"Caches that can be cleared: {human(total)} — " +
                     ", ".join(f"{r['name']} {human(r['size'])} ({r['choice']})" for r in rows[:6]) + ".")
        actions.append({"label": "Review a cache clean", "kind": "view", "target": "caches"})
        actions.append({"label": "Find temporary junk", "kind": "view", "target": "temp"})
    elif intent == "dupes":
        facts.append("Duplicates are matched by content (size, then hashes), and the copy in the most organized folder is kept.")
        actions.append({"label": "Find duplicates", "kind": "view", "target": "more"})
    elif intent == "health":
        from .ssd import disk_health
        disks = disk_health()
        facts += [f"Disk {x['name']}: {x['status']} — {'; '.join(x['notes'])}" for x in disks] or \
            ["Disk health counters are read from Windows; none were reported on this machine."]
    elif intent == "startup":
        from .winapps import startup_apps
        items = startup_apps()
        on = [i["name"] for i in items if i["enabled"]]
        facts.append(f"{len(on)} apps start with Windows: {', '.join(on[:10])}." if items
                     else "Startup apps are read from Windows; none were found here.")
        actions.append({"label": "Manage startup apps", "kind": "view", "target": "apps"})
    elif intent == "projects":
        actions.append({"label": "Find idle projects", "kind": "view", "target": "more"})
        facts.append("Old project dependencies (node_modules, .venv) can be removed and restored with one command; "
                     "idle projects can be archived as zips with full git history.")
    if intent in ("find", "rag"):
        from .executor import where_is
        from .search import search
        kw = _keywords(q)
        hits = search(kw, 6, any_word=True) if kw else []
        for h in hits:
            sources.append({"path": h["path"], "name": h["name"], "snippet": h["snippet"], "mtime": h["mtime"]})
        if intent == "find" and kw:
            moved = []
            for w in (x for x in where_is(kw.split()[0], 20) if not x["undone"]):
                line = f"DriveMind moved {Path(w['src']).name} to {w['dst']}."
                if line not in moved:
                    moved.append(line)
            facts += moved[:3]
        if not hits:
            facts.append("No indexed file matched. The index refreshes every 6 hours, or press 'Refresh index now' on Search.")
    return {"facts": facts, "sources": sources, "actions": actions}


SYSTEM = ("You are DriveMind, a helpful assistant for the user's Windows PC files and storage. "
          "Answer ONLY from the FACTS and SOURCES given. Cite sources as [1], [2]. If the answer is not "
          "there, say you could not find it and suggest a search. Never invent files, sizes or paths. "
          "Be brief: 2-5 short sentences or a short list. Reply in the user's language (English or Roman Urdu).")


def _ollama(settings: Settings, question: str, ctx: Dict, history: List[Dict]) -> Optional[str]:
    facts = "\n".join(f"- {f}" for f in ctx["facts"]) or "- (none)"
    srcs = "\n".join(f"[{i}] {s['name']} ({s['path']}): {s['snippet'] or '(name match)'}"
                     for i, s in enumerate(ctx["sources"], 1)) or "(none)"
    msgs = [{"role": "system", "content": SYSTEM}]
    for h in history[-6:]:
        if h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
            msgs.append({"role": h["role"], "content": h["content"][:1500]})
    msgs.append({"role": "user", "content": f"FACTS:\n{facts}\n\nSOURCES:\n{srcs}\n\nQUESTION: {question}"})
    body = json.dumps({"model": settings.ollama_model, "stream": False, "messages": msgs,
                       "options": {"temperature": 0.2}}).encode()
    req = urllib.request.Request(settings.ollama_url.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            text = json.load(r)["message"]["content"]
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip() or None
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None


def _plain(intent: str, ctx: Dict) -> str:
    """Answer without a model: the facts, stated plainly."""
    lines = list(ctx["facts"])
    if ctx["sources"]:
        lines.append("Most relevant files:")
        lines += [f"[{i}] {s['name']}" + (f" — “{s['snippet'][:90]}”" if s["snippet"] else "")
                  for i, s in enumerate(ctx["sources"], 1)]
    if intent == "rag" and not ctx["sources"]:
        lines.append("I could not find that in your indexed files. Try different words, or ask about space, cleaning, "
                     "duplicates, disk health or startup apps.")
    return "\n".join(lines) or "Ask me about your drive space, cleaning, finding a file, duplicates or disk health."


def answer(question: str, history: Optional[List[Dict]] = None, use_ai: Optional[bool] = None,
           settings: Optional[Settings] = None) -> Dict:
    settings = settings or Settings.load()
    q = (question or "").strip()[:500]
    if not q:
        return {"answer": "Ask me anything about your files or drive.", "sources": [], "actions": [], "intent": "none", "ai": False}
    intent = route(q)
    ctx = gather(q, intent, settings)
    text, used_ai = None, False
    if use_ai is not False:
        from .ai import OllamaClient
        if use_ai or OllamaClient(settings.ollama_url, settings.ollama_model).available():
            text = _ollama(settings, q, ctx, history or [])
            used_ai = text is not None
    return {"answer": text or _plain(intent, ctx), "sources": ctx["sources"], "actions": ctx["actions"],
            "intent": intent, "ai": used_ai}
