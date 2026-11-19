"""Weekly report and large-file finder."""
import time

from fastapi.testclient import TestClient

from conftest import make
from drivemind import db
from drivemind.api import app
from drivemind.config import Decision, Mode, Settings
from drivemind.executor import apply_plan
from drivemind.insights import large_files, plan_large, weekly, weekly_text

H = {"X-DriveMind": "1"}
MB = 1024 * 1024


def journal(op, size, dst=None, ts=None, undone=0, plan="p1", reason=""):
    conn = db.connect()
    conn.execute("INSERT INTO journal(ts, plan_id, op, src, dst, size, reason, undone) VALUES (?,?,?,?,?,?,?,?)",
                 (ts or time.time(), plan, op, "/x/src", dst, size, reason, undone))
    conn.commit()


def test_weekly_counts_only_this_week_and_ignores_undone():
    journal("quarantine", 300 * MB)
    journal("delete_cache", 200 * MB, plan="p2")
    journal("move", 10, dst="/org/Work/Finance/a.pdf")
    journal("move", 10, dst="/org/Work/Finance/b.pdf")
    journal("quarantine", 999 * MB, undone=1)                 # undone: not freed
    journal("quarantine", 777 * MB, ts=time.time() - 30 * 86400)  # last month
    r = weekly(7, drive="/")
    assert r["freed_bytes"] == 500 * MB and r["moved_files"] == 2 and r["plans_applied"] == 2
    assert r["top_categories"][0] == {"name": "Finance", "files": 2}
    assert "freed 500.0 MB" in weekly_text(r) and "organized 2 files" in weekly_text(r)


def test_weekly_drive_growth_from_snapshots():
    conn = db.connect()
    now = time.time()
    for ts, used in ((now - 6 * 86400, 100 * MB), (now - 3 * 86400, 150 * MB), (now, 130 * MB)):
        conn.execute("INSERT INTO snapshots(ts, drive, total, used, free) VALUES (?,?,?,?,?)", (ts, "D:", 1, used, 1))
    conn.commit()
    assert weekly(7, drive="D:")["growth_bytes"] == 30 * MB


def test_report_reaches_the_phone_too():
    c = TestClient(app)
    assert "text" in c.get("/api/report/weekly").json()
    made = c.post("/api/pair", json={"name": "p"}, headers=H).json()
    r = c.get("/m/report/weekly", headers={"Authorization": f"Bearer {made['token']}"})
    assert r.status_code == 200 and r.json()["days"] == 7


def test_large_files_biggest_first_and_skips_protected(isolated):
    big = make(isolated / "Videos" / "wedding.mp4", b"x" * (3 * MB))
    mid = make(isolated / "Downloads" / "setup.iso", b"x" * (2 * MB))
    make(isolated / "Documents" / "small.txt", b"x" * 1000)
    make(isolated / "Documents" / "node_modules" / "huge.bin", b"x" * (4 * MB))
    rows = large_files([isolated], 1 * MB)
    assert [r["name"] for r in rows] == [big.name, mid.name]


def test_removing_a_large_file_always_asks_even_on_autopilot(isolated):
    f = make(isolated / "Videos" / "old.mkv", b"x" * (2 * MB))
    s = Settings()
    s.set_mode(Mode.AUTOPILOT)
    p = plan_large([str(f)], s)
    assert [a.decision for a in p.actions] == [Decision.ASK]
    assert apply_plan(p, s)["done"] == 0 and f.exists(), "nothing happens without approval"
    from drivemind.plan import Status
    p.set_status([p.actions[0].id], Status.APPROVED)
    apply_plan(p, s)
    assert not f.exists(), "approved: moved to quarantine"


def test_large_plan_skips_paths_that_are_not_files(isolated):
    p = plan_large([str(isolated / "Videos"), str(isolated / "nope.bin")])
    assert p.actions == [] and len(p.notes) == 2


def test_archived_project_is_not_counted_as_freed():
    from drivemind.insights import ARCHIVE_ORIGINAL
    journal("archive", 2000 * MB, dst="/q/app.zip", plan="arc")
    journal("quarantine", 2000 * MB, plan="arc", reason=ARCHIVE_ORIGINAL)   # the original, kept 30 days
    journal("delete_cache", 100 * MB, plan="c")
    r = weekly(7, drive="/")
    assert r["freed_bytes"] == 100 * MB and r["cleaned_files"] == 1, "the zip still takes space"
