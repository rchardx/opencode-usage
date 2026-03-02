"""SQLite query layer for OpenCode's database."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ._insights_legacy import SessionMeta


def _default_db_path() -> Path:
    """Resolve the OpenCode database path per platform."""
    if custom := os.environ.get("OPENCODE_DB"):
        return Path(custom)
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "opencode" / "opencode.db"


@dataclass
class TokenStats:
    input: int = 0
    output: int = 0
    reasoning: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total: int = 0


@dataclass
class UsageRow:
    """A single aggregated usage row."""

    label: str
    calls: int = 0
    tokens: TokenStats = field(default_factory=TokenStats)
    cost: float = 0.0
    detail: str | None = None


class OpenCodeDB:
    """Read-only access to the OpenCode SQLite database."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.path = Path(db_path) if db_path else _default_db_path()
        if not self.path.exists():
            raise FileNotFoundError(
                f"OpenCode database not found at {self.path}\nSet OPENCODE_DB env var to override."
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    # ── query helpers ─────────────────────────────────────────────

    def _time_filter(
        self,
        since: datetime | None,
        until: datetime | None = None,
        *,
        col: str = "data",
    ) -> tuple[str, list[Any]]:
        """Return WHERE clause fragments and params for time filtering."""
        clauses: list[str] = []
        params: list[Any] = []
        if since is not None:
            ts_ms = int(since.timestamp() * 1000)
            clauses.append(f"AND json_extract({col}, '$.time.created') >= ?")
            params.append(ts_ms)
        if until is not None:
            ts_ms = int(until.timestamp() * 1000)
            clauses.append(f"AND json_extract({col}, '$.time.created') < ?")
            params.append(ts_ms)
        return " ".join(clauses), params

    def _base_query(
        self,
        group_expr: str,
        since: datetime | None = None,
        until: datetime | None = None,
        order: str = "total_tokens DESC",
        limit: int | None = None,
    ) -> list[UsageRow]:
        time_clause, params = self._time_filter(since, until)

        sql = f"""
            SELECT
                {group_expr} AS label,
                COUNT(*)                                           AS calls,
                COALESCE(SUM(json_extract(data, '$.tokens.input')),     0) AS input_tokens,
                COALESCE(SUM(json_extract(data, '$.tokens.output')),    0) AS output_tokens,
                COALESCE(SUM(json_extract(data, '$.tokens.reasoning')), 0) AS reasoning_tokens,
                COALESCE(SUM(json_extract(data, '$.tokens.cache.read')),  0) AS cache_read,
                COALESCE(SUM(json_extract(data, '$.tokens.cache.write')), 0) AS cache_write,
                COALESCE(SUM(json_extract(data, '$.tokens.total')),    0) AS total_tokens,
                COALESCE(SUM(json_extract(data, '$.cost')),            0) AS cost
            FROM message
            WHERE json_extract(data, '$.role') = 'assistant'
              AND json_extract(data, '$.tokens.total') IS NOT NULL
              {time_clause}
            GROUP BY label
            ORDER BY {order}
        """
        if limit:
            sql += f" LIMIT {limit}"

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        return [
            UsageRow(
                label=r["label"] or "(unknown)",
                calls=r["calls"],
                tokens=TokenStats(
                    input=r["input_tokens"],
                    output=r["output_tokens"],
                    reasoning=r["reasoning_tokens"],
                    cache_read=r["cache_read"],
                    cache_write=r["cache_write"],
                    total=r["total_tokens"],
                ),
                cost=r["cost"],
            )
            for r in rows
        ]

    # ── public API ────────────────────────────────────────────────

    def daily(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[UsageRow]:
        return self._base_query(
            group_expr=(
                "date(json_extract(data, '$.time.created') / 1000, 'unixepoch', 'localtime')"
            ),
            since=since,
            until=until,
            order="label DESC",
            limit=limit,
        )

    def by_model(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[UsageRow]:
        return self._base_query(
            group_expr="json_extract(data, '$.modelID')",
            since=since,
            until=until,
            limit=limit,
        )

    def by_agent(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[UsageRow]:
        """Group by agent x model, showing which model each agent uses."""
        time_clause, params = self._time_filter(since, until)

        sql = f"""
            SELECT
                json_extract(data, '$.agent')   AS agent,
                json_extract(data, '$.modelID') AS model,
                COUNT(*)                                           AS calls,
                COALESCE(SUM(json_extract(data, '$.tokens.input')),     0) AS input_tokens,
                COALESCE(SUM(json_extract(data, '$.tokens.output')),    0) AS output_tokens,
                COALESCE(SUM(json_extract(data, '$.tokens.reasoning')), 0) AS reasoning_tokens,
                COALESCE(SUM(json_extract(data, '$.tokens.cache.read')),  0) AS cache_read,
                COALESCE(SUM(json_extract(data, '$.tokens.cache.write')), 0) AS cache_write,
                COALESCE(SUM(json_extract(data, '$.tokens.total')),    0) AS total_tokens,
                COALESCE(SUM(json_extract(data, '$.cost')),            0) AS cost
            FROM message
            WHERE json_extract(data, '$.role') = 'assistant'
              AND json_extract(data, '$.tokens.total') IS NOT NULL
              {time_clause}
            GROUP BY agent, model
            ORDER BY agent, total_tokens DESC
        """
        if limit:
            sql += f" LIMIT {limit}"

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        return [
            UsageRow(
                label=r["agent"] or "(unknown)",
                calls=r["calls"],
                tokens=TokenStats(
                    input=r["input_tokens"],
                    output=r["output_tokens"],
                    reasoning=r["reasoning_tokens"],
                    cache_read=r["cache_read"],
                    cache_write=r["cache_write"],
                    total=r["total_tokens"],
                ),
                cost=r["cost"],
                detail=r["model"],
            )
            for r in rows
        ]

    def by_provider(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[UsageRow]:
        return self._base_query(
            group_expr="json_extract(data, '$.providerID')",
            since=since,
            until=until,
            limit=limit,
        )

    def by_session(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[UsageRow]:
        """Group by session, using session title as label."""
        time_clause, params = self._time_filter(since, until, col="m.data")

        sql = f"""
            SELECT
                COALESCE(s.title, m.session_id) AS label,
                COUNT(*)                                           AS calls,
                COALESCE(SUM(json_extract(m.data, '$.tokens.input')),     0) AS input_tokens,
                COALESCE(SUM(json_extract(m.data, '$.tokens.output')),    0) AS output_tokens,
                COALESCE(SUM(json_extract(m.data, '$.tokens.reasoning')), 0) AS reasoning_tokens,
                COALESCE(SUM(json_extract(m.data, '$.tokens.cache.read')),  0) AS cache_read,
                COALESCE(SUM(json_extract(m.data, '$.tokens.cache.write')), 0) AS cache_write,
                COALESCE(SUM(json_extract(m.data, '$.tokens.total')),    0) AS total_tokens,
                COALESCE(SUM(json_extract(m.data, '$.cost')),            0) AS cost
            FROM message m
            LEFT JOIN session s ON m.session_id = s.id
            WHERE json_extract(m.data, '$.role') = 'assistant'
              AND json_extract(m.data, '$.tokens.total') IS NOT NULL
              {time_clause}
            GROUP BY m.session_id
            ORDER BY total_tokens DESC
        """
        if limit:
            sql += f" LIMIT {limit}"

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        return [
            UsageRow(
                label=r["label"] or "(untitled)",
                calls=r["calls"],
                tokens=TokenStats(
                    input=r["input_tokens"],
                    output=r["output_tokens"],
                    reasoning=r["reasoning_tokens"],
                    cache_read=r["cache_read"],
                    cache_write=r["cache_write"],
                    total=r["total_tokens"],
                ),
                cost=r["cost"],
            )
            for r in rows
        ]

    def totals(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> UsageRow:
        """Return a single aggregated row for the period."""
        rows = self._base_query(
            group_expr="'total'",
            since=since,
            until=until,
        )
        if rows:
            return rows[0]
        return UsageRow(label="total")

    def to_dicts(self, rows: list[UsageRow]) -> list[dict[str, Any]]:
        """Serialize rows for JSON output."""
        result = []
        for r in rows:
            d: dict[str, Any] = {
                "label": r.label,
                "calls": r.calls,
                "tokens": {
                    "input": r.tokens.input,
                    "output": r.tokens.output,
                    "reasoning": r.tokens.reasoning,
                    "cache_read": r.tokens.cache_read,
                    "cache_write": r.tokens.cache_write,
                    "total": r.tokens.total,
                },
                "cost": round(r.cost, 4),
            }
            if r.detail is not None:
                d["model"] = r.detail
            result.append(d)
        return result

    # ── insights queries ─────────────────────────────────────────

    def session_meta(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[SessionMeta]:
        """Session metadata with aggregated token/cost stats."""
        time_clause, params = self._time_filter(since, until, col="m.data")

        sql = f"""
            SELECT
                s.id AS session_id,
                COALESCE(s.title, s.id) AS title,
                s.parent_id,
                MIN(json_extract(m.data, '$.time.created')) AS start_ms,
                MAX(json_extract(m.data, '$.time.created')) AS end_ms,
                COUNT(m.id) AS message_count,
                COALESCE(SUM(json_extract(m.data, '$.tokens.total')), 0) AS total_tokens,
                COALESCE(SUM(json_extract(m.data, '$.cost')), 0) AS total_cost,
                s.time_updated
            FROM session s
            LEFT JOIN message m ON m.session_id = s.id
                AND json_extract(m.data, '$.role') = 'assistant'
                AND json_extract(m.data, '$.tokens.total') IS NOT NULL
                {time_clause}
            GROUP BY s.id
            ORDER BY total_tokens DESC
        """
        if limit:
            sql += f" LIMIT {limit}"

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        result: list[SessionMeta] = []
        for r in rows:
            start_ms = r["start_ms"]
            end_ms = r["end_ms"]
            if start_ms is not None:
                start_time = datetime.fromtimestamp(start_ms / 1000).astimezone()
            else:
                start_time = datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)
            if start_ms is not None and end_ms is not None:
                duration_minutes = (end_ms - start_ms) / 60000
            else:
                duration_minutes = 0.0
            result.append(
                SessionMeta(
                    session_id=r["session_id"],
                    title=r["title"] or r["session_id"],
                    parent_id=r["parent_id"],
                    start_time=start_time,
                    duration_minutes=duration_minutes,
                    message_count=r["message_count"],
                    user_message_count=0,
                    total_tokens=r["total_tokens"],
                    total_cost=r["total_cost"],
                    agents=[],
                    models=[],
                    tool_counts={},
                    tool_errors=0,
                )
            )
        return result

    def cache_efficiency(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, float]:
        """Per-model cache read ratio: cache_read / (input + cache_read)."""
        time_clause, params = self._time_filter(since, until)

        sql = f"""
            SELECT
                json_extract(data, '$.modelID') AS model,
                COALESCE(SUM(json_extract(data, '$.tokens.cache.read')), 0) AS cache_read,
                COALESCE(SUM(json_extract(data, '$.tokens.input')), 0) AS input_tokens
            FROM message
            WHERE json_extract(data, '$.role') = 'assistant'
              AND json_extract(data, '$.tokens.total') IS NOT NULL
              {time_clause}
            GROUP BY model
        """

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        result: dict[str, float] = {}
        for r in rows:
            model = r["model"]
            cache_read = r["cache_read"]
            input_tokens = r["input_tokens"]
            denominator = input_tokens + cache_read
            if model and denominator > 0:
                result[model] = cache_read / denominator
        return result

    def cost_per_1k_tokens(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, float]:
        """Per-model cost per 1,000 tokens."""
        time_clause, params = self._time_filter(since, until)

        sql = f"""
            SELECT
                json_extract(data, '$.modelID') AS model,
                COALESCE(SUM(json_extract(data, '$.cost')), 0) AS total_cost,
                COALESCE(SUM(json_extract(data, '$.tokens.total')), 0) AS total_tokens
            FROM message
            WHERE json_extract(data, '$.role') = 'assistant'
              AND json_extract(data, '$.tokens.total') IS NOT NULL
              {time_clause}
            GROUP BY model
        """

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        result: dict[str, float] = {}
        for r in rows:
            model = r["model"]
            total_tokens = r["total_tokens"]
            if model and total_tokens > 0:
                result[model] = r["total_cost"] / total_tokens * 1000
        return result

    def tool_error_rates(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, float]:
        """Per-tool error rate from the part table."""
        sql = """
            SELECT
                json_extract(data, '$.tool.name') AS tool_name,
                COUNT(*) AS total_calls,
                SUM(CASE WHEN json_extract(data, '$.state.status') = 'error'
                    THEN 1 ELSE 0 END) AS error_count
            FROM part
            WHERE json_extract(data, '$.type') = 'tool'
              AND json_extract(data, '$.tool.name') IS NOT NULL
            GROUP BY tool_name
        """

        conn = self._connect()
        try:
            rows = conn.execute(sql).fetchall()
        finally:
            conn.close()

        result: dict[str, float] = {}
        for r in rows:
            tool_name = r["tool_name"]
            total_calls = r["total_calls"]
            if tool_name and total_calls > 0:
                result[tool_name] = r["error_count"] / total_calls
        return result

    def agent_delegation(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, list[str]]:
        """Map parent session agents to their sub-agents."""
        sql = """
            SELECT
                json_extract(pm.data, '$.agent') AS parent_agent,
                json_extract(cm.data, '$.agent') AS child_agent
            FROM session s
            JOIN message cm ON cm.session_id = s.id
                AND json_extract(cm.data, '$.role') = 'assistant'
                AND json_extract(cm.data, '$.agent') IS NOT NULL
            JOIN message pm ON pm.session_id = s.parent_id
                AND json_extract(pm.data, '$.role') = 'assistant'
                AND json_extract(pm.data, '$.agent') IS NOT NULL
            WHERE s.parent_id IS NOT NULL
            GROUP BY parent_agent, child_agent
        """

        conn = self._connect()
        try:
            rows = conn.execute(sql).fetchall()
        finally:
            conn.close()

        result: dict[str, list[str]] = {}
        for r in rows:
            parent = r["parent_agent"]
            child = r["child_agent"]
            if parent and child:
                result.setdefault(parent, []).append(child)
        return result

    def build_transcript(self, session_id: str, max_chars: int = 30000) -> str:
        """Flatten session parts into a text transcript for LLM analysis."""
        sql = """
            SELECT data FROM part
            WHERE session_id = ?
            ORDER BY time_created ASC
        """

        conn = self._connect()
        try:
            rows = conn.execute(sql, [session_id]).fetchall()
        finally:
            conn.close()

        parts: list[str] = []
        for r in rows:
            try:
                d = json.loads(r["data"])
            except (json.JSONDecodeError, TypeError):
                continue

            part_type = d.get("type", "")
            if part_type == "text":
                text = d.get("text", "")[:500]
                parts.append(f"[text]: {text}")
            elif part_type == "tool":
                tool_data = d.get("tool", {})
                if isinstance(tool_data, dict):
                    tool_name = tool_data.get("name", "unknown")
                else:
                    tool_name = str(tool_data)
                state_data = d.get("state", {})
                if isinstance(state_data, dict):
                    status = state_data.get("status", "unknown")
                    tool_input = str(state_data.get("input", ""))[:200]
                else:
                    status = "unknown"
                    tool_input = ""
                parts.append(f"[tool:{tool_name}] status:{status} input:{tool_input}")
            elif part_type == "reasoning":
                text = d.get("text", "")[:200]
                parts.append(f"[thinking]: {text}")
            # Skip: step-start, step-finish, compaction, file, patch, subtask

        transcript = "\n".join(parts)

        if len(transcript) > max_chars:
            keep = int(max_chars * 0.4)
            transcript = transcript[:keep] + "\n[...truncated...]\n" + transcript[-keep:]

        return transcript

    def session_user_messages(self, session_id: str) -> list[str]:
        """Return user text messages for a session."""
        sql = """
            SELECT json_extract(data, '$.text') AS text FROM part
            WHERE session_id = ? AND json_extract(data, '$.type') = 'text'
            ORDER BY time_created ASC
        """

        conn = self._connect()
        try:
            rows = conn.execute(sql, [session_id]).fetchall()
        finally:
            conn.close()

        return [r["text"] for r in rows if r["text"]]
