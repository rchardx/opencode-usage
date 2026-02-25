"""Tests for opencode_usage.db queries using real SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from opencode_usage.db import OpenCodeDB, UsageRow, _default_db_path


def _make_msg(
    msg_id: str,
    session_id: str,
    *,
    agent: str = "build",
    model: str = "test-model",
    provider: str = "openrouter",
    input_tok: int = 100,
    output_tok: int = 50,
    reasoning_tok: int = 0,
    cache_read: int = 10,
    cache_write: int = 5,
    total_tok: int = 165,
    cost: float = 0.01,
    created_ms: int | None = None,
    role: str = "assistant",
) -> tuple[str, str, str]:
    """Build a (id, session_id, data_json) tuple for insertion."""
    if created_ms is None:
        created_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    data: dict[str, Any] = {
        "role": role,
        "tokens": {
            "input": input_tok,
            "output": output_tok,
            "reasoning": reasoning_tok,
            "cache": {"read": cache_read, "write": cache_write},
            "total": total_tok,
        },
        "cost": cost,
        "modelID": model,
        "agent": agent,
        "providerID": provider,
        "time": {"created": created_ms},
    }
    return (msg_id, session_id, json.dumps(data))


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a populated test DB and return its path."""
    path = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT)")
    conn.execute("CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT)")

    now = datetime.now(tz=timezone.utc)
    today_ms = int(now.timestamp() * 1000)
    yesterday_ms = int((now - timedelta(days=1)).timestamp() * 1000)
    old_ms = int((now - timedelta(days=10)).timestamp() * 1000)

    messages = [
        # Today — session s1
        _make_msg(
            "m1",
            "s1",
            agent="build",
            model="deepseek-r1",
            provider="openrouter",
            total_tok=1000,
            cost=0.05,
            created_ms=today_ms,
        ),
        _make_msg(
            "m2",
            "s1",
            agent="build",
            model="deepseek-r1",
            provider="openrouter",
            total_tok=500,
            cost=0.02,
            created_ms=today_ms,
        ),
        _make_msg(
            "m3",
            "s1",
            agent="explore",
            model="gemma-3",
            provider="google",
            total_tok=800,
            cost=0.0,
            created_ms=today_ms,
        ),
        # Yesterday — session s2
        _make_msg(
            "m4",
            "s2",
            agent="explore",
            model="qwen-3-coder",
            provider="alibaba",
            total_tok=300,
            cost=0.01,
            created_ms=yesterday_ms,
        ),
        _make_msg(
            "m5",
            "s2",
            agent="oracle",
            model="deepseek-r1",
            provider="openrouter",
            total_tok=200,
            cost=0.0,
            created_ms=yesterday_ms,
        ),
        # 10 days ago — session s3
        _make_msg(
            "m6",
            "s3",
            agent="build",
            model="deepseek-r1",
            provider="openrouter",
            total_tok=9999,
            cost=1.0,
            created_ms=old_ms,
        ),
        # User message — should be excluded from all queries
        _make_msg(
            "m7",
            "s1",
            agent="build",
            model="deepseek-r1",
            provider="openrouter",
            total_tok=50,
            cost=0.0,
            created_ms=today_ms,
            role="user",
        ),
    ]
    conn.executemany("INSERT INTO message VALUES (?, ?, ?)", messages)

    # m8: assistant with missing tokens.total → excluded by IS NOT NULL
    null_total = json.dumps(
        {
            "role": "assistant",
            "tokens": {"input": 10, "output": 5},
            "cost": 0.0,
            "modelID": "test",
            "agent": "build",
            "providerID": "x",
            "time": {"created": today_ms},
        }
    )
    conn.execute("INSERT INTO message VALUES (?, ?, ?)", ("m8", "s1", null_total))

    conn.execute("INSERT INTO session VALUES (?, ?)", ("s1", "Debug Session"))
    conn.execute("INSERT INTO session VALUES (?, ?)", ("s2", "Feature Work"))
    conn.execute("INSERT INTO session VALUES (?, ?)", ("s3", "Old Session"))
    conn.commit()
    conn.close()
    return path


# ── init ─────────────────────────────────────────────────────


class TestOpenCodeDBInit:
    def test_missing_db_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not found"):
            OpenCodeDB(db_path=tmp_path / "nope.db")

    def test_valid_path(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        assert db.path == db_path


# ── daily ────────────────────────────────────────────────────


class TestDaily:
    def test_returns_rows_with_date_labels(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.daily()
        assert len(rows) >= 2  # today + yesterday + old
        for r in rows:
            assert "-" in r.label  # YYYY-MM-DD

    def test_since_filters_old(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        since = datetime.now().astimezone() - timedelta(days=2)
        rows = db.daily(since=since)
        total = sum(r.tokens.total for r in rows)
        # old message (9999 tokens) should be excluded
        assert total == 1000 + 500 + 800 + 300 + 200

    def test_limit(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.daily(limit=1)
        assert len(rows) == 1


# ── by_model ─────────────────────────────────────────────────


class TestByModel:
    def test_groups_by_model(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_model()
        labels = {r.label for r in rows}
        assert "deepseek-r1" in labels
        assert "gemma-3" in labels
        assert "qwen-3-coder" in labels

    def test_aggregates_tokens(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_model()
        dr1 = next(r for r in rows if r.label == "deepseek-r1")
        # m1(1000) + m2(500) + m5(200) + m6(9999)
        assert dr1.tokens.total == 11699

    def test_aggregates_cost(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_model()
        dr1 = next(r for r in rows if r.label == "deepseek-r1")
        assert dr1.cost == pytest.approx(0.05 + 0.02 + 0.0 + 1.0)

    def test_no_detail_field(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_model()
        for r in rows:
            assert r.detail is None


# ── by_agent ─────────────────────────────────────────────────


class TestByAgent:
    def test_groups_by_agent_and_model(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_agent()
        for r in rows:
            assert r.detail is not None  # model as detail

    def test_build_agent_present(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_agent()
        build_rows = [r for r in rows if r.label == "build"]
        assert len(build_rows) >= 1
        assert build_rows[0].detail == "deepseek-r1"

    def test_explore_has_two_models(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_agent()
        explore = [r for r in rows if r.label == "explore"]
        models = {r.detail for r in explore}
        assert models == {"gemma-3", "qwen-3-coder"}


# ── by_provider ──────────────────────────────────────────────


class TestByProvider:
    def test_groups_by_provider(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_provider()
        labels = {r.label for r in rows}
        assert "openrouter" in labels
        assert "google" in labels
        assert "alibaba" in labels

    def test_openrouter_aggregates(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_provider()
        orr = next(r for r in rows if r.label == "openrouter")
        # m1(1000) + m2(500) + m5(200) + m6(9999)
        assert orr.tokens.total == 11699


# ── by_session ───────────────────────────────────────────────


class TestBySession:
    def test_uses_session_title(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_session()
        labels = {r.label for r in rows}
        assert "Debug Session" in labels
        assert "Feature Work" in labels
        assert "Old Session" in labels

    def test_session_token_aggregation(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_session()
        debug = next(r for r in rows if r.label == "Debug Session")
        # s1: m1(1000) + m2(500) + m3(800) = 2300
        assert debug.tokens.total == 2300


# ── totals ───────────────────────────────────────────────────


class TestTotals:
    def test_returns_single_row(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        total = db.totals()
        assert total.label == "total"
        # 6 valid assistant messages
        assert total.calls == 6

    def test_aggregated_tokens(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        total = db.totals()
        expected = 1000 + 500 + 800 + 300 + 200 + 9999
        assert total.tokens.total == expected

    def test_aggregated_cost(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        total = db.totals()
        expected = 0.05 + 0.02 + 0.0 + 0.01 + 0.0 + 1.0
        assert total.cost == pytest.approx(expected)

    def test_empty_db_returns_default(self, tmp_path):
        path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(path))
        conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT)")
        conn.execute("CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT)")
        conn.commit()
        conn.close()

        db = OpenCodeDB(db_path=path)
        total = db.totals()
        assert total.label == "total"
        assert total.calls == 0
        assert total.cost == 0.0
        assert total.tokens.total == 0


# ── until filter ─────────────────────────────────────────────


class TestUntilFilter:
    def test_until_before_all_data(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        ancient = datetime.now().astimezone() - timedelta(days=30)
        total = db.totals(until=ancient)
        assert total.calls == 0

    def test_until_excludes_today(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        # until = 12 hours ago — should exclude today's messages
        cutoff = datetime.now().astimezone() - timedelta(hours=12)
        rows = db.by_model(until=cutoff)
        total_tok = sum(r.tokens.total for r in rows)
        # Only yesterday (300+200) and old (9999) should remain
        assert total_tok == 300 + 200 + 9999

    def test_since_and_until_window(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        now = datetime.now().astimezone()
        since = now - timedelta(days=2)
        until = now - timedelta(hours=12)
        rows = db.daily(since=since, until=until)
        total_tok = sum(r.tokens.total for r in rows)
        # Only yesterday's messages: m4(300) + m5(200)
        assert total_tok == 500


# ── to_dicts ─────────────────────────────────────────────────


class TestToDicts:
    def test_basic_serialization(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        total = db.totals()
        dicts = db.to_dicts([total])
        assert len(dicts) == 1
        d = dicts[0]
        assert d["label"] == "total"
        assert isinstance(d["calls"], int)
        assert isinstance(d["tokens"], dict)
        assert isinstance(d["cost"], float)
        assert set(d["tokens"].keys()) == {
            "input",
            "output",
            "reasoning",
            "cache_read",
            "cache_write",
            "total",
        }

    def test_detail_becomes_model_key(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_agent()
        dicts = db.to_dicts(rows)
        assert all("model" in d for d in dicts)

    def test_no_detail_no_model_key(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        rows = db.by_model()
        dicts = db.to_dicts(rows)
        for d in dicts:
            assert "model" not in d

    def test_cost_rounded_to_four(self):
        row = UsageRow(label="test", cost=0.123456789)
        db_cls = OpenCodeDB.__new__(OpenCodeDB)
        dicts = db_cls.to_dicts([row])
        assert dicts[0]["cost"] == 0.1235

    def test_empty_list(self, db_path):
        db = OpenCodeDB(db_path=db_path)
        assert db.to_dicts([]) == []


# ── _default_db_path ─────────────────────────────────────────


class TestDefaultDbPath:
    def test_default_path(self, monkeypatch):
        """Test default path with no env vars set."""
        monkeypatch.delenv("OPENCODE_DB", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        result = _default_db_path()
        assert result.name == "opencode.db"
        assert result.parent.name == "opencode"
        # Path separator-agnostic check
        assert result.parts[-1] == "opencode.db"
        assert result.parts[-2] == "opencode"

    def test_opencode_db_override(self, monkeypatch):
        """Test OPENCODE_DB env var overrides default."""
        monkeypatch.setenv("OPENCODE_DB", "/custom/path.db")
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        result = _default_db_path()
        # Path separators may vary, so check equality using Path objects
        assert Path(result) == Path("/custom/path.db")

    def test_xdg_data_home_override(self, monkeypatch):
        """Test XDG_DATA_HOME env var affects path."""
        monkeypatch.delenv("OPENCODE_DB", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", "/custom/xdg")
        result = _default_db_path()
        # Check that it uses XDG_DATA_HOME as base
        assert result.name == "opencode.db"
        assert result.parent.name == "opencode"
        assert "/custom/xdg" in str(result) or "\\custom\\xdg" in str(result)

    def test_opencode_db_takes_priority(self, monkeypatch):
        """Test OPENCODE_DB takes priority over XDG_DATA_HOME."""
        monkeypatch.setenv("OPENCODE_DB", "/custom/override.db")
        monkeypatch.setenv("XDG_DATA_HOME", "/custom/xdg")
        result = _default_db_path()
        # OPENCODE_DB should take priority
        assert Path(result) == Path("/custom/override.db")

    def test_path_suffix_consistency(self, monkeypatch):
        """Test that default paths always end with opencode/opencode.db."""
        monkeypatch.delenv("OPENCODE_DB", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        result = _default_db_path()
        assert result.name == "opencode.db"
        assert result.parent.name == "opencode"
        assert result.is_absolute()  # Should be absolute path
