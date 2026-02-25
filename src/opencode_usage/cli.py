"""CLI entry point for opencode-usage."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta

from .db import OpenCodeDB
from .render import console, render_daily, render_grouped, render_summary


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


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        db = OpenCodeDB(db_path=args.db)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    since, period = _resolve_since(args)
    group_by = args.by

    # Default view: summary + daily breakdown
    if group_by is None:
        group_by = "day"

    # Fetch data
    if group_by == "day":
        rows = db.daily(since=since, limit=args.limit)
    elif group_by == "model":
        rows = db.by_model(since=since, limit=args.limit)
    elif group_by == "agent":
        rows = db.by_agent(since=since, limit=args.limit)
    elif group_by == "provider":
        rows = db.by_provider(since=since, limit=args.limit)
    elif group_by == "session":
        rows = db.by_session(since=since, limit=args.limit)
    else:
        rows = []

    # JSON output
    if args.json_output:
        total = db.totals(since=since)
        output = {
            "period": period,
            "total": db.to_dicts([total])[0],
            "rows": db.to_dicts(rows),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    # Rich output
    total = db.totals(since=since)
    render_summary(total, period)
    console.print()

    if group_by == "day":
        render_daily(rows, period)
    else:
        render_grouped(rows, group_by, period)
