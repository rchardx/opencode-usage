"""CLI entry point for opencode-usage."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from typing import Any

from . import render
from .db import OpenCodeDB, UsageRow
from .render import configure_console, render_daily, render_grouped, render_summary


def _parse_since(value: str) -> datetime:
    """Parse a relative duration like '7d', '2w', '30d', '3h' or an ISO date."""
    m = re.fullmatch(r"(\d+)([dhwm])", value.strip().lower())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {
            "h": timedelta(hours=n),
            "d": timedelta(days=n),
            "w": timedelta(weeks=n),
            "m": timedelta(days=n * 30),
        }[unit]
        return datetime.now().astimezone() - delta

    # Try ISO date
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return dt
    except ValueError:
        pass

    raise argparse.ArgumentTypeError(
        f"Invalid time spec: '{value}'. Use '7d', '2w', '30d', '3h', or ISO date."
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="opencode-usage",
        description="Track and display OpenCode token usage statistics.",
    )

    p.add_argument(
        "command",
        nargs="?",
        default=None,
        choices=["today", "yesterday"],
        help="Quick shortcut: 'today' or 'yesterday'",
    )
    p.add_argument(
        "--days",
        type=int,
        default=None,
        metavar="N",
        help="Show last N days (default: 7)",
    )
    p.add_argument(
        "--since",
        type=_parse_since,
        default=None,
        metavar="SPEC",
        help="Time filter: '7d', '2w', '30d', '3h', or ISO date",
    )
    p.add_argument(
        "--by",
        choices=["model", "agent", "provider", "session", "day"],
        default=None,
        help="Group results by dimension",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Max rows to display",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    p.add_argument(
        "--compare",
        action="store_true",
        help="Compare with previous period of same length",
    )
    p.add_argument(
        "--no-color",
        action="store_true",
        dest="no_color",
        help="Disable colored output",
    )
    p.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="Path to OpenCode database (default: auto-detect)",
    )
    return p


def _resolve_since(args: argparse.Namespace) -> tuple[datetime | None, str]:
    """Resolve the effective 'since' datetime and a human-readable period label."""
    now = datetime.now().astimezone()

    if args.command == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return since, "Today"

    if args.command == "yesterday":
        yesterday = now - timedelta(days=1)
        since = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        return since, "Yesterday & Today"

    if args.since is not None:
        return args.since, f"Since {args.since.strftime('%Y-%m-%d')}"

    if args.days is not None:
        since = now - timedelta(days=args.days)
        return since, f"Last {args.days} days"

    # Default: last 7 days
    since = now - timedelta(days=7)
    return since, "Last 7 days"


def _fetch_rows(
    db: OpenCodeDB,
    group_by: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int | None = None,
) -> list[UsageRow]:
    """Fetch rows based on group_by dimension."""
    if group_by == "day":
        return db.daily(since=since, until=until, limit=limit)
    if group_by == "model":
        return db.by_model(since=since, until=until, limit=limit)
    if group_by == "agent":
        return db.by_agent(since=since, until=until, limit=limit)
    if group_by == "provider":
        return db.by_provider(since=since, until=until, limit=limit)
    if group_by == "session":
        return db.by_session(since=since, until=until, limit=limit)
    return []


def _compute_deltas(
    current: list[UsageRow],
    previous: list[UsageRow],
) -> list[float | None]:
    """Compute token delta percentages between current and previous rows."""
    prev_map: dict[str, int] = {}
    for r in previous:
        key = f"{r.label}:{r.detail}" if r.detail else r.label
        prev_map[key] = prev_map.get(key, 0) + r.tokens.total

    deltas: list[float | None] = []
    for r in current:
        key = f"{r.label}:{r.detail}" if r.detail else r.label
        prev_val = prev_map.get(key)
        if prev_val and prev_val > 0:
            deltas.append((r.tokens.total - prev_val) / prev_val * 100)
        else:
            deltas.append(None)
    return deltas


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.no_color:
        configure_console(no_color=True)

    try:
        db = OpenCodeDB(db_path=args.db)
    except FileNotFoundError as e:
        render.console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    since, period = _resolve_since(args)
    group_by = args.by or "day"

    # Compute previous period for --compare
    now = datetime.now().astimezone()
    prev_since = None
    if args.compare and since is not None:
        period_length = now - since
        prev_since = since - period_length

    # Fetch current data
    rows = _fetch_rows(db, group_by, since=since, limit=args.limit)
    total = db.totals(since=since)

    # Fetch previous period data for --compare
    prev_total = None
    prev_rows: list[UsageRow] = []
    if prev_since is not None:
        prev_total = db.totals(since=prev_since, until=since)
        if group_by != "day":
            prev_rows = _fetch_rows(db, group_by, since=prev_since, until=since, limit=args.limit)

    # JSON output
    if args.json_output:
        output: dict[str, Any] = {
            "period": period,
            "total": db.to_dicts([total])[0],
            "rows": db.to_dicts(rows),
        }
        if prev_total is not None:
            output["previous_total"] = db.to_dicts([prev_total])[0]
        if prev_rows:
            output["previous_rows"] = db.to_dicts(prev_rows)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    # Rich output
    render_summary(total, period, prev_total=prev_total)
    render.console.print()

    deltas = _compute_deltas(rows, prev_rows) if prev_rows else None

    if group_by == "day":
        render_daily(rows, period)
    else:
        render_grouped(rows, group_by, period, deltas=deltas)
