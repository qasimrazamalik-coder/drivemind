"""Live sync and Wi-Fi pairing."""
import threading
import time

from fastapi.testclient import TestClient

from drivemind import devices, events
from drivemind.api import app

H = {"X-DriveMind": "1"}


def client():
    return TestClient(app)


def test_long_poll_wakes_on_change_and_times_out_quietly():
    start = events.current()
    t0 = time.time()
    empty = client().get(f"/api/events?since={start}&timeout=0.3").json()
    assert empty["events"] == [] and time.time() - t0 >= 0.25

    threading.Timer(0.2, lambda: events.publish("notices", title="x")).start()
    t0 = time.time()
    got = client().get(f"/api/events?since={start}&timeout=5").json()
    assert time.time() - t0 < 3, "a waiting client must wake as soon as something changes"
    assert [e["kind"] for e in got["events"]] == ["notices"] and got["seq"] > start


def test_every_write_is_published_with_its_kind():
    c = client()
    start = events.current()
    c.put("/api/settings/mode", json={"mode": "safe"}, headers=H)
    kinds = [e["kind"] for e in c.get(f"/api/events?since={start}&timeout=0").json()["events"]]
    assert "settings" in kinds


def test_stale_cursor_after_restart_asks_client_to_reload():
    r = client().get("/api/events?since=5&timeout=0&boot=old-run").json()
    assert r["reset"] is True


def test_phone_finds_pc_and_pairs_with_six_digit_code():
    c = client()
    found = c.get("/m/discover").json()          # no token needed to find the PC
    assert found["app"] == "drivemind" and "token" not in found and found["pairing_open"] is False

    made = c.post("/api/pair", json={"name": "Desk"}, headers=H).json()
    assert len(made["pin"]) == 6 and made["pin"].isdigit()
    assert c.get("/m/discover").json()["pairing_open"] is True

    assert c.post("/m/claim", json={"pin": "000000" if made["pin"] != "000000" else "111111"}).status_code == 403
    got = c.post("/m/claim", json={"pin": made["pin"], "name": "Qasim's phone"}).json()
    assert got["token"] == made["token"]
    auth = {"Authorization": f"Bearer {got['token']}"}
    assert c.get("/m/hello", headers=auth).status_code == 200
    assert any(d["name"] == "Qasim's phone" for d in devices.list_devices())
    assert c.post("/m/claim", json={"pin": made["pin"]}).status_code == 403   # a code works once


def test_code_guessing_locks_out():
    c = client()
    c.post("/api/pair", json={"name": "x"}, headers=H)
    devices._fails.clear()
    codes = [c.post("/m/claim", json={"pin": f"{i:06d}"}).status_code for i in range(12)]
    assert 429 in codes, "after a few wrong codes, code pairing must lock"
    devices._fails.clear()


def test_other_phone_calls_still_need_a_token():
    assert client().get("/m/events?timeout=0").status_code == 401


def test_new_pairing_replaces_unused_one_but_keeps_connected_phones():
    c = client()
    first = c.post("/api/pair", json={"name": "a"}, headers=H).json()
    c.get("/m/hello", headers={"Authorization": f"Bearer {first['token']}"})   # this phone connected
    c.post("/api/pair", json={"name": "b"}, headers=H)
    third = c.post("/api/pair", json={"name": "c"}, headers=H).json()
    names = sorted(d["id"] for d in devices.list_devices())
    assert names == sorted([first["id"], third["id"]]), "connected phone kept, only the newest unused pairing left"
