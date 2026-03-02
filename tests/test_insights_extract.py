"""Tests for opencode_usage.insights.extract."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from opencode_usage.insights.extract import (
    aggregate_all,
    extract_agent_stats,
    extract_delegation_stats,
    extract_model_stats,
    extract_project_stats,
    extract_session_meta,
    extract_todo_stats,
    extract_tool_stats,
    filter_sessions,
    reconstruct_transcript,
)

# ── Fixed timestamps for deterministic tests ─────────────────

_BASE_MS = 1_700_000_000_000
_MINUTE = 60_000
_SECOND = 1_000


# ── Helpers ───────────────────────────────────────────────────


def _msg_data(
    *,
    role: str = "assistant",
    agent: str = "build",
    model: str = "deepseek-r1",
    input_tok: int = 100,
    output_tok: int = 50,
    total_tok: int = 150,
    cost: float = 0.01,
    time_ms: int = _BASE_MS,
) -> str:
    """Build JSON data for a message row."""
    data: dict[str, Any] = {
        "role": role,
        "tokens": {
            "input": input_tok,
            "output": output_tok,
            "total": total_tok,
        },
        "cost": cost,
        "modelID": model,
        "agent": agent,
        "time": {"created": time_ms},
    }
    return json.dumps(data)


def _part_data(
    *,
    part_type: str = "text",
    text: str = "",
    tool: str = "",
    status: str = "completed",
    file_path: str | None = None,
) -> str:
    """Build JSON data for a part row."""
    if part_type == "text":
        data: dict[str, Any] = {"type": "text", "text": text}
    elif part_type == "tool":
        state: dict[str, Any] = {"status": status}
        if file_path:
            state["input"] = {"filePath": file_path}
        data = {"type": "tool", "tool": tool, "state": state}
    elif part_type == "reasoning":
        data = {"type": "reasoning", "text": text}
    else:
        data = {"type": part_type}
    return json.dumps(data)


# ── Fixture ───────────────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a fully populated test DB."""
    db_file = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(db_file))

    # Create tables
    conn.execute(
        "CREATE TABLE session ("
        "id TEXT PRIMARY KEY, project_id TEXT, parent_id TEXT, "
        "title TEXT, time_created INTEGER, time_updated INTEGER)"
    )
    conn.execute(
        "CREATE TABLE message ("
        "id TEXT PRIMARY KEY, session_id TEXT, "
        "data TEXT, time_created INTEGER)"
    )
    conn.execute(
        "CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, data TEXT, time_created INTEGER)"
    )
    conn.execute(
        "CREATE TABLE todo ("
        "id TEXT PRIMARY KEY, session_id TEXT, "
        "content TEXT, status TEXT, priority TEXT)"
    )
    conn.execute("CREATE TABLE project (id TEXT PRIMARY KEY, worktree TEXT, name TEXT)")

    t = _BASE_MS

    # ── Sessions ──
    sessions = [
        # s_valid_1: root, 3 user + 2 asst, 5 min duration
        ("s_valid_1", "proj1", None, "Debug Session", t, t + 5 * _MINUTE),
        # s_valid_2: root, 2 user + 2 asst, 2 min duration
        ("s_valid_2", "proj1", None, "Feature Work", t, t + 2 * _MINUTE),
        # s_short: root, 2 user + 1 asst, 30 sec (< 1 min)
        ("s_short", None, None, "Quick Question", t, t + 30 * _SECOND),
        # s_few: root, 1 user + 1 asst, 5 min (< 2 user msgs)
        ("s_few", None, None, "Single Query", t, t + 5 * _MINUTE),
        # s_sub: child of s_valid_1
        ("s_sub", "proj1", "s_valid_1", "Sub Task", t, t + 2 * _MINUTE),
    ]
    conn.executemany("INSERT INTO session VALUES (?,?,?,?,?,?)", sessions)

    # ── Messages ──
    messages = [
        # s_valid_1: 3 user + 2 assistant, span 5 min
        ("mv1u1", "s_valid_1", _msg_data(role="user", cost=0, time_ms=t), t),
        (
            "mv1a1",
            "s_valid_1",
            _msg_data(
                agent="build",
                model="deepseek-r1",
                input_tok=100,
                output_tok=50,
                total_tok=150,
                cost=0.01,
                time_ms=t + _MINUTE,
            ),
            t + _MINUTE,
        ),
        (
            "mv1u2",
            "s_valid_1",
            _msg_data(role="user", cost=0, time_ms=t + 2 * _MINUTE),
            t + 2 * _MINUTE,
        ),
        (
            "mv1a2",
            "s_valid_1",
            _msg_data(
                agent="explore",
                model="gemma-3",
                input_tok=200,
                output_tok=100,
                total_tok=300,
                cost=0.02,
                time_ms=t + 3 * _MINUTE,
            ),
            t + 3 * _MINUTE,
        ),
        (
            "mv1u3",
            "s_valid_1",
            _msg_data(role="user", cost=0, time_ms=t + 5 * _MINUTE),
            t + 5 * _MINUTE,
        ),
        # s_valid_2: 2 user + 2 assistant, span 2 min
        ("mv2u1", "s_valid_2", _msg_data(role="user", cost=0, time_ms=t), t),
        (
            "mv2a1",
            "s_valid_2",
            _msg_data(
                agent="build",
                model="deepseek-r1",
                input_tok=80,
                output_tok=40,
                total_tok=120,
                cost=0.005,
                time_ms=t + 30 * _SECOND,
            ),
            t + 30 * _SECOND,
        ),
        (
            "mv2u2",
            "s_valid_2",
            _msg_data(role="user", cost=0, time_ms=t + 90 * _SECOND),
            t + 90 * _SECOND,
        ),
        (
            "mv2a2",
            "s_valid_2",
            _msg_data(
                agent="build",
                model="deepseek-r1",
                input_tok=60,
                output_tok=30,
                total_tok=90,
                cost=0.003,
                time_ms=t + 2 * _MINUTE,
            ),
            t + 2 * _MINUTE,
        ),
        # s_short: 2 user + 1 assistant, span 30 sec
        ("msu1", "s_short", _msg_data(role="user", cost=0, time_ms=t), t),
        (
            "msu2",
            "s_short",
            _msg_data(role="user", cost=0, time_ms=t + 10 * _SECOND),
            t + 10 * _SECOND,
        ),
        (
            "msa1",
            "s_short",
            _msg_data(
                agent="build",
                model="deepseek-r1",
                input_tok=40,
                output_tok=20,
                total_tok=60,
                cost=0.001,
                time_ms=t + 30 * _SECOND,
            ),
            t + 30 * _SECOND,
        ),
        # s_few: 1 user + 1 assistant, span 5 min
        ("mfu1", "s_few", _msg_data(role="user", cost=0, time_ms=t), t),
        (
            "mfa1",
            "s_few",
            _msg_data(
                agent="oracle",
                model="deepseek-r1",
                input_tok=150,
                output_tok=75,
                total_tok=225,
                cost=0.015,
                time_ms=t + 5 * _MINUTE,
            ),
            t + 5 * _MINUTE,
        ),
        # s_sub: 2 user + 1 assistant, span 2 min
        ("mbu1", "s_sub", _msg_data(role="user", cost=0, time_ms=t), t),
        ("mbu2", "s_sub", _msg_data(role="user", cost=0, time_ms=t + _MINUTE), t + _MINUTE),
        (
            "mba1",
            "s_sub",
            _msg_data(
                agent="oracle",
                model="deepseek-r1",
                input_tok=50,
                output_tok=25,
                total_tok=75,
                cost=0.005,
                time_ms=t + 2 * _MINUTE,
            ),
            t + 2 * _MINUTE,
        ),
    ]
    conn.executemany("INSERT INTO message VALUES (?,?,?,?)", messages)

    # ── Parts (for s_valid_1) ──
    parts = [
        ("p_text_user", "mv1u1", _part_data(text="Help me debug this issue"), t),
        (
            "p_tool_read",
            "mv1a1",
            _part_data(part_type="tool", tool="read", status="completed", file_path="/src/main.py"),
            t + _MINUTE + _SECOND,
        ),
        (
            "p_tool_edit",
            "mv1a1",
            _part_data(
                part_type="tool", tool="edit", status="completed", file_path="/src/utils.ts"
            ),
            t + _MINUTE + 2 * _SECOND,
        ),
        (
            "p_tool_bash",
            "mv1a1",
            _part_data(part_type="tool", tool="bash", status="error"),
            t + _MINUTE + 3 * _SECOND,
        ),
        (
            "p_reasoning",
            "mv1a1",
            _part_data(part_type="reasoning", text="Let me analyze the error trace"),
            t + _MINUTE + 4 * _SECOND,
        ),
        (
            "p_text_asst",
            "mv1a2",
            _part_data(text="The fix is to update the import"),
            t + 3 * _MINUTE + _SECOND,
        ),
        ("p_step", "mv1a2", _part_data(part_type="step-start"), t + 3 * _MINUTE + 2 * _SECOND),
    ]
    conn.executemany("INSERT INTO part VALUES (?,?,?,?)", parts)

    # ── Todos ──
    todos = [
        ("t1", "s_valid_1", "Fix bug", "pending", "high"),
        ("t2", "s_valid_1", "Add test", "completed", "medium"),
        ("t3", "s_valid_1", "Deploy", "completed", "low"),
        ("t4", "s_valid_2", "Implement feature", "pending", "high"),
        ("t5", "s_valid_2", "Write docs", "completed", "medium"),
    ]
    conn.executemany("INSERT INTO todo VALUES (?,?,?,?,?)", todos)

    # ── Projects ──
    conn.execute(
        "INSERT INTO project VALUES (?,?,?)",
        ("proj1", "/home/user/my-project", "my-project"),
    )

    conn.commit()
    conn.close()
    return db_file


# ── TestSessionFiltering ──────────────────────────────────────


class TestSessionFiltering:
    def test_returns_valid_root_sessions(self, db_path: Path):
        """Only root sessions with >=2 user msgs and >=1 min."""
        result = filter_sessions(db_path, since=None)
        assert sorted(result) == ["s_valid_1", "s_valid_2"]

    def test_excludes_short_sessions(self, db_path: Path):
        """s_short has <1 min duration, excluded."""
        result = filter_sessions(db_path, since=None)
        assert "s_short" not in result

    def test_excludes_few_user_msgs(self, db_path: Path):
        """s_few has only 1 user message, excluded."""
        result = filter_sessions(db_path, since=None)
        assert "s_few" not in result

    def test_excludes_sub_sessions(self, db_path: Path):
        """s_sub has parent_id, excluded."""
        result = filter_sessions(db_path, since=None)
        assert "s_sub" not in result

    def test_since_filters_future(self, db_path: Path):
        """since after all data returns empty."""
        future = datetime.fromtimestamp((_BASE_MS + 10 * _MINUTE) / 1000, tz=timezone.utc)
        result = filter_sessions(db_path, since=future)
        assert result == []

    def test_since_before_all_data(self, db_path: Path):
        """since before all data returns same as no filter."""
        past = datetime.fromtimestamp((_BASE_MS - 10 * _MINUTE) / 1000, tz=timezone.utc)
        result = filter_sessions(db_path, since=past)
        assert sorted(result) == ["s_valid_1", "s_valid_2"]

    def test_until_excludes_data(self, db_path: Path):
        """until before all data returns empty."""
        before = datetime.fromtimestamp((_BASE_MS - _MINUTE) / 1000, tz=timezone.utc)
        result = filter_sessions(db_path, since=None, until=before)
        assert result == []


# ── TestMetadataExtraction ────────────────────────────────────


class TestMetadataExtraction:
    def test_basic_fields(self, db_path: Path):
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.id == "s_valid_1"
        assert meta.title == "Debug Session"
        assert meta.parent_id is None

    def test_message_counts(self, db_path: Path):
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.user_msg_count == 3
        assert meta.assistant_msg_count == 2

    def test_token_aggregation(self, db_path: Path):
        """Tokens summed from assistant messages only."""
        meta = extract_session_meta(db_path, "s_valid_1")
        # mv1a1: input=100, output=50, total=150
        # mv1a2: input=200, output=100, total=300
        assert meta.input_tokens == 300
        assert meta.output_tokens == 150
        assert meta.total_tokens == 450

    def test_cost_aggregation(self, db_path: Path):
        """Cost summed from all messages (user cost=0)."""
        meta = extract_session_meta(db_path, "s_valid_1")
        # mv1a1: 0.01, mv1a2: 0.02, users: 0
        assert meta.cost == pytest.approx(0.03)

    def test_duration(self, db_path: Path):
        meta = extract_session_meta(db_path, "s_valid_1")
        # span: t to t+5min = 5 minutes
        assert meta.duration_minutes == pytest.approx(5.0)

    def test_agent_counts(self, db_path: Path):
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.agent_counts == {
            "build": 1,
            "explore": 1,
        }

    def test_model_counts(self, db_path: Path):
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.model_counts == {
            "deepseek-r1": 1,
            "gemma-3": 1,
        }

    def test_tool_counts(self, db_path: Path):
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.tool_counts == {
            "read": 1,
            "edit": 1,
            "bash": 1,
        }

    def test_languages(self, db_path: Path):
        meta = extract_session_meta(db_path, "s_valid_1")
        # /src/main.py → py, /src/utils.ts → ts
        assert meta.languages == {"py": 1, "ts": 1}

    def test_project_path(self, db_path: Path):
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.project_path == "/home/user/my-project"

    def test_timestamps(self, db_path: Path):
        meta = extract_session_meta(db_path, "s_valid_1")
        assert meta.start_time == _BASE_MS
        assert meta.end_time == _BASE_MS + 5 * _MINUTE

    def test_nonexistent_session(self, db_path: Path):
        """Missing session returns minimal SessionMeta."""
        meta = extract_session_meta(db_path, "nonexistent")
        assert meta.id == "nonexistent"
        assert meta.title == "nonexistent"
        assert meta.total_tokens == 0

    def test_session_with_parent(self, db_path: Path):
        meta = extract_session_meta(db_path, "s_sub")
        assert meta.parent_id == "s_valid_1"
        assert meta.user_msg_count == 2
        assert meta.assistant_msg_count == 1

    def test_session_no_project_table(self, tmp_path: Path):
        """Handles missing project table gracefully."""
        db_file = tmp_path / "noproj.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE session ("
            "id TEXT PRIMARY KEY, project_id TEXT, "
            "parent_id TEXT, title TEXT, "
            "time_created INTEGER, time_updated INTEGER)"
        )
        conn.execute(
            "CREATE TABLE message ("
            "id TEXT PRIMARY KEY, session_id TEXT, "
            "data TEXT, time_created INTEGER)"
        )
        conn.execute(
            "CREATE TABLE part ("
            "id TEXT PRIMARY KEY, message_id TEXT, "
            "data TEXT, time_created INTEGER)"
        )
        conn.execute(
            "INSERT INTO session VALUES (?,?,?,?,?,?)",
            ("s1", None, None, "Test", _BASE_MS, _BASE_MS),
        )
        conn.execute(
            "INSERT INTO message VALUES (?,?,?,?)",
            ("m1", "s1", _msg_data(time_ms=_BASE_MS), _BASE_MS),
        )
        conn.commit()
        conn.close()

        meta = extract_session_meta(db_file, "s1")
        assert meta.project_path is None
        assert meta.title == "Test"


# ── TestTranscriptReconstruction ──────────────────────────────


class TestTranscriptReconstruction:
    def test_basic_transcript(self, db_path: Path):
        transcript = reconstruct_transcript(db_path, "s_valid_1")
        assert "[user]: Help me debug this issue" in transcript
        assert "[assistant]: Used read (completed)" in transcript
        assert "[assistant]: Used edit (completed)" in transcript
        assert "[assistant]: Used bash (error)" in transcript
        assert "[assistant]: (reasoning)" in transcript
        assert "[assistant]: The fix is to update" in transcript

    def test_skips_unknown_types(self, db_path: Path):
        """step-start type should be skipped."""
        transcript = reconstruct_transcript(db_path, "s_valid_1")
        assert "step-start" not in transcript

    def test_chronological_order(self, db_path: Path):
        transcript = reconstruct_transcript(db_path, "s_valid_1")
        lines = transcript.strip().split("\n")
        # First line should be user text, last should be asst
        assert lines[0].startswith("[user]:")
        assert lines[-1].startswith("[assistant]:")

    def test_truncation(self, db_path: Path):
        """Transcript truncated to max_chars."""
        transcript = reconstruct_transcript(db_path, "s_valid_1", max_chars=50)
        assert "[TRUNCATED" in transcript

    def test_empty_session(self, db_path: Path):
        """Session with no parts returns empty string."""
        transcript = reconstruct_transcript(db_path, "nonexistent")
        assert transcript == ""

    def test_no_truncation_when_short(self, db_path: Path):
        """No truncation header when within limit."""
        transcript = reconstruct_transcript(db_path, "s_valid_1", max_chars=100_000)
        assert "[TRUNCATED" not in transcript

    def test_reasoning_truncated_to_200(self, tmp_path: Path):
        """Reasoning text capped at 200 chars."""
        db_file = tmp_path / "reason.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "CREATE TABLE session ("
            "id TEXT PRIMARY KEY, project_id TEXT, "
            "parent_id TEXT, title TEXT, "
            "time_created INTEGER, time_updated INTEGER)"
        )
        conn.execute(
            "CREATE TABLE message ("
            "id TEXT PRIMARY KEY, session_id TEXT, "
            "data TEXT, time_created INTEGER)"
        )
        conn.execute(
            "CREATE TABLE part ("
            "id TEXT PRIMARY KEY, message_id TEXT, "
            "data TEXT, time_created INTEGER)"
        )
        conn.execute(
            "INSERT INTO session VALUES (?,?,?,?,?,?)",
            ("s1", None, None, "T", _BASE_MS, _BASE_MS),
        )
        conn.execute(
            "INSERT INTO message VALUES (?,?,?,?)",
            ("m1", "s1", _msg_data(time_ms=_BASE_MS), _BASE_MS),
        )
        long_text = "x" * 500
        conn.execute(
            "INSERT INTO part VALUES (?,?,?,?)",
            ("p1", "m1", _part_data(part_type="reasoning", text=long_text), _BASE_MS),
        )
        conn.commit()
        conn.close()

        transcript = reconstruct_transcript(db_file, "s1")
        reasoning_line = next(ln for ln in transcript.split("\n") if "(reasoning)" in ln)
        text_part = reasoning_line.split("(reasoning) ")[1]
        assert len(text_part) == 200


# ── TestStatsExtraction ───────────────────────────────────────


class TestAgentStats:
    def test_agent_names(self, db_path: Path):
        stats = extract_agent_stats(db_path, since=None)
        assert "build" in stats
        assert "explore" in stats
        assert "oracle" in stats

    def test_build_calls(self, db_path: Path):
        """build: mv1a1 + mv2a1 + mv2a2 + msa1 = 4 calls."""
        stats = extract_agent_stats(db_path, since=None)
        assert stats["build"]["calls"] == 4

    def test_build_tokens(self, db_path: Path):
        """build: 150 + 120 + 90 + 60 = 420 tokens."""
        stats = extract_agent_stats(db_path, since=None)
        assert stats["build"]["tokens"] == 420

    def test_build_models(self, db_path: Path):
        stats = extract_agent_stats(db_path, since=None)
        assert stats["build"]["models_used"] == ["deepseek-r1"]

    def test_explore_stats(self, db_path: Path):
        stats = extract_agent_stats(db_path, since=None)
        assert stats["explore"]["calls"] == 1
        assert stats["explore"]["tokens"] == 300
        assert stats["explore"]["models_used"] == ["gemma-3"]

    def test_oracle_stats(self, db_path: Path):
        """oracle: mfa1 + mba1 = 2 calls, 300 tokens."""
        stats = extract_agent_stats(db_path, since=None)
        assert stats["oracle"]["calls"] == 2
        assert stats["oracle"]["tokens"] == 300

    def test_cost_aggregation(self, db_path: Path):
        stats = extract_agent_stats(db_path, since=None)
        # build: 0.01 + 0.005 + 0.003 + 0.001 = 0.019
        assert stats["build"]["cost"] == pytest.approx(0.019)


class TestModelStats:
    def test_model_names(self, db_path: Path):
        stats = extract_model_stats(db_path, since=None)
        assert "deepseek-r1" in stats
        assert "gemma-3" in stats

    def test_deepseek_calls(self, db_path: Path):
        """deepseek-r1: 6 assistant messages."""
        stats = extract_model_stats(db_path, since=None)
        assert stats["deepseek-r1"]["calls"] == 6

    def test_deepseek_tokens(self, db_path: Path):
        """deepseek-r1: 150+120+90+60+225+75 = 720."""
        stats = extract_model_stats(db_path, since=None)
        assert stats["deepseek-r1"]["tokens"] == 720

    def test_deepseek_agents(self, db_path: Path):
        stats = extract_model_stats(db_path, since=None)
        agents = sorted(stats["deepseek-r1"]["agents_using"])
        assert agents == ["build", "oracle"]

    def test_gemma_stats(self, db_path: Path):
        stats = extract_model_stats(db_path, since=None)
        assert stats["gemma-3"]["calls"] == 1
        assert stats["gemma-3"]["tokens"] == 300
        assert stats["gemma-3"]["agents_using"] == ["explore"]


class TestToolStats:
    def test_tool_names(self, db_path: Path):
        stats = extract_tool_stats(db_path, since=None)
        assert "read" in stats
        assert "edit" in stats
        assert "bash" in stats

    def test_read_completed(self, db_path: Path):
        stats = extract_tool_stats(db_path, since=None)
        assert stats["read"]["completed"] == 1
        assert stats["read"]["errors"] == 0
        assert stats["read"]["total"] == 1

    def test_bash_error(self, db_path: Path):
        stats = extract_tool_stats(db_path, since=None)
        assert stats["bash"]["completed"] == 0
        assert stats["bash"]["errors"] == 1
        assert stats["bash"]["total"] == 1


class TestTodoStats:
    def test_status_counts(self, db_path: Path):
        stats = extract_todo_stats(db_path, since=None)
        assert stats["pending"] == 2
        assert stats["completed"] == 3

    def test_time_filter_excludes(self, db_path: Path):
        """since after all sessions returns empty."""
        future = datetime.fromtimestamp((_BASE_MS + 10 * _MINUTE) / 1000, tz=timezone.utc)
        stats = extract_todo_stats(db_path, since=future)
        assert stats == {}


class TestDelegationStats:
    def test_root_and_sub_counts(self, db_path: Path):
        stats = extract_delegation_stats(db_path, since=None)
        assert stats["root_sessions"] == 4
        assert stats["sub_sessions"] == 1

    def test_max_depth(self, db_path: Path):
        stats = extract_delegation_stats(db_path, since=None)
        assert stats["max_depth"] == 1

    def test_avg_depth(self, db_path: Path):
        stats = extract_delegation_stats(db_path, since=None)
        # 4 roots at depth 0, 1 sub at depth 1 -> avg = 1/5
        assert stats["avg_depth"] == pytest.approx(0.2)

    def test_sub_types(self, db_path: Path):
        stats = extract_delegation_stats(db_path, since=None)
        assert stats["sub_types"] == {"s_valid_1": 1}


class TestProjectStats:
    def test_project_counts(self, db_path: Path):
        stats = extract_project_stats(db_path, since=None)
        # proj1 linked to s_valid_1, s_valid_2, s_sub
        assert stats["/home/user/my-project"] == 3

    def test_time_filter(self, db_path: Path):
        future = datetime.fromtimestamp((_BASE_MS + 10 * _MINUTE) / 1000, tz=timezone.utc)
        stats = extract_project_stats(db_path, since=future)
        assert stats == {}


class TestAggregateAll:
    def test_total_sessions(self, db_path: Path):
        ids = ["s_valid_1", "s_valid_2"]
        agg = aggregate_all(db_path, ids, since=None)
        assert agg.total_sessions == 2
        assert agg.analyzed_sessions == 0

    def test_date_range(self, db_path: Path):
        agg = aggregate_all(db_path, ["s_valid_1"], since=None)
        assert agg.date_range[0] == _BASE_MS
        assert agg.date_range[1] == _BASE_MS + 5 * _MINUTE

    def test_total_messages(self, db_path: Path):
        """Counts all user + assistant messages."""
        agg = aggregate_all(db_path, ["s_valid_1"], since=None)
        # 17 total messages (5+4+3+2+3 user+assistant)
        assert agg.total_messages == 17

    def test_total_cost(self, db_path: Path):
        agg = aggregate_all(db_path, ["s_valid_1"], since=None)
        # Sum of all costs (user cost=0)
        expected = 0.01 + 0.02 + 0.005 + 0.003 + 0.001 + 0.015 + 0.005
        assert agg.total_cost == pytest.approx(expected)

    def test_top_tools(self, db_path: Path):
        agg = aggregate_all(db_path, ["s_valid_1"], since=None)
        tool_names = [name for name, _ in agg.top_tools]
        assert "read" in tool_names
        assert "edit" in tool_names
        assert "bash" in tool_names

    def test_top_agents(self, db_path: Path):
        agg = aggregate_all(db_path, ["s_valid_1"], since=None)
        agent_names = [name for name, _ in agg.top_agents]
        assert "build" in agent_names
        # build has most calls (4), should be first
        assert agg.top_agents[0][0] == "build"

    def test_top_models(self, db_path: Path):
        agg = aggregate_all(db_path, ["s_valid_1"], since=None)
        model_names = [name for name, _ in agg.top_models]
        assert "deepseek-r1" in model_names
        # deepseek-r1 has most calls (6), should be first
        assert agg.top_models[0][0] == "deepseek-r1"
