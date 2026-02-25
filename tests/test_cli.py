"""Tests for opencode_usage.cli helpers."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from opencode_usage.cli import (
    _build_parser,
    _compute_deltas,
    _fetch_rows,
    _parse_since,
    _resolve_since,
)
from opencode_usage.db import OpenCodeDB, TokenStats, UsageRow

# ── _parse_since ─────────────────────────────────────────────


class TestParseSince:
    def test_days(self):
        result = _parse_since("7d")
        expected = datetime.now().astimezone() - timedelta(days=7)
        assert abs((result - expected).total_seconds()) < 2

    def test_weeks(self):
        result = _parse_since("2w")
        expected = datetime.now().astimezone() - timedelta(weeks=2)
        assert abs((result - expected).total_seconds()) < 2

    def test_hours(self):
        result = _parse_since("3h")
        expected = datetime.now().astimezone() - timedelta(hours=3)
        assert abs((result - expected).total_seconds()) < 2

    def test_months(self):
        result = _parse_since("1m")
        expected = datetime.now().astimezone() - timedelta(days=30)
        assert abs((result - expected).total_seconds()) < 2

    def test_iso_date(self):
        result = _parse_since("2025-01-01")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 1

    def test_invalid_raises(self):
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid time spec"):
            _parse_since("bogus")

    def test_whitespace_trimmed(self):
        result = _parse_since("  7d  ")
        expected = datetime.now().astimezone() - timedelta(days=7)
        assert abs((result - expected).total_seconds()) < 2

    def test_case_insensitive(self):
        result = _parse_since("7D")
        expected = datetime.now().astimezone() - timedelta(days=7)
        assert abs((result - expected).total_seconds()) < 2


# ── _build_parser ────────────────────────────────────────────


class TestBuildParser:
    def test_compare_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["--compare"])
        assert args.compare is True

    def test_no_color_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["--no-color"])
        assert args.no_color is True

    def test_defaults(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.compare is False
        assert args.no_color is False
        assert args.command is None
        assert args.days is None
        assert args.since is None
        assert args.by is None
        assert args.limit is None
        assert args.json_output is False
        assert args.db is None

    def test_by_choices(self):
        parser = _build_parser()
        for choice in ("model", "agent", "provider", "session", "day"):
            args = parser.parse_args(["--by", choice])
            assert args.by == choice

    def test_command_today(self):
        parser = _build_parser()
        args = parser.parse_args(["today"])
        assert args.command == "today"

    def test_command_yesterday(self):
        parser = _build_parser()
        args = parser.parse_args(["yesterday"])
        assert args.command == "yesterday"

    def test_json_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["--json"])
        assert args.json_output is True

    def test_limit_int(self):
        parser = _build_parser()
        args = parser.parse_args(["--limit", "10"])
        assert args.limit == 10


# ── _resolve_since ───────────────────────────────────────────


class TestResolveSince:
    def test_today(self):
        ns = argparse.Namespace(command="today", since=None, days=None)
        since, period = _resolve_since(ns)
        now = datetime.now().astimezone()
        assert since.date() == now.date()
        assert since.hour == 0
        assert since.minute == 0
        assert period == "Today"

    def test_yesterday(self):
        ns = argparse.Namespace(command="yesterday", since=None, days=None)
        since, period = _resolve_since(ns)
        yesterday = datetime.now().astimezone() - timedelta(days=1)
        assert since.date() == yesterday.date()
        assert period == "Yesterday & Today"

    def test_days_flag(self):
        ns = argparse.Namespace(command=None, since=None, days=14)
        since, period = _resolve_since(ns)
        expected = datetime.now().astimezone() - timedelta(days=14)
        assert abs((since - expected).total_seconds()) < 2
        assert period == "Last 14 days"

    def test_since_flag(self):
        dt = datetime(2025, 1, 15).astimezone()
        ns = argparse.Namespace(command=None, since=dt, days=None)
        since, period = _resolve_since(ns)
        assert since == dt
        assert "2025-01-15" in period

    def test_default_seven_days(self):
        ns = argparse.Namespace(command=None, since=None, days=None)
        since, period = _resolve_since(ns)
        expected = datetime.now().astimezone() - timedelta(days=7)
        assert abs((since - expected).total_seconds()) < 2
        assert period == "Last 7 days"


# ── _compute_deltas ──────────────────────────────────────────


class TestComputeDeltas:
    def test_matching_labels(self):
        current = [UsageRow(label="model-a", tokens=TokenStats(total=200))]
        previous = [UsageRow(label="model-a", tokens=TokenStats(total=100))]
        deltas = _compute_deltas(current, previous)
        assert len(deltas) == 1
        assert deltas[0] == pytest.approx(100.0)

    def test_missing_label_returns_none(self):
        current = [UsageRow(label="model-a", tokens=TokenStats(total=200))]
        previous = [UsageRow(label="model-b", tokens=TokenStats(total=100))]
        deltas = _compute_deltas(current, previous)
        assert deltas == [None]

    def test_zero_previous_returns_none(self):
        current = [UsageRow(label="model-a", tokens=TokenStats(total=200))]
        previous = [UsageRow(label="model-a", tokens=TokenStats(total=0))]
        deltas = _compute_deltas(current, previous)
        assert deltas == [None]

    def test_negative_delta(self):
        current = [UsageRow(label="x", tokens=TokenStats(total=50))]
        previous = [UsageRow(label="x", tokens=TokenStats(total=100))]
        deltas = _compute_deltas(current, previous)
        assert deltas[0] == pytest.approx(-50.0)

    def test_detail_included_in_key(self):
        current = [
            UsageRow(label="build", detail="model-a", tokens=TokenStats(total=200)),
        ]
        previous = [
            UsageRow(label="build", detail="model-a", tokens=TokenStats(total=100)),
        ]
        deltas = _compute_deltas(current, previous)
        assert deltas[0] == pytest.approx(100.0)

    def test_detail_mismatch_returns_none(self):
        current = [
            UsageRow(label="build", detail="model-a", tokens=TokenStats(total=200)),
        ]
        previous = [
            UsageRow(label="build", detail="model-b", tokens=TokenStats(total=100)),
        ]
        deltas = _compute_deltas(current, previous)
        assert deltas == [None]

    def test_empty_previous(self):
        current = [UsageRow(label="x", tokens=TokenStats(total=100))]
        deltas = _compute_deltas(current, [])
        assert deltas == [None]

    def test_empty_current(self):
        previous = [UsageRow(label="x", tokens=TokenStats(total=100))]
        deltas = _compute_deltas([], previous)
        assert deltas == []


# ── _fetch_rows ──────────────────────────────────────────────


def _make_cli_db(tmp_path: Path) -> Path:
    """Create a minimal test DB for _fetch_rows tests."""
    db_path = tmp_path / "cli_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT)")
    conn.execute("CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT)")

    now_ms = int(datetime.now().astimezone().timestamp() * 1000)
    data = json.dumps(
        {
            "role": "assistant",
            "tokens": {
                "input": 100,
                "output": 50,
                "reasoning": 0,
                "cache": {"read": 10, "write": 5},
                "total": 165,
            },
            "cost": 0.01,
            "modelID": "test-model",
            "agent": "build",
            "providerID": "openrouter",
            "time": {"created": now_ms},
        }
    )
    conn.execute("INSERT INTO message VALUES (?, ?, ?)", ("m1", "s1", data))
    conn.execute("INSERT INTO session VALUES (?, ?)", ("s1", "Test Session"))
    conn.commit()
    conn.close()
    return db_path


class TestFetchRows:
    def test_day(self, tmp_path):
        db = OpenCodeDB(db_path=_make_cli_db(tmp_path))
        rows = _fetch_rows(db, "day")
        assert len(rows) == 1

    def test_model(self, tmp_path):
        db = OpenCodeDB(db_path=_make_cli_db(tmp_path))
        rows = _fetch_rows(db, "model")
        assert len(rows) == 1
        assert rows[0].label == "test-model"

    def test_agent(self, tmp_path):
        db = OpenCodeDB(db_path=_make_cli_db(tmp_path))
        rows = _fetch_rows(db, "agent")
        assert len(rows) == 1
        assert rows[0].label == "build"
        assert rows[0].detail == "test-model"

    def test_provider(self, tmp_path):
        db = OpenCodeDB(db_path=_make_cli_db(tmp_path))
        rows = _fetch_rows(db, "provider")
        assert len(rows) == 1
        assert rows[0].label == "openrouter"

    def test_session(self, tmp_path):
        db = OpenCodeDB(db_path=_make_cli_db(tmp_path))
        rows = _fetch_rows(db, "session")
        assert len(rows) == 1
        assert rows[0].label == "Test Session"

    def test_unknown_group_returns_empty(self, tmp_path):
        db = OpenCodeDB(db_path=_make_cli_db(tmp_path))
        rows = _fetch_rows(db, "unknown")
        assert rows == []
