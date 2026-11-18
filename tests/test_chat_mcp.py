import asyncio
import os
import sys
import zipfile
from pathlib import Path

import pytest
from conftest import make

from drivemind.chat import answer, route


def _docx(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", f"<w:t>{text}</w:t>")


def test_routing_english_and_roman_urdu():
    assert route("what is eating my C drive space?") == "space"
    assert route("C drive saaf karo") == "clean"
    assert route("meri invoice kahan hai") == "find"
    assert route("is my ssd healthy") == "health"
    assert route("what did the Al Noor contract say about payment terms") == "rag"


def test_rag_answers_from_files_without_a_model(isolated):
    from drivemind.search import build_index
    _docx(isolated / "Documents" / "AlNoor_contract.docx",
          "Payment terms: 50% advance, 50% on delivery within 14 days. Client: Al Noor Trading, Dubai.")
    make(isolated / "Documents" / "shopping.txt", b"milk eggs bread")
    build_index([isolated / "Documents"])
    r = answer("what are the payment terms in the al noor contract", use_ai=False)
    assert r["intent"] == "rag" and not r["ai"]
    assert r["sources"][0]["name"] == "AlNoor_contract.docx"
    assert "[1] AlNoor_contract.docx" in r["answer"]
    r2 = answer("where is my al noor contract", use_ai=False)
    assert r2["intent"] == "find" and r2["sources"]
    assert "free of" not in r2["answer"]  # a find answer is about the file, not the drive


def test_find_lists_each_live_move_once(isolated):
    from drivemind import db
    conn = db.connect()
    src, dst = str(isolated / "Desktop" / "Invoice_X.pdf"), str(isolated / "Organized" / "Invoice_X.pdf")
    for undone in (1, 1, 0):  # moved, undone, moved again, ... the journal keeps every row
        conn.execute("INSERT INTO journal(ts, plan_id, op, src, dst, size, reason, undone) VALUES (0, 1, 'move', ?, ?, 1, '', ?)",
                     (src, dst, undone))
    conn.commit()
    r = answer("find invoice_x", use_ai=False)
    assert r["answer"].count("DriveMind moved Invoice_X.pdf") == 1


def test_rag_with_model_gets_only_real_context(isolated, monkeypatch):
    from drivemind import chat
    from drivemind.search import build_index
    _docx(isolated / "Documents" / "lease.docx", "Rent is AED 5,000 per month, due on the 1st.")
    build_index([isolated / "Documents"])
    seen = {}

    def fake_ollama(settings, q, ctx, history):
        seen["ctx"] = ctx
        return "Rent is AED 5,000 per month [1]."

    monkeypatch.setattr(chat, "_ollama", fake_ollama)
    r = answer("how much is the rent in the lease", use_ai=True)
    assert r["ai"] and r["answer"].endswith("[1].")
    assert seen["ctx"]["sources"][0]["name"] == "lease.docx"


def test_api_chat(isolated):
    from fastapi.testclient import TestClient
    from drivemind.api import app
    r = TestClient(app).post("/api/chat", headers={"X-DriveMind": "1"}, json={"question": "clean caches"}).json()
    assert r["intent"] == "clean" and r["actions"][0]["target"] == "caches"


mcp = pytest.importorskip("mcp")


def test_mcp_server_over_stdio(isolated):
    """Start `python -m drivemind mcp` and talk MCP to it, like Claude Code would."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "drivemind", "mcp"], env=dict(os.environ))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                tools = {t.name for t in (await session.list_tools()).tools}
                res = await session.call_tool("drive_status", {})
                return tools, res

    tools, res = asyncio.run(run())
    assert {"drive_status", "search_files", "plan_cleanup", "apply_plan", "ask_drivemind"} <= tools
    assert not getattr(res, "is_error", getattr(res, "isError", False))
