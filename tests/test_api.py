from fastapi.testclient import TestClient

from conftest import make

from drivemind.api import app

H = {"X-DriveMind": "1"}


def client():
    return TestClient(app)


def test_requires_header_and_localhost(isolated):
    c = client()
    assert c.post("/api/plans/clean", json={}).status_code == 403
    assert c.get("/api/status", headers={"host": "evil.example.com"}).status_code == 403
    assert c.get("/api/status").status_code == 200


def test_full_flow(isolated, tmp_path):
    c = client()
    make(isolated / "Desktop" / "invoice_acme.pdf")
    make(isolated / "Desktop" / "song.mp3")
    st = c.get("/api/status").json()
    assert st["drives"] and "Desktop" in st["user_folders"]

    root = str(tmp_path / "Org")
    plan = c.post("/api/plans/organize", headers=H,
                  json={"source": str(isolated / "Desktop"), "root": root, "use_ai": False}).json()
    assert plan["summary"]["waiting"] == 2
    inv = [a["id"] for a in plan["actions"] if "invoice" in a["src"]]
    other = [a["id"] for a in plan["actions"] if "invoice" not in a["src"]]
    c.post(f"/api/plans/{plan['id']}/decide", headers=H, json={"approve": inv, "reject": other})
    res = c.post(f"/api/plans/{plan['id']}/apply", headers=H, json={}).json()
    assert res["result"]["done"] == 1
    assert c.get("/api/where", params={"q": "acme"}).json()
    assert c.post(f"/api/plans/{plan['id']}/undo", headers=H).json()["result"]["restored"] == 1
    assert (isolated / "Desktop" / "invoice_acme.pdf").exists()


def test_settings_endpoints(isolated):
    c = client()
    assert c.put("/api/settings/mode", headers=H, json={"mode": "autopilot"}).json()["mode"] == "autopilot"
    r = c.put("/api/settings/option", headers=H, json={"key": "use_cloud_ai", "value": "yes"}).json()
    assert r["options"]["use_cloud_ai"] == "yes" and r["mode"] == "custom"
    c.put("/api/settings/cache", headers=H, json={"key": "pip", "value": "no"})
    assert {x["id"]: x["choice"] for x in c.get("/api/caches").json()}["pip"] == "no"
    assert c.put("/api/settings", headers=H, json={"organize_root": "/x", "mode": "safe"}).json()["mode"] == "custom"


def test_scan_job_and_rules(isolated):
    import time
    c = client()
    make(isolated / "Documents" / "a.bin", b"x" * 300)
    job = c.post("/api/scan", headers=H, json={"root": str(isolated)}).json()["job"]
    for _ in range(50):
        j = c.get(f"/api/jobs/{job}").json()
        if j["status"] != "running":
            break
        time.sleep(0.05)
    assert j["status"] == "done" and j["result"]["total_size"] == 300
    assert c.post("/api/rules", headers=H, json={"text": "nothing useful"}).status_code == 400
    assert c.post("/api/rules", headers=H, json={"text": ".apk files go to Installers/Android"}).status_code == 200
    assert len(c.get("/api/rules").json()) == 1


def test_explain_known_folder(isolated, tmp_path):
    make(tmp_path / "proj" / "node_modules" / "x.js", b"x" * 10)
    r = client().post("/api/explain", headers=H, json={"path": str(tmp_path / "proj" / "node_modules")}).json()
    assert r["source"] == "known" and "npm install" in r["safe_to_delete"]


def test_dashboard_served(isolated):
    c = client()
    assert "DriveMind" in c.get("/").text
    assert c.get("/static/app.js").status_code == 200
