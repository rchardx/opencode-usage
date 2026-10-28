"""Tests for opencode_usage.db queries using real SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

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
        """Test XDG_DATA_HOME env var affects path when CLI unavailable."""
        monkeypatch.delenv("OPENCODE_DB", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", "/custom/xdg")
        with patch("opencode_usage._opencode_cli._find_opencode", return_value=None):
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


# ── Insights DB queries fixture ───────────────────────────────────────────────


def _make_part(
    part_id: str,
    session_id: str,
    *,
    part_type: str = "text",
    text: str = "",
    tool_name: str = "bash",
    status: str = "success",
    time_created: int | None = None,
) -> tuple[str, str, str, int, str]:
    """Build a (id, message_id, session_id, time_created, data_json) tuple for part insertion."""
    if time_created is None:
        time_created = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    if part_type == "text":
        data: dict[str, Any] = {"type": "text", "text": text}
    elif part_type == "tool":
        data = {
            "type": "tool",
            "tool": {"name": tool_name},
            "state": {"status": status, "input": "some input", "output": "some output"},
        }
    elif part_type == "reasoning":
        data = {"type": "reasoning", "text": text}
    else:
        data = {"type": part_type}
    return (part_id, "msg-" + part_id, session_id, time_created, json.dumps(data))


@pytest.fixture()
def insights_db_path(tmp_path: Path) -> Path:
    """Create a test DB with session, message, and part tables for insights tests."""
    path = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT)")
    conn.execute(
        "CREATE TABLE session "
        "(id TEXT PRIMARY KEY, parent_id TEXT, title TEXT, "
        "time_created INTEGER, time_updated INTEGER)"
    )
    conn.execute(
        "CREATE TABLE part "
        "(id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, "
        "time_created INTEGER, data TEXT)"
    )

    now = datetime.now(tz=timezone.utc)
    now_ms = int(now.timestamp() * 1000)

    # Sessions
    conn.execute(
        "INSERT INTO session VALUES (?,?,?,?,?)",
        ("s1", None, "Session One", now_ms - 10000, now_ms),
    )
    conn.execute(
        "INSERT INTO session VALUES (?,?,?,?,?)",
        ("s2", "s1", "Session Two (child)", now_ms - 5000, now_ms),
    )

    # Messages for s1
    conn.executemany(
        "INSERT INTO message VALUES (?,?,?)",
        [
            _make_msg(
                "m1",
                "s1",
                agent="build",
                model="deepseek-r1",
                input_tok=100,
                cache_read=50,
                total_tok=200,
                cost=0.01,
                created_ms=now_ms,
            ),
            _make_msg(
                "m2",
                "s1",
                agent="build",
                model="deepseek-r1",
                input_tok=200,
                cache_read=100,
                total_tok=400,
                cost=0.02,
                created_ms=now_ms,
            ),
        ],
    )
    # Messages for s2
    conn.executemany(
        "INSERT INTO message VALUES (?,?,?)",
        [
            _make_msg(
                "m3",
                "s2",
                agent="explore",
                model="gemma-3",
                input_tok=50,
                cache_read=0,
                total_tok=100,
                cost=0.005,
                created_ms=now_ms,
            ),
        ],
    )

    # Parts for s1
    conn.executemany(
        "INSERT INTO part VALUES (?,?,?,?,?)",
        [
            _make_part("p1", "s1", part_type="text", text="Hello world", time_created=now_ms),
            _make_part(
                "p2",
                "s1",
                part_type="tool",
                tool_name="bash",
                status="success",
                time_created=now_ms + 1,
            ),
            _make_part(
                "p3",
                "s1",
                part_type="tool",
                tool_name="bash",
                status="error",
                time_created=now_ms + 2,
            ),
            _make_part(
                "p4",
                "s1",
                part_type="reasoning",
                text="Thinking...",
                time_created=now_ms + 3,
            ),
            _make_part(
                "p5",
                "s1",
                part_type="step-start",
                time_created=now_ms + 4,
            ),
        ],
    )

    conn.commit()
    conn.close()
    return path


# ── TestSessionMeta ───────────────────────────────────────────────────────────


class TestSessionMeta:
    def test_returns_sessions(self, insights_db_path: Path) -> None:
        """session_meta returns all sessions with aggregated stats."""
        db = OpenCodeDB(db_path=insights_db_path)
        sessions = db.session_meta()
        assert len(sessions) == 2

    def test_session_has_correct_tokens(self, insights_db_path: Path) -> None:
        """session_meta aggregates tokens correctly."""
        db = OpenCodeDB(db_path=insights_db_path)
        sessions = db.session_meta()
        # s1 has m1+m2 = 600 tokens, s2 has m3 = 100 tokens
        totals = {s.session_id: s.total_tokens for s in sessions}
        assert totals["s1"] == 600
        assert totals["s2"] == 100

    def test_respects_limit(self, insights_db_path: Path) -> None:
        """session_meta respects the limit parameter."""
        db = OpenCodeDB(db_path=insights_db_path)
        sessions = db.session_meta(limit=1)
        assert len(sessions) == 1


# ── TestBuildTranscript ───────────────────────────────────────────────────────


class TestBuildTranscript:
    def test_basic_transcript(self, insights_db_path: Path) -> None:
        """build_transcript returns text with expected part types."""
        db = OpenCodeDB(db_path=insights_db_path)
        transcript = db.build_transcript("s1")
        assert "[text]" in transcript
        assert "[tool:bash]" in transcript
        assert "[thinking]" in transcript
        # step-start should be skipped
        assert "step-start" not in transcript

    def test_truncation(self, insights_db_path: Path) -> None:
        """build_transcript truncates to max_chars."""
        db = OpenCodeDB(db_path=insights_db_path)
        transcript = db.build_transcript("s1", max_chars=50)
        assert len(transcript) <= 50 + len("\n[...truncated...]\n") + 50

    def test_empty_session(self, insights_db_path: Path) -> None:
        """build_transcript returns empty string for session with no parts."""
        db = OpenCodeDB(db_path=insights_db_path)
        transcript = db.build_transcript("nonexistent-session")
        assert transcript == ""


# ── TestCacheEfficiency ───────────────────────────────────────────────────────


class TestCacheEfficiency:
    def test_computes_ratios(self, insights_db_path: Path) -> None:
        """cache_efficiency returns ratios between 0 and 1."""
        db = OpenCodeDB(db_path=insights_db_path)
        eff = db.cache_efficiency()
        for model, ratio in eff.items():
            assert 0.0 <= ratio <= 1.0, f"Invalid ratio for {model}: {ratio}"

    def test_deepseek_ratio(self, insights_db_path: Path) -> None:
        """deepseek-r1 cache ratio = (50+100) / (100+50+200+100) = 150/450 = 0.333."""
        db = OpenCodeDB(db_path=insights_db_path)
        eff = db.cache_efficiency()
        assert "deepseek-r1" in eff
        assert pytest.approx(eff["deepseek-r1"], abs=0.01) == 150 / 450

    def test_zero_cache_read(self, insights_db_path: Path) -> None:
        """Model with zero cache_read returns 0.0 ratio."""
        db = OpenCodeDB(db_path=insights_db_path)
        eff = db.cache_efficiency()
        # gemma-3 has cache_read=0
        if "gemma-3" in eff:
            assert eff["gemma-3"] == 0.0


# ── TestToolErrorRates ────────────────────────────────────────────────────────


class TestToolErrorRates:
    def test_computes_rates(self, insights_db_path: Path) -> None:
        """tool_error_rates returns per-tool error rates."""
        db = OpenCodeDB(db_path=insights_db_path)
        rates = db.tool_error_rates()
        # bash has 1 success + 1 error = 50% error rate
        if "bash" in rates:
            assert pytest.approx(rates["bash"], abs=0.01) == 0.5

    def test_rates_between_0_and_1(self, insights_db_path: Path) -> None:
        """All tool error rates are between 0 and 1."""
        db = OpenCodeDB(db_path=insights_db_path)
        rates = db.tool_error_rates()
        for tool, rate in rates.items():
            assert 0.0 <= rate <= 1.0, f"Invalid rate for {tool}: {rate}"


# ── TestCostPer1kTokens ───────────────────────────────────────────────────────


class TestCostPer1kTokens:
    def test_computes_ratio(self, insights_db_path: Path) -> None:
        """cost_per_1k_tokens returns positive values for models with cost."""
        db = OpenCodeDB(db_path=insights_db_path)
        cost_1k = db.cost_per_1k_tokens()
        assert "deepseek-r1" in cost_1k
        # deepseek-r1: cost=0.03, tokens=600 → 0.03/600*1000 = 0.05
        assert pytest.approx(cost_1k["deepseek-r1"], abs=0.001) == 0.05


# ── V2 & Mixed Schema Reproduction Tests ──────────────────────────────────────


def _make_v2_msg(
    msg_id: str,
    session_id: str,
    *,
    agent: str = "build",
    model_id: str = "deepseek-v4",
    provider_id: str = "opencode",
    input_tok: int = 100,
    output_tok: int = 50,
    reasoning_tok: int = 0,
    cache_read: int = 10,
    cache_write: int = 5,
    cost: float = 0.01,
    created_ms: int | None = None,
    msg_type: str = "assistant",
) -> tuple[str, str, str, int, int, str]:
    """Build a tuple for session_message insertion."""
    if created_ms is None:
        created_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    data: dict[str, Any] = {
        "agent": agent,
        "model": {
            "id": model_id,
            "providerID": provider_id,
        },
        "cost": cost,
        "tokens": {
            "input": input_tok,
            "output": output_tok,
            "reasoning": reasoning_tok,
            "cache": {"read": cache_read, "write": cache_write},
        },
        "time": {
            "created": created_ms,
        },
    }
    return (msg_id, session_id, msg_type, 1, created_ms, json.dumps(data))


@pytest.fixture()
def v2_db_path(tmp_path: Path) -> Path:
    """Create a populated v2-only test DB and return its path."""
    path = tmp_path / "opencode_v2.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE session_v2 (id TEXT PRIMARY KEY, title TEXT, time_created INTEGER)"
    )
    conn.execute(
        "CREATE TABLE session_message (id TEXT PRIMARY KEY, session_id TEXT, type TEXT, seq INTEGER, time_created INTEGER, data TEXT)"
    )

    now = datetime.now(tz=timezone.utc)
    today_ms = int(now.timestamp() * 1000)
    yesterday_ms = int((now - timedelta(days=1)).timestamp() * 1000)

    rows = [
        _make_v2_msg(
            "v2_m1",
            "v2_s1",
            agent="build",
            model_id="deepseek-v4",
            provider_id="opencode",
            input_tok=200,
            output_tok=50,
            cost=0.02,
            created_ms=today_ms,
        ),
        _make_v2_msg(
            "v2_m2",
            "v2_s1",
            agent="explore",
            model_id="deepseek-v4",
            provider_id="opencode",
            input_tok=100,
            output_tok=50,
            cost=0.01,
            created_ms=today_ms,
        ),
        _make_v2_msg(
            "v2_m3",
            "v2_s2",
            agent="build",
            model_id="gpt-4o",
            provider_id="openai",
            input_tok=500,
            output_tok=100,
            cost=0.05,
            created_ms=yesterday_ms,
        ),
        # 0 tokens call (aborted) -> should not count as call
        _make_v2_msg("v2_m4", "v2_s2", model_id="gpt-4o", provider_id="openai", input_tok=0, output_tok=0, cost=0.0, created_ms=today_ms),
        # user message -> should be ignored
        _make_v2_msg("v2_m5", "v2_s1", model_id="deepseek-v4", provider_id="opencode", input_tok=50, output_tok=0, cost=0.0, created_ms=today_ms, msg_type="user"),
    ]
    conn.executemany("INSERT INTO session_message (id, session_id, type, seq, time_created, data) VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.execute("INSERT INTO session_v2 (id, title, time_created) VALUES (?, ?, ?)", ("v2_s1", "V2 Debug", today_ms))
    conn.execute("INSERT INTO session_v2 (id, title, time_created) VALUES (?, ?, ?)", ("v2_s2", "V2 Feature", yesterday_ms))
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def v2_seconds_db_path(tmp_path: Path) -> Path:
    """Create a v2 test DB where time_created is stored in seconds rather than milliseconds."""
    path = tmp_path / "opencode_v2_sec.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE session_v2 (id TEXT PRIMARY KEY, title TEXT, time_created INTEGER)"
    )
    conn.execute(
        "CREATE TABLE session_message (id TEXT PRIMARY KEY, session_id TEXT, type TEXT, seq INTEGER, time_created INTEGER, data TEXT)"
    )
    now = datetime.now(tz=timezone.utc)
    today_sec = int(now.timestamp())
    msg = _make_v2_msg(
        "v2_sec_m1",
        "v2_s1",
        model_id="deepseek-v4",
        provider_id="opencode",
        input_tok=200,
        output_tok=50,
        cost=0.02,
        created_ms=today_sec,
    )
    conn.execute(
        "INSERT INTO session_message (id, session_id, type, seq, time_created, data) VALUES (?, ?, ?, ?, ?, ?)",
        ("v2_sec_m1", "v2_s1", "assistant", 1, today_sec, msg[5]),
    )
    conn.execute(
        "INSERT INTO session_v2 (id, title, time_created) VALUES (?, ?, ?)",
        ("v2_s1", "V2 Sec Session", today_sec),
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def mixed_disjoint_db_path(tmp_path: Path) -> Path:
    """Create a populated mixed DB where v1 and v2 have completely disjoint sessions and messages."""
    path = tmp_path / "opencode_mixed_disjoint.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT)")
    conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT)")
    conn.execute("CREATE TABLE session_v2 (id TEXT PRIMARY KEY, title TEXT, time_created INTEGER)")
    conn.execute(
        "CREATE TABLE session_message (id TEXT PRIMARY KEY, session_id TEXT, type TEXT, seq INTEGER, time_created INTEGER, data TEXT)"
    )

    now = datetime.now(tz=timezone.utc)
    today_ms = int(now.timestamp() * 1000)
    old_ms = int((now - timedelta(days=10)).timestamp() * 1000)

    # v1 message: session s_v1, model deepseek-r1
    v1_msg = _make_msg("v1_m1", "s_v1", model="deepseek-r1", total_tok=500, cost=0.02, created_ms=old_ms)
    conn.execute("INSERT INTO message VALUES (?, ?, ?)", v1_msg)
    conn.execute("INSERT INTO session VALUES (?, ?)", ("s_v1", "V1 Disjoint Session"))

    # v2 message: session s_v2, model deepseek-v4
    v2_msg = _make_v2_msg(
        "v2_m1",
        "s_v2",
        model_id="deepseek-v4",
        input_tok=300,
        output_tok=100,
        cost=0.03,
        created_ms=today_ms,
    )
    conn.execute(
        "INSERT INTO session_message (id, session_id, type, seq, time_created, data) VALUES (?, ?, ?, ?, ?, ?)",
        v2_msg,
    )
    conn.execute("INSERT INTO session_v2 VALUES (?, ?, ?)", ("s_v2", "V2 Disjoint Session", today_ms))

    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def mixed_db_path(tmp_path: Path) -> Path:
    """Create a populated mixed DB (migrated from v1 to v2) with overlapping IDs."""
    path = tmp_path / "opencode_mixed.db"
    conn = sqlite3.connect(str(path))
    # v1 tables
    conn.execute("CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT)")
    conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT)")
    # v2 tables
    conn.execute("CREATE TABLE session_v2 (id TEXT PRIMARY KEY, title TEXT, time_created INTEGER)")
    conn.execute("CREATE TABLE session_message (id TEXT PRIMARY KEY, session_id TEXT, type TEXT, seq INTEGER, time_created INTEGER, data TEXT)")

    now = datetime.now(tz=timezone.utc)
    today_ms = int(now.timestamp() * 1000)
    old_ms = int((now - timedelta(days=20)).timestamp() * 1000)

    # Old message only in v1
    v1_only = _make_msg("v1_only_msg", "s_old", total_tok=300, cost=0.01, created_ms=old_ms)
    conn.execute("INSERT INTO message VALUES (?, ?, ?)", v1_only)
    conn.execute("INSERT INTO session VALUES (?, ?)", ("s_old", "Old V1 Session"))

    # Migrated message present in BOTH v1 and v2 with SAME ID
    shared_v1 = _make_msg("shared_msg", "s_shared", total_tok=400, cost=0.02, created_ms=today_ms)
    conn.execute("INSERT INTO message VALUES (?, ?, ?)", shared_v1)
    shared_v2 = _make_v2_msg("shared_msg", "s_shared", model_id="test-model", provider_id="openrouter", input_tok=300, output_tok=100, cost=0.02, created_ms=today_ms)
    conn.execute("INSERT INTO session_message (id, session_id, type, seq, time_created, data) VALUES (?, ?, ?, ?, ?, ?)", shared_v2)
    conn.execute("INSERT INTO session VALUES (?, ?)", ("s_shared", "Shared Session V1"))
    conn.execute("INSERT INTO session_v2 (id, title, time_created) VALUES (?, ?, ?)", ("s_shared", "Shared Session V2", today_ms))

    # New message only in v2
    v2_only = _make_v2_msg("v2_only_msg", "s_new", model_id="v2-model", provider_id="opencode", input_tok=500, output_tok=200, cost=0.04, created_ms=today_ms)
    conn.execute("INSERT INTO session_message (id, session_id, type, seq, time_created, data) VALUES (?, ?, ?, ?, ?, ?)", v2_only)
    conn.execute("INSERT INTO session_v2 (id, title, time_created) VALUES (?, ?, ?)", ("s_new", "New V2 Session", today_ms))

    conn.commit()
    conn.close()
    return path


class TestV2SchemaSupport:
    def test_v2_totals(self, v2_db_path: Path) -> None:
        """v2 database returns correct total calls, tokens, and cost."""
        db = OpenCodeDB(db_path=v2_db_path)
        totals = db.totals()
        assert totals.calls == 3
        assert totals.tokens.input == 800
        assert totals.tokens.output == 200
        assert totals.tokens.total == 1000
        assert pytest.approx(totals.cost, abs=0.001) == 0.08

    def test_v2_by_model(self, v2_db_path: Path) -> None:
        """v2 database groups by model correctly."""
        db = OpenCodeDB(db_path=v2_db_path)
        rows = db.by_model()
        models = {r.label: r for r in rows}
        assert "deepseek-v4" in models
        assert models["deepseek-v4"].calls == 2
        assert "gpt-4o" in models
        assert models["gpt-4o"].calls == 1

    def test_v2_by_session(self, v2_db_path: Path) -> None:
        """v2 database resolves session titles from session_v2."""
        db = OpenCodeDB(db_path=v2_db_path)
        rows = db.by_session()
        labels = [r.label for r in rows]
        assert "V2 Debug" in labels
        assert "V2 Feature" in labels

    def test_v2_daily(self, v2_db_path: Path) -> None:
        """v2 database aggregates daily usage with date labels."""
        db = OpenCodeDB(db_path=v2_db_path)
        rows = db.daily()
        assert len(rows) == 2
        for r in rows:
            assert "-" in r.label
        today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        today_row = next(r for r in rows if r.label == today_str)
        assert today_row.calls == 2
        assert today_row.tokens.total == 400

    def test_v2_by_agent(self, v2_db_path: Path) -> None:
        """v2 database groups by agent and model correctly."""
        db = OpenCodeDB(db_path=v2_db_path)
        rows = db.by_agent()
        agent_models = {(r.label, r.detail): r for r in rows}
        assert ("build", "deepseek-v4") in agent_models
        assert ("explore", "deepseek-v4") in agent_models
        assert ("build", "gpt-4o") in agent_models
        assert agent_models[("build", "deepseek-v4")].calls == 1
        assert agent_models[("explore", "deepseek-v4")].calls == 1
        assert agent_models[("build", "gpt-4o")].calls == 1

    def test_v2_by_provider(self, v2_db_path: Path) -> None:
        """v2 database groups by provider correctly."""
        db = OpenCodeDB(db_path=v2_db_path)
        rows = db.by_provider()
        providers = {r.label: r for r in rows}
        assert "opencode" in providers
        assert "openai" in providers
        assert providers["opencode"].calls == 2
        assert providers["openai"].calls == 1

    def test_v2_since_filter(self, v2_db_path: Path) -> None:
        """v2 database correctly filters rows with since parameter."""
        db = OpenCodeDB(db_path=v2_db_path)
        since = datetime.now(tz=timezone.utc) - timedelta(hours=12)
        rows = db.daily(since=since)
        assert len(rows) == 1
        assert rows[0].calls == 2
        assert rows[0].tokens.total == 400

    def test_v2_until_filter(self, v2_db_path: Path) -> None:
        """v2 database correctly filters rows with until parameter."""
        db = OpenCodeDB(db_path=v2_db_path)
        until = datetime.now(tz=timezone.utc) - timedelta(hours=12)
        rows = db.daily(until=until)
        assert len(rows) == 1
        assert rows[0].calls == 1
        assert rows[0].tokens.total == 600

    def test_v2_seconds_timestamps(self, v2_seconds_db_path: Path) -> None:
        """v2 database handles time_created stored in seconds (< 10^12) correctly."""
        db = OpenCodeDB(db_path=v2_seconds_db_path)
        totals = db.totals()
        assert totals.calls == 1
        assert totals.tokens.total == 250
        assert pytest.approx(totals.cost, abs=0.001) == 0.02
        daily = db.daily()
        assert len(daily) == 1
        assert "-" in daily[0].label

    def test_v2_to_dicts(self, v2_db_path: Path) -> None:
        """v2 database produces expected dict structure for --json output."""
        db = OpenCodeDB(db_path=v2_db_path)
        rows = db.by_model()
        dicts = db.to_dicts(rows)
        assert len(dicts) == 2
        for d in dicts:
            assert "label" in d
            assert "calls" in d
            assert "tokens" in d
            assert "cost" in d
            assert isinstance(d["tokens"]["total"], int)


class TestMixedSchemaSupport:
    def test_mixed_deduplication(self, mixed_db_path: Path) -> None:
        """Mixed database must deduplicate shared IDs and include both v1-only and v2-only messages."""
        db = OpenCodeDB(db_path=mixed_db_path)
        totals = db.totals()
        # 1 v1_only + 1 shared (not double counted!) + 1 v2_only = 3 calls
        assert totals.calls == 3
        # Tokens:
        # v1_only: input=100, output=50, reasoning=0, cache_r=10, cache_w=5 -> total=165
        # shared_v2: input=300, output=100, cache_r=10, cache_w=5 -> total=400
        # v2_only: input=500, output=200, cache_r=10, cache_w=5 -> total=700
        assert totals.tokens.total == 1400

    def test_mixed_disjoint(self, mixed_disjoint_db_path: Path) -> None:
        """Mixed database seamlessly merges disjoint v1 and v2 records."""
        db = OpenCodeDB(db_path=mixed_disjoint_db_path)
        totals = db.totals()
        assert totals.calls == 2
        assert totals.tokens.total == 900
        assert pytest.approx(totals.cost, abs=0.001) == 0.05

        models = {r.label for r in db.by_model()}
        assert models == {"deepseek-r1", "deepseek-v4"}

        sessions = {r.label for r in db.by_session()}
        assert sessions == {"V1 Disjoint Session", "V2 Disjoint Session"}

