"""Session data extraction functions for OpenCode insights."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .types import AggregatedStats, SessionMeta


def _connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a read-only SQLite connection."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _time_params(
    since: datetime | None,
    until: datetime | None = None,
) -> tuple[str, list[Any]]:
    """Return WHERE clause fragments for message time filtering."""
    params: list[Any] = []
    clauses: list[str] = []
    if since:
        clauses.append("json_extract(m.data, '$.time.created') >= ?")
        params.append(int(since.timestamp() * 1000))
    if until:
        clauses.append("json_extract(m.data, '$.time.created') < ?")
        params.append(int(until.timestamp() * 1000))
    where = ("AND " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _session_time_params(
    since: datetime | None,
    until: datetime | None = None,
) -> tuple[str, list[Any]]:
    """Return WHERE clause fragments for session time filtering."""
    params: list[Any] = []
    clauses: list[str] = []
    if since:
        clauses.append("s.time_created >= ?")
        params.append(int(since.timestamp() * 1000))
    if until:
        clauses.append("s.time_created < ?")
        params.append(int(until.timestamp() * 1000))
    where = ("AND " + " AND ".join(clauses)) if clauses else ""
    return where, params


# ── T5: Session Filtering & Metadata ─────────────────────────


def filter_sessions(
    db_path: Path | str,
    since: datetime | None,
    until: datetime | None = None,
) -> list[str]:
    """Return root session IDs with sufficient activity in the time range."""
    time_clause, params = _time_params(since, until)
    sql = f"""
        SELECT s.id,
            COUNT(CASE WHEN json_extract(m.data, '$.role') = 'user'
                THEN 1 END) AS user_count,
            MAX(json_extract(m.data, '$.time.created'))
                - MIN(json_extract(m.data, '$.time.created'))
                AS duration_ms
        FROM session s
        LEFT JOIN message m ON m.session_id = s.id
        WHERE s.parent_id IS NULL
        {time_clause}
        GROUP BY s.id
        HAVING user_count >= 2 AND duration_ms >= 60000
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [r["id"] for r in rows]


def extract_session_meta(
    db_path: Path | str,
    session_id: str,
) -> SessionMeta:
    """Populate SessionMeta from DB for a single session."""
    conn = _connect(db_path)
    try:
        # 1. Message-level stats
        row = conn.execute(
            """
            SELECT
                s.title, s.parent_id,
                MIN(json_extract(m.data, '$.time.created'))
                    AS start_ms,
                MAX(json_extract(m.data, '$.time.created'))
                    AS end_ms,
                COUNT(CASE WHEN json_extract(m.data, '$.role') = 'user'
                    THEN 1 END) AS user_count,
                COUNT(CASE WHEN json_extract(m.data, '$.role') = 'assistant'
                    THEN 1 END) AS asst_count,
                COALESCE(SUM(
                    CASE WHEN json_extract(m.data, '$.role') = 'assistant'
                    THEN json_extract(m.data, '$.tokens.input') END
                ), 0) AS input_tok,
                COALESCE(SUM(
                    CASE WHEN json_extract(m.data, '$.role') = 'assistant'
                    THEN json_extract(m.data, '$.tokens.output') END
                ), 0) AS output_tok,
                COALESCE(SUM(
                    CASE WHEN json_extract(m.data, '$.role') = 'assistant'
                    THEN json_extract(m.data, '$.tokens.total') END
                ), 0) AS total_tok,
                COALESCE(SUM(json_extract(m.data, '$.cost')), 0)
                    AS total_cost
            FROM session s
            LEFT JOIN message m ON m.session_id = s.id
            WHERE s.id = ?
            GROUP BY s.id
            """,
            [session_id],
        ).fetchone()

        if row is None:
            return SessionMeta(id=session_id, title=session_id)

        # 2. Agent/model counts
        am_rows = conn.execute(
            """
            SELECT json_extract(data, '$.agent') AS agent,
                   json_extract(data, '$.modelID') AS model
            FROM message
            WHERE session_id = ?
              AND json_extract(data, '$.role') = 'assistant'
            """,
            [session_id],
        ).fetchall()

        agent_counts: dict[str, int] = {}
        model_counts: dict[str, int] = {}
        for amr in am_rows:
            ag = amr["agent"]
            md = amr["model"]
            if ag:
                agent_counts[ag] = agent_counts.get(ag, 0) + 1
            if md:
                model_counts[md] = model_counts.get(md, 0) + 1

        # 3. Tool counts
        tool_rows = conn.execute(
            """
            SELECT json_extract(data, '$.tool') AS tool,
                   COUNT(*) AS cnt
            FROM part
            WHERE message_id IN (
                SELECT id FROM message WHERE session_id = ?
            )
            AND json_extract(data, '$.type') = 'tool'
            GROUP BY tool
            """,
            [session_id],
        ).fetchall()
        tool_counts = {r["tool"]: r["cnt"] for r in tool_rows if r["tool"]}

        # 4. Language detection from file paths
        fp_rows = conn.execute(
            """
            SELECT json_extract(data, '$.state.input.filePath') AS fp
            FROM part
            WHERE message_id IN (
                SELECT id FROM message WHERE session_id = ?
            )
            AND json_extract(data, '$.type') = 'tool'
            AND json_extract(data, '$.tool')
                IN ('read', 'edit', 'write', 'patch')
            AND json_extract(data, '$.state.input.filePath')
                IS NOT NULL
            """,
            [session_id],
        ).fetchall()
        languages: dict[str, int] = {}
        for fpr in fp_rows:
            fp = fpr["fp"]
            if fp:
                ext = Path(fp).suffix.lstrip(".")
                if ext:
                    languages[ext] = languages.get(ext, 0) + 1

        # 5. Project path (table may not exist in all DBs)
        project_path: str | None = None
        try:
            proj_row = conn.execute(
                """
                SELECT p.worktree
                FROM project p
                JOIN session s ON s.project_id = p.id
                WHERE s.id = ?
                """,
                [session_id],
            ).fetchone()
            if proj_row:
                project_path = proj_row["worktree"]
        except sqlite3.OperationalError:
            pass

    finally:
        conn.close()

    start_ms = row["start_ms"] or 0
    end_ms = row["end_ms"] or 0
    dur = end_ms - start_ms if start_ms and end_ms else 0

    return SessionMeta(
        id=session_id,
        title=row["title"] or session_id,
        project_path=project_path,
        parent_id=row["parent_id"],
        duration_minutes=dur / 60_000,
        user_msg_count=int(row["user_count"]),
        assistant_msg_count=int(row["asst_count"]),
        input_tokens=int(row["input_tok"]),
        output_tokens=int(row["output_tok"]),
        total_tokens=int(row["total_tok"]),
        cost=float(row["total_cost"]),
        tool_counts=tool_counts,
        languages=languages,
        agent_counts=agent_counts,
        model_counts=model_counts,
        start_time=int(start_ms),
        end_time=int(end_ms),
    )


# ── T6: Transcript Reconstruction ────────────────────────────


def reconstruct_transcript(
    db_path: Path | str,
    session_id: str,
    max_chars: int = 30000,
) -> str:
    """Flatten session parts into a chronological transcript."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT p.data, m.data AS msg_data
            FROM part p
            JOIN message m ON p.message_id = m.id
            WHERE m.session_id = ?
            ORDER BY p.time_created ASC, p.id ASC
            """,
            [session_id],
        ).fetchall()
    finally:
        conn.close()

    lines: list[str] = []
    for r in rows:
        try:
            part = json.loads(r["data"])
            msg = json.loads(r["msg_data"])
        except (json.JSONDecodeError, TypeError):
            continue

        ptype = part.get("type", "")
        if ptype == "text" and part.get("text"):
            role = msg.get("role", "unknown")
            lines.append(f"[{role}]: {part['text']}")
        elif ptype == "tool":
            tool = part.get("tool", "unknown")
            state = part.get("state") or {}
            status = state.get("status", "unknown")
            lines.append(f"[assistant]: Used {tool} ({status})")
        elif ptype == "reasoning" and part.get("text"):
            text = part["text"][:200]
            lines.append(f"[assistant]: (reasoning) {text}")

    transcript = "\n".join(lines)

    if len(transcript) > max_chars:
        header = f"[TRUNCATED — showing last {max_chars} chars]\n"
        transcript = header + transcript[-max_chars:]

    return transcript


# ── T7: Statistics Extraction ─────────────────────────────────


def extract_agent_stats(
    db_path: Path | str,
    since: datetime | None,
    until: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """Agent-level aggregated statistics."""
    time_clause, params = _time_params(since, until)
    sql = f"""
        SELECT
            json_extract(m.data, '$.agent') AS agent,
            json_extract(m.data, '$.modelID') AS model,
            COUNT(*) AS calls,
            COALESCE(SUM(json_extract(m.data, '$.tokens.total')),
                0) AS tokens,
            COALESCE(SUM(json_extract(m.data, '$.cost')),
                0) AS cost
        FROM message m
        WHERE json_extract(m.data, '$.role') = 'assistant'
        {time_clause}
        GROUP BY agent, model
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    result: dict[str, dict] = {}
    for r in rows:
        agent = r["agent"]
        if not agent:
            continue
        if agent not in result:
            result[agent] = {
                "calls": 0,
                "tokens": 0,
                "cost": 0.0,
                "models_used": [],
            }
        result[agent]["calls"] += r["calls"]
        result[agent]["tokens"] += r["tokens"]
        result[agent]["cost"] += r["cost"]
        model = r["model"]
        if model and model not in result[agent]["models_used"]:
            result[agent]["models_used"].append(model)
    return result


def extract_model_stats(
    db_path: Path | str,
    since: datetime | None,
    until: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """Model-level aggregated statistics."""
    time_clause, params = _time_params(since, until)
    sql = f"""
        SELECT
            json_extract(m.data, '$.modelID') AS model,
            json_extract(m.data, '$.agent') AS agent,
            COUNT(*) AS calls,
            COALESCE(SUM(json_extract(m.data, '$.tokens.total')),
                0) AS tokens,
            COALESCE(SUM(json_extract(m.data, '$.cost')),
                0) AS cost
        FROM message m
        WHERE json_extract(m.data, '$.role') = 'assistant'
        {time_clause}
        GROUP BY model, agent
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    result: dict[str, dict] = {}
    for r in rows:
        model = r["model"]
        if not model:
            continue
        if model not in result:
            result[model] = {
                "calls": 0,
                "tokens": 0,
                "cost": 0.0,
                "agents_using": [],
            }
        result[model]["calls"] += r["calls"]
        result[model]["tokens"] += r["tokens"]
        result[model]["cost"] += r["cost"]
        agent = r["agent"]
        if agent and agent not in result[model]["agents_using"]:
            result[model]["agents_using"].append(agent)
    return result


def extract_tool_stats(
    db_path: Path | str,
    since: datetime | None,
    until: datetime | None = None,
) -> dict[str, dict[str, int]]:
    """Tool completion/error counts from the part table."""
    time_clause, params = _time_params(since, until)
    sql = f"""
        SELECT
            json_extract(p.data, '$.tool') AS tool,
            json_extract(p.data, '$.state.status') AS status,
            COUNT(*) AS cnt
        FROM part p
        JOIN message m ON p.message_id = m.id
        WHERE json_extract(p.data, '$.type') = 'tool'
        {time_clause}
        GROUP BY tool, status
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    result: dict[str, dict] = {}
    for r in rows:
        tool = r["tool"]
        if not tool:
            continue
        if tool not in result:
            result[tool] = {"completed": 0, "errors": 0, "total": 0}
        cnt = r["cnt"]
        result[tool]["total"] += cnt
        if r["status"] == "error":
            result[tool]["errors"] += cnt
        else:
            result[tool]["completed"] += cnt
    return result


def extract_todo_stats(
    db_path: Path | str,
    since: datetime | None,
    until: datetime | None = None,
) -> dict[str, int]:
    """Todo status counts joined with session for time filtering."""
    time_clause, params = _session_time_params(since, until)
    sql = f"""
        SELECT t.status, COUNT(*) AS cnt
        FROM todo t
        JOIN session s ON t.session_id = s.id
        WHERE 1=1
        {time_clause}
        GROUP BY t.status
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    return {r["status"]: r["cnt"] for r in rows if r["status"]}


def extract_delegation_stats(
    db_path: Path | str,
    since: datetime | None,
    until: datetime | None = None,
) -> dict[str, Any]:
    """Session hierarchy statistics."""
    time_clause, params = _session_time_params(since, until)
    sql = f"""
        SELECT s.id, s.parent_id
        FROM session s
        WHERE 1=1
        {time_clause}
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    root_count = 0
    sub_count = 0
    children: dict[str, list[str]] = {}
    parent_map: dict[str, str | None] = {}

    for r in rows:
        sid = r["id"]
        pid = r["parent_id"]
        parent_map[sid] = pid
        if pid is None:
            root_count += 1
        else:
            sub_count += 1
            children.setdefault(pid, []).append(sid)

    # Compute depths via parent traversal
    depths: dict[str, int] = {}
    for sid in parent_map:
        depth = 0
        current: str | None = sid
        while current is not None and parent_map.get(current) is not None:
            depth += 1
            current = parent_map[current]
        depths[sid] = depth

    max_depth = max(depths.values()) if depths else 0
    all_depths = list(depths.values())
    avg_depth = sum(all_depths) / len(all_depths) if all_depths else 0.0

    sub_types: dict[str, int] = {k: len(v) for k, v in children.items()}

    return {
        "root_sessions": root_count,
        "sub_sessions": sub_count,
        "sub_types": sub_types,
        "max_depth": max_depth,
        "avg_depth": avg_depth,
    }


def extract_project_stats(
    db_path: Path | str,
    since: datetime | None,
    until: datetime | None = None,
) -> dict[str, int]:
    """Project path to session count mapping."""
    time_clause, params = _session_time_params(since, until)
    sql = f"""
        SELECT p.worktree AS project_path, COUNT(s.id) AS cnt
        FROM session s
        JOIN project p ON s.project_id = p.id
        WHERE 1=1
        {time_clause}
        GROUP BY p.worktree
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    return {r["project_path"]: r["cnt"] for r in rows if r["project_path"]}


def aggregate_all(
    db_path: Path | str,
    session_ids: list[str],
    since: datetime | None,
    until: datetime | None = None,
) -> AggregatedStats:
    """Build AggregatedStats from extraction functions."""
    agent_stats = extract_agent_stats(db_path, since, until)
    model_stats = extract_model_stats(db_path, since, until)
    tool_stats = extract_tool_stats(db_path, since, until)

    # Query date range and totals
    time_clause, params = _time_params(since, until)
    sql = f"""
        SELECT
            MIN(json_extract(m.data, '$.time.created')) AS min_time,
            MAX(json_extract(m.data, '$.time.created')) AS max_time,
            COUNT(*) AS total_messages,
            COALESCE(SUM(json_extract(m.data, '$.cost')), 0)
                AS total_cost
        FROM message m
        WHERE json_extract(m.data, '$.role')
            IN ('user', 'assistant')
        {time_clause}
    """
    conn = _connect(db_path)
    try:
        row = conn.execute(sql, params).fetchone()
    finally:
        conn.close()

    min_time = int(row["min_time"] or 0)
    max_time = int(row["max_time"] or 0)
    total_messages = row["total_messages"] or 0
    total_cost = float(row["total_cost"] or 0.0)

    top_tools = sorted(
        [(name, d["total"]) for name, d in tool_stats.items()],
        key=lambda x: x[1],
        reverse=True,
    )[:10]
    top_agents = sorted(
        [(name, d["calls"]) for name, d in agent_stats.items()],
        key=lambda x: x[1],
        reverse=True,
    )[:10]
    top_models = sorted(
        [(name, d["calls"]) for name, d in model_stats.items()],
        key=lambda x: x[1],
        reverse=True,
    )[:10]

    return AggregatedStats(
        total_sessions=len(session_ids),
        analyzed_sessions=0,
        date_range=(min_time, max_time),
        total_messages=total_messages,
        total_cost=total_cost,
        top_tools=top_tools,
        top_agents=top_agents,
        top_models=top_models,
    )
