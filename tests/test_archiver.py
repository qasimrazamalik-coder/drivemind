import os
import subprocess
import time
import zipfile
from pathlib import Path

import pytest
from conftest import make

from drivemind.archiver import git_state, plan_archive
from drivemind.config import Decision, Mode, Settings
from drivemind.executor import apply_plan, undo_plan

pytestmark = pytest.mark.skipif(subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
                                reason="git not installed")


def git(p, *a):
    subprocess.run(["git", "-C", str(p), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *a],
                   check=True, capture_output=True)


def age_tree(p: Path, days: float):
    t = time.time() - days * 86400
    for dirpath, _, files in os.walk(p):
        for n in files:
            os.utime(os.path.join(dirpath, n), (t, t))


def repo(root: Path, name: str, pushed: bool, dirty: bool = False) -> Path:
    p = root / name
    make(p / "package.json", b"{}")
    make(p / "src" / "app.js", b"console.log(1)")
    make(p / "build" / "notes.md", b"hand-written, not a build output")  # no build tool marker? package.json is one
    make(p / "node_modules" / "lib" / "big.js", b"x" * 5000)
    git(p, "init", "-q")
    (p / ".gitignore").write_text("node_modules\n")
    git(p, "add", "-A")
    git(p, "commit", "-qm", "init")
    if pushed:
        bare = root / f"{name}.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        git(p, "remote", "add", "origin", str(bare))
        git(p, "push", "-q", "-u", "origin", "HEAD")
    if dirty:
        (p / "src" / "app.js").write_text("changed")
    age_tree(p, 200)
    return p


def test_git_state(tmp_path):
    clean = repo(tmp_path / "code", "clean", pushed=True)
    local = repo(tmp_path / "code", "local", pushed=False)
    dirty = repo(tmp_path / "code", "dirty", pushed=True, dirty=True)
    assert git_state(clean)["safe"]
    assert "never pushed" in git_state(local)["warnings"][0]
    assert any("uncommitted" in w for w in git_state(dirty)["warnings"])


def test_archive_zip_undo(isolated, tmp_path):
    code = tmp_path / "code"
    clean = repo(code, "clean", pushed=True)
    local = repo(code, "local", pushed=False)
    fresh = code / "fresh"
    make(fresh / "package.json", b"{}")                     # active project: left alone
    s = Settings()
    s.set_mode(Mode.AUTOPILOT)
    archive = tmp_path / "Archive"
    p = plan_archive(s, [code], archive)
    by = {Path(a.src).name: a for a in p.actions}
    assert set(by) == {"clean", "local"}
    assert by["clean"].decision == Decision.YES
    assert by["local"].decision == Decision.ASK and "never pushed" in by["local"].reason  # never automatic
    r = apply_plan(p, s)
    assert r["done"] == 1 and not clean.exists() and local.exists()
    z = Path(by["clean"].dst)
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    assert "clean/src/app.js" in names and any(n.startswith("clean/.git/") for n in names)
    assert not any("node_modules" in n for n in names)        # regenerable deps left out
    assert "clean/build/notes.md" in names                      # build folders are kept: may be hand-made
    undo_plan(p)
    assert (clean / "src" / "app.js").exists() and not z.exists()
    assert git_state(clean)["safe"]
