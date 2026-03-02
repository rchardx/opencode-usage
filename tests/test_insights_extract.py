"""Tests for opencode_usage.insights.extract — session data extraction."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from opencode_usage.insights.extract import (
    aggregate_all,
    extract_agent_stats,
    extract_delegation_stats,
    extract_model_stats,
    extract_session_meta,
    extract_todo_stats,
    extract_tool_stats,
    filter_sessions,
    reconstruct_transcript,
)

# Base timestamp: 2025-01-01 00:00:00 UTC in milliseconds
_BASE_MS = 1_735_689_600_000


def _msg(
    role: str,
    agent: str = "",
    model: str = "",
    tokens_total: int = 0,
    cost: float = 0.0,
    t_offset_ms: int = 0,
) -> str:
    return json.dumps(
        {
            "role": role,
            "agent": agent or None,
            "modelID": model or None,
            "tokens": {
                "input": tokens_total // 2,
                "output": tokens_total // 2,
                "total": tokens_total,
            },
            "cost": cost,
            "time": {"created": _BASE_MS + t_offset_ms},
        }
    )


def _part(
    ptype: str,
    tool: str = "",
    status: str = "completed",
    text: str = "",
    file_path: str = "",
    t_offset_ms: int = 0,
) -> str:
    if ptype == "text":
        return json.dumps({"type": "text", "text": text})
    if ptype == "tool":
        return json.dumps(
            {
                "type": "tool",
                "tool": tool,
                "state": {
                    "status": status,
                    "input": {"filePath": file_path} if file_path else {},
                    "output": "ok",
                },
            }
        )
    if ptype == "reasoning":
        return json.dumps({"type": "reasoning", "text": text})
    return json.dumps({"type": ptype})


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a test database with realistic session/message/part data."""
    db_file = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(db_file))

    conn.execute("""CREATE TABLE session (
        id TEXT PRIMARY KEY, project_id TEXT, parent_id TEXT,
        title TEXT, time_created INTEGER, time_updated INTEGER
    )""")
    conn.execute("""CREATE TABLE message (
        id TEXT PRIMARY KEY, session_id TEXT, data TEXT, time_created INTEGER
    )""")
    conn.execute("""CREATE TABLE part (
        id TEXT PRIMARY KEY, message_id TEXT, data TEXT, time_created INTEGER
    )""")
    conn.execute("""CREATE TABLE todo (
        id TEXT PRIMARY KEY, session_id TEXT, content TEXT, status TEXT, priority TEXT
    )""")
    conn.execute("""CREATE TABLE project (
        id TEXT PRIMARY KEY, worktree TEXT, name TEXT
    )""")

    # Sessions
    # s_valid_1: root, 2 user msgs, 5 min duration → VALID
    # s_valid_2: root, 3 user msgs, 2 min duration → VALID
    # s_short:   root, 2 user msgs, 30 sec duration → FILTERED (too short)
    # s_few:     root, 1 user msg, 5 min duration → FILTERED (too few user msgs)
    # s_sub:     sub-session (parent_id set) → FILTERED (sub-session)
    conn.executemany(
        "INSERT INTO session VALUES (?,?,?,?,?,?)",
        [
            ("s_valid_1", "proj1", None, "Debug session", _BASE_MS, _BASE_MS + 300_000),
            ("s_valid_2", "proj1", None, "Feature session", _BASE_MS, _BASE_MS + 120_000),
            ("s_short", None, None, "Short session", _BASE_MS, _BASE_MS + 30_000),
            ("s_few", None, None, "Few msgs", _BASE_MS, _BASE_MS + 300_000),
            ("s_sub", None, "s_valid_1", "Sub", _BASE_MS, _BASE_MS + 60_000),
        ],
    )

    # Project
    conn.execute(
        "INSERT INTO project VALUES (?,?,?)", ("proj1", "/home/user/myproject", "myproject")
    )

    # Messages for s_valid_1 (5 min span, 2 user + 2 assistant)
    conn.executemany(
        "INSERT INTO message VALUES (?,?,?,?)",
        [
            ("m1", "s_valid_1", _msg("user", t_offset_ms=0), _BASE_MS),
            (
                "m2",
                "s_valid_1",
                _msg(
                    "assistant",
                    agent="build",
                    model="gpt-4o",
                    tokens_total=1000,
                    cost=0.01,
                    t_offset_ms=60_000,
                ),
                _BASE_MS + 60_000,
            ),
            ("m3", "s_valid_1", _msg("user", t_offset_ms=120_000), _BASE_MS + 120_000),
            (
                "m4",
                "s_valid_1",
                _msg(
                    "assistant",
                    agent="build",
                    model="gpt-4o",
                    tokens_total=2000,
                    cost=0.02,
                    t_offset_ms=300_000,
                ),
                _BASE_MS + 300_000,
            ),
        ],
    )

    # Messages for s_valid_2 (2 min span, 3 user + 1 assistant)
    conn.executemany(
        "INSERT INTO message VALUES (?,?,?,?)",
        [
            ("m5", "s_valid_2", _msg("user", t_offset_ms=0), _BASE_MS),
            ("m6", "s_valid_2", _msg("user", t_offset_ms=30_000), _BASE_MS + 30_000),
            ("m7", "s_valid_2", _msg("user", t_offset_ms=60_000), _BASE_MS + 60_000),
            (
                "m8",
                "s_valid_2",
                _msg(
                    "assistant",
                    agent="explore",
                    model="gemini-pro",
                    tokens_total=500,
                    cost=0.005,
                    t_offset_ms=120_000,
                ),
                _BASE_MS + 120_000,
            ),
        ],
    )

    # Messages for s_short (30 sec span — too short)
    conn.executemany(
        "INSERT INTO message VALUES (?,?,?,?)",
        [
            ("m9", "s_short", _msg("user", t_offset_ms=0), _BASE_MS),
            ("m10", "s_short", _msg("user", t_offset_ms=30_000), _BASE_MS + 30_000),
        ],
    )

    # Messages for s_few (5 min span but only 1 user msg)
    conn.executemany(
        "INSERT INTO message VALUES (?,?,?,?)",
        [
            ("m11", "s_few", _msg("user", t_offset_ms=0), _BASE_MS),
            (
                "m12",
                "s_few",
                _msg(
                    "assistant",
                    agent="build",
                    model="gpt-4o",
                    tokens_total=500,
                    cost=0.005,
                    t_offset_ms=300_000,
                ),
                _BASE_MS + 300_000,
            ),
        ],
    )

    # Messages for s_sub
    conn.executemany(
        "INSERT INTO message VALUES (?,?,?,?)",
        [
            ("m13", "s_sub", _msg("user", t_offset_ms=0), _BASE_MS),
            ("m14", "s_sub", _msg("user", t_offset_ms=30_000), _BASE_MS + 30_000),
            (
                "m15",
                "s_sub",
                _msg(
                    "assistant",
                    agent="oracle",
                    model="gpt-4o",
                    tokens_total=300,
                    cost=0.003,
                    t_offset_ms=60_000,
                ),
                _BASE_MS + 60_000,
            ),
        ],
    )

    # Parts for s_valid_1
    conn.executemany(
        "INSERT INTO part VALUES (?,?,?,?)",
        [
            ("p1", "m2", _part("text", text="Let me analyze this."), _BASE_MS + 60_000),
            (
                "p2",
                "m2",
                _part("tool", tool="read", status="completed", file_path="/src/main.py"),
                _BASE_MS + 61_000,
            ),
            (
                "p3",
                "m2",
                _part("tool", tool="edit", status="completed", file_path="/src/utils.ts"),
                _BASE_MS + 62_000,
            ),
            (
                "p4",
                "m4",
                _part("reasoning", text="The error is in the import."),
                _BASE_MS + 300_000,
            ),
            ("p5", "m4", _part("text", text="Here is the fix."), _BASE_MS + 301_000),
            ("p6", "m4", _part("tool", tool="bash", status="error"), _BASE_MS + 302_000),
        ],
    )

    # Parts for s_valid_2
    conn.executemany(
        "INSERT INTO part VALUES (?,?,?,?)",
        [
            ("p7", "m8", _part("text", text="Found the relevant files."), _BASE_MS + 120_000),
            (
                "p8",
                "m8",
                _part("tool", tool="read", status="completed", file_path="/src/index.py"),
                _BASE_MS + 121_000,
            ),
        ],
    )

    # Todos
    conn.executemany(
        "INSERT INTO todo VALUES (?,?,?,?,?)",
        [
            ("t1", "s_valid_1", "Fix bug", "completed", "high"),
            ("t2", "s_valid_1", "Write tests", "completed", "medium"),
            ("t3", "s_valid_1", "Update docs", "pending", "low"),
            ("t4", "s_valid_2", "Add feature", "in_progress", "high"),
            ("t5", "s_valid_2", "Review PR", "pending", "medium"),
        ],
    )

    conn.commit()
    conn.close()
    return db_file


# ── TestSessionFiltering ──────────────────────────────────────────────────────


class TestSessionFiltering:
    def test_returns_only_valid_root_sessions(self, db_path: Path) -> None:
        result = filter_sessions(db_path, since=None)
        assert set(result) == {"s_valid_1", "s_valid_2"}

    def test_excludes_sub_sessions(self, db_path: Path) -> None:
        result = filter_sessions(db_path, since=None)
        assert "s_sub" not in result

    def test_excludes_too_short_sessions(self, db_path: Path) -> None:
        result = filter_sessions(db_path, since=None)
        assert "s_short" not in result

    def test_excludes_too_few_user_messages(self, db_path: Path) -> None:
        result = filter_sessions(db_path, since=None)
        assert "s_few" not in result

    def test_returns_list_of_strings(self, db_path: Path) -> None:
        result = filter_sessions(db_path, since=None)
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_empty_db_returns_empty(self, tmp_path: Path) -> None:
        db_file = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE session (id TEXT, project_id TEXT, parent_id TEXT, "
            "title TEXT, time_created INTEGER, time_updated INTEGER)"
        )
        conn.execute(
            "CREATE TABLE message (id TEXT, session_id TEXT, data TEXT, time_created INTEGER)"
        )
        conn.commit()
        conn.close()
        assert filter_sessions(db_file, since=None) == []


# ── TestMetadataExtraction ────────────────────────────────────────────────────


class TestMetadataExtraction:
    def test_basic_fields(self, db_path: Path) -> None:
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.id == "s_valid_1"
        assert meta.title == "Debug session"
        assert meta.parent_id is None

    def test_message_counts(self, db_path: Path) -> None:
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.user_msg_count == 2
        assert meta.assistant_msg_count == 2

    def test_token_aggregation(self, db_path: Path) -> None:
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.total_tokens == 3000  # 1000 + 2000
        assert meta.input_tokens == 1500  # 500 + 1000
        assert meta.output_tokens == 1500

    def test_cost_aggregation(self, db_path: Path) -> None:
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.cost == pytest.approx(0.03)

    def test_duration_minutes(self, db_path: Path) -> None:
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.duration_minutes == pytest.approx(5.0)

    def test_start_end_time(self, db_path: Path) -> None:
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.start_time == _BASE_MS
        assert meta.end_time == _BASE_MS + 300_000

    def test_agent_counts(self, db_path: Path) -> None:
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.agent_counts == {"build": 2}

    def test_model_counts(self, db_path: Path) -> None:
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.model_counts == {"gpt-4o": 2}

    def test_tool_counts(self, db_path: Path) -> None:
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.tool_counts["read"] == 1
        assert meta.tool_counts["edit"] == 1
        assert meta.tool_counts["bash"] == 1

    def test_language_detection(self, db_path: Path) -> None:
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.languages.get("py", 0) >= 1
        assert meta.languages.get("ts", 0) >= 1

    def test_missing_session_returns_minimal(self, db_path: Path) -> None:
        meta = extract_session_meta(db_path, "nonexistent")
        assert meta.id == "nonexistent"
        assert meta.title == "nonexistent"
        assert meta.total_tokens == 0


# ── TestTranscriptReconstruction ─────────────────────────────────────────────


class TestTranscriptReconstruction:
    def test_includes_text_parts(self, db_path: Path) -> None:
        transcript = reconstruct_transcript(db_path, "s_valid_1")
        assert "Let me analyze this." in transcript
        assert "Here is the fix." in transcript

    def test_includes_tool_parts(self, db_path: Path) -> None:
        transcript = reconstruct_transcript(db_path, "s_valid_1")
        assert "Used read (completed)" in transcript
        assert "Used edit (completed)" in transcript
        assert "Used bash (error)" in transcript

    def test_includes_reasoning_parts(self, db_path: Path) -> None:
        transcript = reconstruct_transcript(db_path, "s_valid_1")
        assert "(reasoning)" in transcript
        assert "The error is in the import." in transcript

    def test_role_labels(self, db_path: Path) -> None:
        transcript = reconstruct_transcript(db_path, "s_valid_1")
        assert "[assistant]:" in transcript

    def test_truncation_when_over_limit(self, db_path: Path) -> None:
        transcript = reconstruct_transcript(db_path, "s_valid_1", max_chars=50)
        assert transcript.startswith("[TRUNCATED")
        assert len(transcript) <= 50 + len("[TRUNCATED — showing last 50 chars]\n")

    def test_no_truncation_when_under_limit(self, db_path: Path) -> None:
        transcript = reconstruct_transcript(db_path, "s_valid_1", max_chars=100_000)
        assert not transcript.startswith("[TRUNCATED")

    def test_empty_session_returns_empty_string(self, db_path: Path) -> None:
        transcript = reconstruct_transcript(db_path, "s_few")
        assert transcript == ""


# ── TestStatsExtraction ───────────────────────────────────────────────────────


class TestStatsExtraction:
    def test_agent_stats_keys(self, db_path: Path) -> None:
        stats = extract_agent_stats(db_path, since=None)
        assert "build" in stats
        assert "explore" in stats

    def test_agent_stats_structure(self, db_path: Path) -> None:
        stats = extract_agent_stats(db_path, since=None)
        build = stats["build"]
        assert "calls" in build
        assert "tokens" in build
        assert "cost" in build
        assert "models_used" in build

    def test_agent_stats_values(self, db_path: Path) -> None:
        stats = extract_agent_stats(db_path, since=None)
        # build agent: m2 (1000 tok, 0.01) + m4 (2000 tok, 0.02) + m12 (500 tok, 0.005)
        assert stats["build"]["calls"] >= 2
        assert stats["build"]["tokens"] >= 3000

    def test_model_stats_keys(self, db_path: Path) -> None:
        stats = extract_model_stats(db_path, since=None)
        assert "gpt-4o" in stats
        assert "gemini-pro" in stats

    def test_model_stats_structure(self, db_path: Path) -> None:
        stats = extract_model_stats(db_path, since=None)
        gpt = stats["gpt-4o"]
        assert "calls" in gpt
        assert "agents_using" in gpt

    def test_tool_stats_keys(self, db_path: Path) -> None:
        stats = extract_tool_stats(db_path, since=None)
        assert "read" in stats
        assert "edit" in stats
        assert "bash" in stats

    def test_tool_stats_completed_vs_errors(self, db_path: Path) -> None:
        stats = extract_tool_stats(db_path, since=None)
        assert stats["bash"]["errors"] == 1
        assert stats["bash"]["total"] == 1
        assert stats["read"]["completed"] >= 1
        assert stats["read"]["errors"] == 0

    def test_todo_stats(self, db_path: Path) -> None:
        stats = extract_todo_stats(db_path, since=None)
        assert stats.get("completed", 0) == 2
        assert stats.get("pending", 0) == 2
        assert stats.get("in_progress", 0) == 1

    def test_delegation_stats_root_count(self, db_path: Path) -> None:
        stats = extract_delegation_stats(db_path, since=None)
        assert stats["root_sessions"] == 4  # s_valid_1, s_valid_2, s_short, s_few
        assert stats["sub_sessions"] == 1  # s_sub

    def test_delegation_stats_structure(self, db_path: Path) -> None:
        stats = extract_delegation_stats(db_path, since=None)
        assert "root_sessions" in stats
        assert "sub_sessions" in stats
        assert "sub_types" in stats
        assert "max_depth" in stats
        assert "avg_depth" in stats

    def test_aggregate_all_structure(self, db_path: Path) -> None:
        agg = aggregate_all(db_path, ["s_valid_1", "s_valid_2"], since=None)
        assert agg.total_sessions == 2
        assert agg.analyzed_sessions == 0
        assert isinstance(agg.date_range, tuple)
        assert len(agg.date_range) == 2
        assert agg.total_messages > 0
        assert agg.total_cost > 0

    def test_aggregate_all_top_lists(self, db_path: Path) -> None:
        agg = aggregate_all(db_path, ["s_valid_1", "s_valid_2"], since=None)
        assert isinstance(agg.top_tools, list)
        assert isinstance(agg.top_agents, list)
        assert isinstance(agg.top_models, list)
        # Each entry is (name, count)
        if agg.top_tools:
            assert isinstance(agg.top_tools[0], tuple)
            assert len(agg.top_tools[0]) == 2

    def test_aggregate_all_empty_sessions(self, db_path: Path) -> None:
        agg = aggregate_all(db_path, [], since=None)
        assert agg.total_sessions == 0
