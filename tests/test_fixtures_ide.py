"""Testes do builder de fixtures sqlite (state.vscdb do Kiro IDE)."""
from __future__ import annotations

import json
import sqlite3

from tests.fixtures.ide.build_state_vscdb import (
    build_state_vscdb,
    load_default_kiro_agent_data,
)


def test_default_fixture_loads_valid_json():
    data = load_default_kiro_agent_data()
    assert data["hasBeenInstalled"] is True
    breakdown = data["kiro.resourceNotifications.usageState"]["usageBreakdowns"][0]
    assert breakdown["unit"] == "INVOCATIONS"
    assert breakdown["currency"]["code"] == "USD"
    assert breakdown["usageLimit"] == 1000


def test_build_creates_sqlite_with_kiro_agent(tmp_path):
    db = build_state_vscdb(tmp_path)
    assert db.exists()
    assert db.name == "state.vscdb"

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        cur.execute("SELECT value FROM ItemTable WHERE key = 'kiro.kiroAgent'")
        row = cur.fetchone()
        assert row is not None
        payload = json.loads(row[0].decode("utf-8") if isinstance(row[0], bytes) else row[0])
        assert payload["kiro.resourceNotifications.usageState"]["usageBreakdowns"][0]["currentUsage"] == 100.0
    finally:
        con.close()


def test_build_supports_omitting_kiro_agent(tmp_path):
    db = build_state_vscdb(tmp_path, omit_kiro_agent=True)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM ItemTable WHERE key = 'kiro.kiroAgent'")
        assert cur.fetchone()[0] == 0
    finally:
        con.close()


def test_build_supports_custom_kiro_agent_data(tmp_path):
    custom = {"hasBeenInstalled": True, "fooBar": 42}
    db = build_state_vscdb(tmp_path, kiro_agent_data=custom)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        cur.execute("SELECT value FROM ItemTable WHERE key = 'kiro.kiroAgent'")
        row = cur.fetchone()
        payload = json.loads(row[0].decode("utf-8") if isinstance(row[0], bytes) else row[0])
        assert payload == custom
    finally:
        con.close()


def test_build_supports_extra_keys(tmp_path):
    db = build_state_vscdb(
        tmp_path,
        extra_keys={"telemetryClientId": "abc-123", "colorThemeData": "{}"},
    )
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        cur.execute("SELECT key FROM ItemTable ORDER BY key")
        keys = [r[0] for r in cur.fetchall()]
        assert "telemetryClientId" in keys
        assert "colorThemeData" in keys
        assert "kiro.kiroAgent" in keys
    finally:
        con.close()


def test_build_overwrites_existing_db(tmp_path):
    db1 = build_state_vscdb(tmp_path)
    mtime1 = db1.stat().st_mtime
    # Re-build com data customizada
    db2 = build_state_vscdb(tmp_path, kiro_agent_data={"x": 1})
    assert db2 == db1  # mesmo path
    con = sqlite3.connect(f"file:{db2}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        cur.execute("SELECT value FROM ItemTable WHERE key = 'kiro.kiroAgent'")
        payload = json.loads(cur.fetchone()[0].decode("utf-8"))
        assert payload == {"x": 1}
    finally:
        con.close()
