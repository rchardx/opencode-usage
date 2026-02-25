"""SQLite query layer for OpenCode's database."""

from __future__ import annotations

import os
import platform
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _default_db_path() -> Path:
    """Resolve the OpenCode database path per platform."""
    if custom := os.environ.get("OPENCODE_DB"):
        return Path(custom)

    system = platform.system()
    if system == "Darwin":
        base = Path.home() / ".local" / "share"
    elif system == "Linux":
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    elif system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local" / "share"

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
