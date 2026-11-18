"""Phone sync: pairing, token protection, CORS only on /m, and actions from the phone."""

from fastapi.testclient import TestClient

from conftest import make

from drivemind.api import app

H = {"X-DriveMind": "1"}


def paired():
    c = TestClient(app)
    r = c.post("/api/pair", headers=H, json={"name": "Pixel"}).json()
    assert r["token"] and r["url"].startswith("drivemind://pair?") and "<svg" in r["qr_svg"]
    return c, {"Authorization": f"Bearer {r['token']}"}, r


def test_phone_needs_valid_token(isolated):
    c = TestClient(app)
    assert c.get("/m/hello").status_code == 401
    assert c.get("/m/hello", headers={"Authorization": "Bearer wrong"}).status_code == 401
    c, auth, _ = paired()
    hello = c.get("/m/hello", headers=auth).json()
    assert hello["drive"] and hello["mode"] == "balanced"


def test_phone_works_from_lan_host_but_api_does_not(isolated):
    c, auth, _ = paired()
    lan = {"host": "192.168.1.20:7878"}
    assert c.get("/m/status", headers={**auth, **lan}).status_code == 200
    assert c.get("/api/status", headers=lan).status_code == 403        # dashboard API stays localhost-only


def test_cors_only_on_phone_api(isolated):
    c, auth, _ = paired()
    pre = c.options("/m/plans", headers={"Origin": "http://x", "Access-Control-Request-Method": "GET"})
    assert pre.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-origin" not in c.get("/api/status").headers


def test_unpair_revokes(isolated):
    c, auth, r = paired()
    assert c.delete(f"/api/devices/{r['id']}", headers=H).status_code == 200
    assert c.get("/m/hello", headers=auth).status_code == 401


def test_approve_and_apply_from_phone(isolated, tmp_path):
    c, auth, _ = paired()
    make(isolated / "Desktop" / "invoice_x.pdf")
    plan = c.post("/api/plans/organize", headers=H,
                  json={"source": str(isolated / "Desktop"), "root": str(tmp_path / "Org"), "use_ai": False}).json()
    pending = c.get("/m/plans/pending", headers=auth).json()
    assert [p["id"] for p in pending] == [plan["id"]]
    ids = [a["id"] for a in plan["actions"]]
    c.post(f"/m/plans/{plan['id']}/decide", headers=auth, json={"approve": ids})
    res = c.post(f"/m/plans/{plan['id']}/apply", headers=auth, json={}).json()
    assert res["result"]["done"] == 1 and (tmp_path / "Org" / "Work" / "Finance" / "invoice_x.pdf").exists()
    assert c.get("/m/plans/pending", headers=auth).json() == []
    # the desktop sees the same plan as applied
    assert TestClient(app).get(f"/api/plans/{plan['id']}").json()["status"] == "applied"


def test_settings_sync_both_ways(isolated):
    c, auth, _ = paired()
    c.put("/m/settings/mode", headers=auth, json={"mode": "safe"})
    assert c.get("/api/settings").json()["settings"]["mode"] == "safe"
    c.put("/api/settings/cache", headers=H, json={"key": "pip", "value": "no"})
    assert {x["id"]: x["choice"] for x in c.get("/m/caches", headers=auth).json()}["pip"] == "no"


def test_tidy_now_runs_only_yes_items(isolated):
    from conftest import cache_dir
    make(cache_dir(isolated, "pip") / "a.bin", b"x" * 500)
    make(cache_dir(isolated, "npm") / "b.bin", b"x" * 500)
    c, auth, _ = paired()
    r = c.post("/m/tidy", headers=auth).json()
    assert r["freed_bytes"] == 500 and r["waiting"] >= 1
    assert (cache_dir(isolated, "npm") / "b.bin").exists()
