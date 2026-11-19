import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

from conftest import make

from drivemind.devdata import compact_script, report
from drivemind.search import build_index, name_words, parse_query, search
from drivemind.ssd import assess, parse


def _docx(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f"<w:document><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>")


def _at(path: Path, y: int, m: int, d: int = 10):
    t = datetime(y, m, d, 12).timestamp()
    os.utime(path, (t, t))


def test_search_finds_by_content_type_and_date(isolated):
    docs = isolated / "Documents"
    inv = docs / "Work" / "INV-0042.docx"
    _docx(inv, "Tax invoice for Al Noor Trading LLC, Dubai. Total AED 4,500.")
    _at(inv, 2026, 3)
    other = docs / "Work" / "INV-0043.docx"
    _docx(other, "Tax invoice for Lahore client.")
    _at(other, 2026, 3)
    old = docs / "notes_dubai_trip.txt"
    make(old, b"Dubai trip packing list")
    _at(old, 2025, 3)
    r = build_index([docs])
    assert r["added"] == 3
    hits = search("dubai invoice march")
    assert [h["name"] for h in hits] == ["INV-0042.docx"]           # content match, not file name
    assert "[Dubai]" in hits[0]["snippet"] or "Dubai" in hits[0]["snippet"]
    assert [h["name"] for h in search("dubai 2025")] == ["notes_dubai_trip.txt"]
    assert {h["name"] for h in search("invoice word")} == {"INV-0042.docx", "INV-0043.docx"}
    # incremental: unchanged files are skipped, deleted files leave the index
    other.unlink()
    r2 = build_index([docs])
    assert r2["added"] == 0 and r2["removed"] == 1 and r2["total"] == 2


def test_name_words_and_query_parsing():
    assert name_words("Invoice_DubaiClient-March2026.pdf") == "Invoice Dubai Client March 2026 pdf"
    q = parse_query("contract pdf from March 2026")
    assert q == {"words": ["contract"], "exts": [".pdf"], "month": 3, "year": 2026}


def test_ssd_assessment():
    raw = json.dumps([
        {"Name": "Samsung 980", "Media": "SSD", "Bus": "NVMe", "Health": "Healthy", "SizeGB": 512,
         "Wear": 12, "Temp": 41, "ReadErrors": 0, "WriteErrors": 0, "PowerOnHours": 5300},
        {"Name": "Old HDD", "Media": "HDD", "Bus": "SATA", "Health": "Warning", "SizeGB": 1000,
         "Wear": None, "Temp": None, "ReadErrors": 3, "WriteErrors": 0, "PowerOnHours": None},
    ])
    good, bad = parse(raw)
    assert good["status"] == "good" and "12% of its write life used" in good["notes"]
    assert bad["status"] == "critical" and any("back up now" in n for n in bad["notes"])
    assert any("administrator" in n for n in bad["notes"])       # honest when counters are missing
    assert assess({"Name": "x", "Health": "Healthy", "Wear": 85})["status"] == "critical"
    assert parse(json.dumps({"Name": "single", "Health": "Healthy", "Wear": 3}))[0]["name"] == "single"


def test_devdata_report(isolated):
    local = isolated / "AppData" / "Local"
    make(local / "Packages" / "CanonicalGroupLimited.Ubuntu_x" / "LocalState" / "ext4.vhdx", b"v" * 3000)
    make(local / "Docker" / "wsl" / "disk" / "docker_data.vhdx", b"d" * 5000)
    make(isolated / ".android" / "avd" / "Pixel.avd" / "userdata.img", b"a" * 1000)
    rows = report(windows=True)
    assert [r["id"] for r in rows] == ["docker", "wsl", "avd"]
    assert rows[0]["compact"]["scripts"][0].startswith('select vdisk file="')
    assert any("ANDROID_AVD_HOME" in s for s in rows[2]["steps"])
    assert "compact vdisk" in compact_script("C:\\x.vhdx")
    assert report(windows=False) == []
