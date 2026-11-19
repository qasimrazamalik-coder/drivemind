from conftest import make

from drivemind.scanner import scan
from drivemind.winapps import Reg, installed_apps, set_startup, startup_apps


def test_scan_breakdowns(tmp_path):
    root = tmp_path / "d"
    make(root / "a.pdf", b"x" * 1000)
    make(root / "b.jpg", b"x" * 3000, age_days=400)
    make(root / "old" / "c.mp4", b"x" * 500, age_days=2000)
    r = scan(root)
    assert r.categories["Images"] == [1, 3000] and r.categories["Documents"] == [1, 1000]
    assert r.age_buckets["< 1 month"][0] == 1 and r.age_buckets["1–3 years"][0] == 1 and r.age_buckets["3+ years"][0] == 1
    assert r.size_buckets["< 1 MB"] == [3, 4500]


def fake_reg():
    U = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    return Reg({
        ("HKLM", U + r"\{A}"): {"DisplayName": "Android Studio", "Publisher": "Google LLC", "EstimatedSize": 3_000_000,
                                  "InstallDate": "20250102", "InstallLocation": r"C:\Program Files\Android"},
        ("HKLM", U + r"\{B}"): {"DisplayName": "Hidden runtime", "SystemComponent": 1},
        ("HKLM", U + r"\{C}"): {"DisplayName": "Steam", "EstimatedSize": 500_000, "InstallLocation": r"D:\Steam"},
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"): {"Discord": r"C:\Discord\Update.exe", "OneDrive": "od.exe"},
        ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"): {"OneDrive": bytes([3] + [0] * 11)},
        ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"): {"SecurityHealth": "health.exe"},
    })


def test_installed_apps():
    apps = installed_apps(fake_reg())
    assert [a["name"] for a in apps] == ["Android Studio", "Steam"]       # hidden components skipped, biggest first
    assert apps[0]["size"] == 3_000_000 * 1024 and apps[0]["installed"] == "2025-01-02" and apps[0]["drive"] == "C:"


def test_startup_toggle_like_task_manager():
    reg = fake_reg()
    items = {i["name"]: i for i in startup_apps(reg, include_folders=False)}
    assert items["Discord"]["enabled"] and not items["OneDrive"]["enabled"]
    assert not items["SecurityHealth"]["can_toggle"]                       # machine-wide: read-only
    assert set_startup("Discord", False, reg)
    assert not {i["name"]: i for i in startup_apps(reg, False)}["Discord"]["enabled"]
    assert set_startup("Discord", True, reg)
    assert {i["name"]: i for i in startup_apps(reg, False)}["Discord"]["enabled"]
    assert not set_startup("SecurityHealth", False, reg)


def test_latest_scan_survives_a_restart(isolated):
    from fastapi.testclient import TestClient
    from drivemind import api
    from conftest import make
    make(isolated / "Documents" / "a.pdf", b"x" * 5000)
    c = TestClient(api.app)
    job = c.post("/api/scan", json={"root": str(isolated)}, headers={"X-DriveMind": "1"}).json()["job"]
    import time
    for _ in range(100):
        if c.get(f"/api/jobs/{job}").json()["status"] == "done":
            break
        time.sleep(0.05)
    api._last_scan.clear()                          # what a restart does to memory
    again = c.get("/api/scan/latest").json()
    assert again["root"] == str(isolated) and any(x["name"] == "Documents" for x in again["categories"])
