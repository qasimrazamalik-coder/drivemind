from pathlib import Path

from conftest import WIN, cache_dir, make

from drivemind.cleaner import cache_report, is_known_cache_path, plan_cache_clean, plan_temp_clean
from drivemind.config import Decision, Mode, Settings
from drivemind.devjunk import find_dev_junk, plan_dev_junk
from drivemind.duplicates import plan_duplicates
from drivemind.executor import apply_plan, undo_plan
from drivemind.plan import Status


def test_cache_catalog_and_choices(isolated):
    make(cache_dir(isolated, "pip") / "http" / "a.bin", b"x" * 2048)
    make(cache_dir(isolated, "npm") / "b.bin", b"x" * 1024)
    s = Settings()
    rows = {r["id"]: r for r in cache_report(s)}
    assert len(rows) == 17
    assert rows["pip"]["size"] == 2048 and rows["pip"]["choice"] == "yes"
    assert rows["npm"]["choice"] == "ask"
    assert rows["aimodels"]["display_only"] and rows["cookies"]["choice"] == "no"
    p = plan_cache_clean(s, only=["pip", "npm"])
    by = {a.category: a for a in p.actions}
    assert by["pip"].decision == Decision.YES and by["npm"].decision == Decision.ASK
    r = apply_plan(p, s)
    assert r["done"] == 1 and r["freed_bytes"] == 2048
    assert cache_dir(isolated, "pip").exists()                    # folder kept, contents gone
    assert not any(cache_dir(isolated, "pip").rglob("*.bin"))
    assert (cache_dir(isolated, "npm") / "b.bin").exists()        # Ask item untouched


def test_scheduled_clean_respects_global_switch(isolated):
    make(cache_dir(isolated, "pip") / "a.bin", b"x" * 10)
    s = Settings()
    s.set_option("weekly_cache_clean", Decision.ASK)
    p = plan_cache_clean(s, only=["pip"], scheduled=True)
    assert p.actions[0].decision == Decision.ASK                   # stricter of item (yes) and global (ask)


def test_executor_refuses_unknown_cache_paths(isolated, tmp_path):
    victim = make(tmp_path / "precious" / "thesis.docx", b"important")
    from drivemind.plan import Action, Op, Plan
    p = Plan(title="evil", kind="clean",
             actions=[Action(op=Op.DELETE_CACHE, src=str(victim.parent), decision=Decision.YES)])
    r = apply_plan(p, Settings())
    assert r["failed"] == 1 and victim.exists()
    assert "not a known cache" in p.actions[0].error
    assert is_known_cache_path(cache_dir(isolated, "pip")) is False  # does not exist yet -> not resolved


def test_temp_junk_rules(isolated, tmp_path):
    dl, desk = isolated / "Downloads", isolated / "Desktop"
    make(dl / "movie.mkv.crdownload", age_days=5)
    make(dl / "fresh.crdownload", age_days=0)
    make(dl / "old_setup.exe", age_days=30)
    make(dl / "new_setup.exe", age_days=1)
    make(dl / "photos.zip")
    make(dl / "photos" / "1.jpg")
    make(desk / "~$report.docx", age_days=3)
    make(desk / "Screenshot 2025-01-01.png", age_days=200)
    (desk / "empty" / "nested").mkdir(parents=True)
    s = Settings()
    p = plan_temp_clean(s, roots=[dl, desk], archive_root=tmp_path / "Archive")
    by = {Path(a.src).name: a for a in p.actions}
    assert "movie.mkv.crdownload" in by and "fresh.crdownload" not in by
    assert "old_setup.exe" in by and "new_setup.exe" not in by
    assert by["photos.zip"].category == "extractedzips"
    assert by["~$report.docx"].decision == Decision.YES
    assert by["Screenshot 2025-01-01.png"].op.value == "move"
    assert "empty" in by and "nested" not in by                     # top-most empty folder only
    assert by["old_setup.exe"].decision == Decision.ASK             # installers default to Ask
    s.temp_choices["installers"] = Decision.NO
    p2 = plan_temp_clean(s, roots=[dl], archive_root=tmp_path / "Archive")
    assert {a.status for a in p2.actions if a.category == "installers"} == {Status.SKIPPED}


def test_dev_junk_only_in_stale_projects(isolated, tmp_path):
    old = tmp_path / "code" / "old-app"
    make(old / "package.json", b"{}", age_days=100)
    make(old / "src" / "a.js", b"x", age_days=100)
    make(old / "node_modules" / "lib" / "i.js", b"x" * 500, age_days=100)
    new = tmp_path / "code" / "new-app"
    make(new / "package.json", b"{}")
    make(new / "node_modules" / "lib" / "i.js", b"x" * 500)
    junk = find_dev_junk([tmp_path / "code"], 60)
    assert [Path(j["path"]).parent.name for j in junk] == ["old-app"]
    s = Settings()
    s.set_mode(Mode.AUTOPILOT)
    p = plan_dev_junk(s, [tmp_path / "code"])
    r = apply_plan(p, s)
    assert r["done"] == 1 and not (old / "node_modules").exists() and (old / "src" / "a.js").exists()
    assert (new / "node_modules").exists()


def test_duplicates_keep_best_copy(isolated, tmp_path):
    content = b"y" * 4096
    keep = make(isolated / "Documents" / "Work" / "brief.pdf", content, age_days=10)
    dup1 = make(isolated / "Downloads" / "brief (1).pdf", content)
    dup2 = make(isolated / "Desktop" / "brief - Copy.pdf", content)
    make(isolated / "Documents" / "other.pdf", b"z" * 4096)       # same size, different content
    s = Settings()
    p = plan_duplicates(s, [isolated / "Documents", isolated / "Downloads", isolated / "Desktop"])
    assert sorted(Path(a.src).name for a in p.actions) == ["brief (1).pdf", "brief - Copy.pdf"]
    p.set_status([], Status.APPROVED)
    apply_plan(p, s)
    assert keep.exists() and not dup1.exists() and not dup2.exists()
    undo_plan(p)
    assert dup1.exists() and dup2.exists()


def test_relocate_user_folder(isolated, tmp_path):
    from drivemind.pathmanager import plan_relocate
    make(isolated / "Videos" / "clip.mp4", b"v" * 100)
    s = Settings()
    p = plan_relocate(s, tmp_path / "D", names=["Videos"], home=isolated)
    assert len(p.actions) == 1 and p.actions[0].decision == Decision.ASK
    p.set_status([], Status.APPROVED)
    r = apply_plan(p, s)
    assert r["done"] == 1 and (tmp_path / "D" / "Videos" / "clip.mp4").exists()
    undo_plan(p)
    assert (isolated / "Videos" / "clip.mp4").exists()


def test_temp_caches_keep_recent_files(isolated, tmp_path):
    """Regression: temp folders may hold files a running app still needs."""
    import os
    tmpdir = Path(os.environ["TEMP" if WIN else "TMPDIR"])
    old = make(tmpdir / "metro-cache" / "old.bin", b"o" * 100, age_days=3)
    os.utime(old, (old.stat().st_mtime, old.stat().st_mtime))
    fresh = make(tmpdir / "metro-cache" / "fresh.bin", b"f" * 100)
    unrelated = make(tmpdir / "my-work" / "draft.txt", b"keep")
    s = Settings()
    from drivemind.cleaner import CATALOG_BY_ID
    assert CATALOG_BY_ID["wintemp"].posix == []                  # /tmp itself is never a cache on Linux
    p = plan_cache_clean(s, only=["expo"])                       # never touches the real C:\Windows\Temp in CI
    assert all("my-work" not in a.src for a in p.actions)
    apply_plan(p, s)
    assert not old.exists() and fresh.exists() and unrelated.exists()
