"""Background guardian loop: snapshots, low-space alerts, Downloads triage, scheduled cleans.

Runs inside the local server (or `drivemind watch`). Heavy jobs wait while the laptop is
on battery or a fullscreen game is running.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

from . import db
from .cleaner import plan_cache_clean, plan_temp_clean
from .config import Decision, Settings
from .disk import drive_status, list_drives, record_snapshot, system_drive
from .executor import apply_plan, purge_quarantine
from .paths import user_folders
from .plan import Status
from .planner import plan_organize
from .scanner import human
from .winapi import is_fullscreen_app_running, is_on_battery


def notify(level: str, title: str, body: str = "", plan_id: Optional[str] = None) -> None:
    conn = db.connect()
    recent = conn.execute("SELECT id FROM notices WHERE title=? AND ts>?", (title, time.time() - 6 * 3600)).fetchone()
    if recent:
        return  # never repeat the same alert within 6 hours
    conn.execute("INSERT INTO notices(ts, level, title, body, plan_id) VALUES (?,?,?,?,?)",
                 (time.time(), level, title, body, plan_id))
    conn.commit()
    from . import events
    events.publish("notices", level=level, title=title)
    _toast(title, body)


def _toast(title: str, body: str) -> None:
    try:  # optional: pip install win11toast
        from win11toast import toast  # type: ignore
        toast(title, body, app_id="DriveMind")
    except Exception:
        pass


class Guardian:
    def __init__(self, interval_s: float = 300):
        self.interval = interval_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_run = self._load_state()

    @staticmethod
    def _state_path() -> Path:
        from .config import data_dir
        return data_dir() / "guardian_state.json"

    def _load_state(self) -> dict:
        import json
        try:
            return json.loads(self._state_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"weekly_clean": time.time()}  # first scheduled clean one week after install

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="drivemind-guardian", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _due(self, key: str, every_s: float) -> bool:
        if time.time() - self.last_run.get(key, 0) >= every_s:
            self.last_run[key] = time.time()
            import json
            try:
                self._state_path().write_text(json.dumps(self.last_run), encoding="utf-8")
            except OSError:
                pass
            return True
        return False

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:  # the guardian must never crash the app
                notify("watch", "DriveMind background job failed", str(e)[:200])
            self._stop.wait(self.interval)

    def tick(self) -> None:
        s = Settings.load()
        for d in list_drives():
            record_snapshot(d)
        from . import events
        events.publish("status", source="guardian")
        if s.decision("low_space_alert") != Decision.NO:
            st = drive_status(system_drive(), s.low_space_percent)
            if st and st.status != "good":
                when = f" At this rate it is full in about {st.days_to_full:.0f} days." if st.days_to_full else ""
                notify(st.status, f"Drive {st.drive} is {100 - st.free_percent:.0f}% full",
                       f"{human(st.free)} free.{when} Open DriveMind for the top fixes.")
        heavy_ok = not is_on_battery() and not is_fullscreen_app_running()

        if s.decision("sort_new_downloads") != Decision.NO and s.organize_root and self._due("downloads", 120):
            dl = user_folders()["Downloads"]
            if dl.exists():
                p = plan_organize(dl, Path(s.organize_root), s, use_ai=None)
                # only files that have stopped changing for a minute (finished downloads)
                for a in p.actions:
                    try:
                        if time.time() - Path(a.src).stat().st_mtime < 60:
                            a.status = Status.SKIPPED
                    except OSError:
                        pass
                if s.decision("sort_new_downloads") == Decision.YES:
                    apply_plan(p, s)
                elif p.summary()["waiting"]:
                    p.save()
                    notify("info", f"{p.summary()['waiting']} new downloads ready to sort",
                           "Review them in DriveMind.", p.id)

        if heavy_ok and self._due("search_index", 6 * 3600):
            from .search import build_index, default_roots
            build_index(default_roots())

        if self._due("ssd", 86400):
            from .ssd import disk_health
            for d in disk_health():
                if d["status"] != "good":
                    notify(d["status"], f"Disk check: {d['name']} needs attention", "; ".join(d["notes"])[:200])

        # Weekly report: one notice (and phone notification) summing up the week. Starts a week
        # after install rather than reporting an empty week on day one.
        self.last_run.setdefault("weekly_report", time.time())
        if self._due("weekly_report", 7 * 86400):
            from .insights import weekly, weekly_text
            notify("info", "Your week with DriveMind", weekly_text(weekly(7)))

        if heavy_ok and self._due("weekly_clean", 7 * 86400):
            if s.decision("weekly_cache_clean") != Decision.NO:
                p = plan_cache_clean(s, scheduled=True)
                r = apply_plan(p, s)
                if r["done"]:
                    notify("info", f"Weekly clean freed {human(r['freed_bytes'])}", "", p.id)
                if p.summary()["waiting"]:
                    p.save()
            if s.decision("clean_temp_junk") != Decision.NO:
                p = plan_temp_clean(s)
                apply_plan(p, s)
                if p.summary()["waiting"]:
                    p.save()
                    notify("info", f"{p.summary()['waiting']} temporary files to review", "", p.id)
            purge_quarantine(s.quarantine_days)
