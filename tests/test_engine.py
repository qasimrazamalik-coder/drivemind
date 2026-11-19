import time
from pathlib import Path

from conftest import make

from drivemind.classify import classify, destination_folder, smart_name, version_key
from drivemind.config import Decision, Mode, Settings
from drivemind.disk import forecast_days_to_full, health_score, status_for
from drivemind.executor import apply_plan, undo_plan, where_is
from drivemind.plan import Op, Plan, Status
from drivemind.planner import plan_organize
from drivemind.rules import parse_rule
from drivemind.scanner import scan


# ---------------------------------------------------------------- settings ---
def test_modes_and_gate():
    s = Settings()
    assert s.mode == Mode.BALANCED
    assert s.decision("organize_moves") == Decision.ASK
    assert s.decision("skip_quarantine") == Decision.NO
    s.set_mode(Mode.AUTOPILOT)
    assert s.decision("organize_moves") == Decision.YES
    # low-confidence AI guesses wait for the user even in Autopilot
    assert s.gate("organize_moves", 0.95) == Decision.YES
    assert s.gate("organize_moves", 0.5) == Decision.ASK
    s.set_option("organize_moves", Decision.NO)
    assert s.mode == Mode.CUSTOM
    s.save()
    assert Settings.load().decision("organize_moves") == Decision.NO


# ---------------------------------------------------------------- scanner ----
def test_scan_sizes_and_largest(tmp_path):
    root = tmp_path / "data"
    make(root / "a" / "big.bin", b"x" * 5000)
    make(root / "a" / "small.txt", b"x" * 10)
    make(root / "b" / "c" / "mid.bin", b"x" * 1000)
    res = scan(root)
    assert res.total_size == 6010 and res.file_count == 3
    kids = dict(res.top_children())
    assert kids[str(root / "a")] == 5010 and kids[str(root / "b")] == 1000
    assert res.largest_files[0].path.name == "big.bin"


def test_scan_does_not_follow_symlinks(tmp_path):
    import pytest
    root = tmp_path / "data"
    make(root / "real" / "f.bin", b"x" * 100)
    try:
        (root / "loop").symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need Developer Mode on Windows")
    assert scan(root).total_size == 100


# ---------------------------------------------------------------- classify ---
def test_classifier():
    assert classify(Path("Screenshot 2026-11-01 120000.png")).category == "Screenshots"
    c = classify(Path("Invoice_March_Acme.pdf"))
    assert (c.category, c.topic) == ("Documents", "Finance")
    assert classify(Path("Qasim_CV_2026.docx")).topic == "CV"
    assert classify(Path("setup.exe")).category == "Installers"
    assert classify(Path("mystery.qqq")).confidence < 0.6
    assert destination_folder("developer", "Documents", "Finance") == "Work/Finance"
    assert destination_folder("johnny_decimal", "Installers") == "90-99 System/92 Installers"


def test_smart_name_and_versions():
    assert smart_name(Path("IMG-20261101-WA0003.jpg")) == "2026-11-01 WhatsApp photo 0003.jpg"
    assert smart_name(Path("IMG_20261101_123456.jpg")) == "2026-11-01 12.34.56 Photo.jpg"
    assert smart_name(Path("holiday.jpg")) is None
    assert version_key(Path("report final FINAL.docx")) == version_key(Path("report v2.docx")) == "report|.docx"


def test_rule_parser():
    r = parse_rule("anything with invoice from Downloads goes to Work/Invoices")
    assert r.match.name_contains == ["invoice"] and r.match.source_contains == "Downloads"
    assert r.destination == "Work/Invoices"
    r = parse_rule(".apk files go to Installers/Android")
    assert r.match.extensions == [".apk"]
    r = parse_rule("screenshots older than 3 months go to Archive/Shots")
    assert r.match.name_contains == ["screenshot"] and r.match.older_than_days == 90


# ------------------------------------------------------ organize end to end ---
def _desktop(home: Path) -> Path:
    d = home / "Desktop"
    make(d / "Invoice_Acme_March.pdf", b"inv")
    make(d / "notes.txt", b"n")
    make(d / "Screenshot 2026-11-01.png", b"png")
    make(d / "IMG-20261101-WA0003.jpg", b"jpg")
    make(d / "setup.exe", b"exe")
    make(d / "report.docx", b"v1", age_days=5)
    make(d / "report final.docx", b"v2")
    make(d / "my-app" / "package.json", b"{}")
    make(d / "my-app" / "src" / "index.js", b"x")
    make(d / "desktop.ini", b"x")
    return d


def test_organize_plan_decisions_and_safety(isolated, tmp_path):
    desk = _desktop(isolated)
    root = tmp_path / "Organized"
    s = Settings()
    p = plan_organize(desk, root, s, use_ai=False)
    by_src = {Path(a.src).name: a for a in p.actions}
    assert "desktop.ini" not in by_src                       # system file never touched
    assert Path(by_src["Invoice_Acme_March.pdf"].dst).as_posix().endswith("Work/Finance/Invoice_Acme_March.pdf")
    assert by_src["my-app"].category == "Projects"           # project moved whole
    assert by_src["IMG-20261101-WA0003.jpg"].dst.endswith("2026-11-01 WhatsApp photo 0003.jpg")
    assert "_versions" in by_src["report.docx"].dst           # older version stacked
    assert "_versions" not in by_src["report final.docx"].dst
    # Balanced mode: moves wait for the user, nothing is runnable yet
    assert all(a.decision == Decision.ASK for a in p.actions)
    r = apply_plan(p, s)
    assert r["done"] == 0 and (desk / "notes.txt").exists()


def test_apply_undo_and_where(isolated, tmp_path):
    desk = _desktop(isolated)
    root = tmp_path / "Organized"
    s = Settings()
    p = plan_organize(desk, root, s, use_ai=False)
    p.set_status([], Status.APPROVED)
    p.save()
    r = apply_plan(p, s)
    assert r["failed"] == 0 and r["done"] == len(p.actions)
    assert (root / "Work" / "Finance" / "Invoice_Acme_March.pdf").exists()
    assert (root / "Projects" / "my-app" / "src" / "index.js").exists()
    assert not (desk / "notes.txt").exists()
    hits = where_is("Invoice_Acme")
    assert hits and hits[0]["exists_now"]
    u = undo_plan(Plan.load(p.id))
    assert u["restored"] == len(p.actions)
    assert (desk / "notes.txt").exists() and (desk / "my-app" / "package.json").exists()
    assert not (root / "Work").exists()                       # empty folders cleaned up


def test_name_collision_and_duplicate(isolated, tmp_path):
    desk = isolated / "Desktop"
    root = tmp_path / "Organized"
    make(root / "Documents" / "plain.txt", b"same")
    make(desk / "plain.txt", b"same")                          # exact copy -> duplicate
    make(root / "Documents" / "todo.txt", b"old")
    make(desk / "todo.txt", b"different")                      # same name, new content -> suffix
    p = plan_organize(desk, root, Settings(), use_ai=False)
    by = {Path(a.src).name: a for a in p.actions}
    assert by["plain.txt"].op == Op.QUARANTINE
    assert by["todo.txt"].dst.endswith("todo (2).txt")


def test_autopilot_runs_and_quarantine_is_reversible(isolated, tmp_path):
    desk = isolated / "Desktop"
    root = tmp_path / "Organized"
    make(root / "Documents" / "a.txt", b"same")
    make(desk / "a.txt", b"same")
    s = Settings()
    s.set_mode(Mode.AUTOPILOT)
    p = plan_organize(desk, root, s, use_ai=False)
    r = apply_plan(p, s)
    assert r["done"] == 1 and not (desk / "a.txt").exists()
    q = Path(p.actions[0].dst)
    assert q.exists() and "quarantine" in str(q)
    undo_plan(p)
    assert (desk / "a.txt").read_bytes() == b"same"


def test_protected_and_excluded_paths(isolated, tmp_path):
    desk = isolated / "Desktop"
    make(desk / "keep" / "x.txt")
    make(desk / "a.pdf")
    s = Settings(exclusions=[str(desk)])
    p = plan_organize(desk, tmp_path / "Org", s, use_ai=False)
    assert not p.actions and "protected" in p.notes[0]


def test_learner_takes_over_after_feedback(isolated, tmp_path):
    from drivemind import learner
    root = tmp_path / "Org"
    for i in range(4):
        learner.record(f"acme_brief_{i}.pdf", "Documents", str(root / "Clients" / "Acme"), True)
    make(isolated / "Desktop" / "acme_brief_new.pdf")
    p = plan_organize(isolated / "Desktop", root, Settings(), use_ai=False)
    a = p.actions[0]
    assert Path(a.dst).as_posix().endswith("Clients/Acme/acme_brief_new.pdf") and a.category == "Learned"


def test_ai_used_only_for_unsure_files(isolated, tmp_path):
    from drivemind.ai import AIGuess

    class FakeAI:
        def __init__(self):
            self.seen = []

        def available(self):
            return True

        def classify(self, names):
            self.seen = names
            return {n: AIGuess("Design", "Logos", 0.9, "looks like a logo source file") for n in names}

    make(isolated / "Desktop" / "logo_final.qqq")
    make(isolated / "Desktop" / "invoice.pdf")
    fake = FakeAI()
    p = plan_organize(isolated / "Desktop", tmp_path / "Org", Settings(), use_ai=None, ai_client=fake)
    assert fake.seen == ["logo_final.qqq"]                    # confident files never go to the AI
    by = {Path(a.src).name: a for a in p.actions}
    assert Path(by["logo_final.qqq"].dst).as_posix().endswith("Design/Logos/logo_final.qqq")
    assert by["logo_final.qqq"].reason.startswith("AI:")


# ------------------------------------------------------------------- disk ----
def test_health_and_forecast():
    assert health_score(40) == 100 and health_score(15) == 60 and health_score(0) == 0
    assert status_for(20) == "good" and status_for(10) == "watch" and status_for(3) == "critical"
    from drivemind import db
    conn = db.connect()
    now = time.time()
    total = 100_000
    for day in range(10):  # 1000 bytes more used per day
        conn.execute("INSERT INTO snapshots(ts, drive, total, used, free) VALUES (?,?,?,?,?)",
                     (now - (9 - day) * 86400, "X:", total, 50_000 + day * 1000, total - 50_000 - day * 1000))
    conn.commit()
    days = forecast_days_to_full("X:")
    assert 40 <= days <= 42                                     # 41,000 free / 1,000 per day


def test_undo_reports_files_that_come_back_under_a_new_name(isolated, tmp_path):
    desk = isolated / "Desktop"
    make(desk / "Invoice_Acme_March.pdf", b"old invoice")
    s = Settings()
    p = plan_organize(desk, tmp_path / "Organized", s, use_ai=False)
    p.set_status([], Status.APPROVED)
    p.save()
    apply_plan(p, s)
    make(desk / "Invoice_Acme_March.pdf", b"a newer file the user made since")
    u = undo_plan(Plan.load(p.id))
    assert u["restored"] == 1
    assert (desk / "Invoice_Acme_March.pdf").read_bytes() == b"a newer file the user made since", "never overwrite"
    assert len(u["renamed"]) == 1 and Path(u["renamed"][0]["now"]).read_bytes() == b"old invoice"
    assert Path(u["renamed"][0]["was"]) == desk / "Invoice_Acme_March.pdf"
