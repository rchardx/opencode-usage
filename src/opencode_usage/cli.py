"""CLI entry point for opencode-usage."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from typing import Any

from . import __version__, render
from .config import Config
from .config import load as load_config
from .db import OpenCodeDB, UsageRow
from .render import render_daily, render_grouped, render_summary

_MAIN_EPILOG = """
Configuration:
  Values are read from ~/.config/opencode-usage/config.toml
  (or $XDG_CONFIG_HOME/opencode-usage/config.toml). CLI flags always win
  over config values, which win over built-in defaults.

    [defaults]
    days = 7          # or weeks / months
    by = "day"        # minute, hour, day, week, month, model, agent,
                      # provider, session
    sort = "tokens"   # tokens, cost, calls

    [insights]
    preferred_models = ["opencode-go/kimi-k3"]
                      # ordered list shown first in the interactive picker

Environment:
  OPENCODE_DB          override the database path (same as --db)

Commands:
  run       token usage statistics (default)
  insights  LLM-powered usage analysis report
  providers list provider IDs (from 'opencode models')
  models    list model IDs (from 'opencode models')
  help      show help for a command

Examples:
  opencode-usage                             last 7 days, daily breakdown
  opencode-usage --days 30 --by model
  opencode-usage --weeks 2 --by month
  opencode-usage --months 3 --by week
  opencode-usage --since 3h --by hour
  opencode-usage --provider kimi-for-coding --by model --sort cost
  opencode-usage --model k3 --agent build --csv
  opencode-usage --compare --by model
  opencode-usage insights --no-llm
  opencode-usage help run
"""

_RUN_EPILOG = """
Time filtering:
  --since, --days, --weeks and --months are alternatives; the first one
  given wins in that order. --since accepts durations (7d, 2w, 30d, 3h,
  12m) or an ISO date (2026-08-01).

Grouping (--by):
  minute    per-minute buckets            hour      per-hour buckets
  day       per-day buckets (default)     week      per-week buckets (2026-W31)
  month     per-month buckets             model     per model
  agent     per agent, one row per agent x model
  provider  per provider                  session   per session (by title)

Filters (repeatable):
  --provider / --model / --agent keep only matching rows; --exclude-provider
  removes them. Matching is exact on the providerID / modelID / agent fields.

Output:
  --sort orders grouped rows by tokens (default), cost, or calls.
  --json emits machine-readable JSON, including run_rate_monthly.
  --csv emits rows as CSV; mutually exclusive with --json.
  The summary panel includes an "approx $X/mo" run-rate projection.
  --compare adds deltas against the previous period of the same length.
"""

_INSIGHTS_EPILOG = """
  Generates a self-contained HTML report. Sessions are analyzed with an
  LLM through the opencode CLI unless --no-llm is given.

  --model selects the analysis model (provider/model). When omitted, an
  interactive picker shows the models from [insights] preferred_models in
  the config file first, then the recommended list.
  --force clears the per-facet cache and re-analyzes everything.
  --concurrency caps parallel LLM workers (default: min(cpu_count, 8)).
  --no-llm skips all LLM calls and produces a data-only report.
"""


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


def _add_time_args(parser: argparse.ArgumentParser) -> None:
    """Add --days and --since to *parser* (shared by run & insights)."""
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        metavar="N",
        help="Show last N days (default: 7)",
    )
    parser.add_argument(
        "--since",
        type=_parse_since,
        default=None,
        metavar="SPEC",
        help="Time filter: '7d', '2w', '30d', '3h', or ISO date",
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="opencode-usage",
        description=(
            "Track and display OpenCode token usage statistics, read directly "
            "from OpenCode's local SQLite database."
        ),
        epilog=_MAIN_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")

    sub = p.add_subparsers(dest="subcommand", metavar="COMMAND")

    # ── run ──────────────────────────────────────────────────
    run_p = sub.add_parser(
        "run",
        help="Token usage statistics (default)",
        epilog=_RUN_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_time_args(run_p)
    run_p.add_argument(
        "--by",
        choices=["model", "agent", "provider", "session", "day"],
        default=None,
        help="Group results by dimension",
    )
    run_p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Max rows to display",
    )
    run_p.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    run_p.add_argument(
        "--compare",
        action="store_true",
        help="Compare with previous period of same length",
    )

    # ── insights ────────────────────────────────────────────
    ins_p = sub.add_parser(
        "insights",
        help="LLM-powered usage analysis report",
        epilog=_INSIGHTS_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_time_args(ins_p)
    ins_p.add_argument(
        "--model",
        default=None,
        help="Model ID for insights analysis (interactive picker if omitted)",
    )
    ins_p.add_argument(
        "--force",
        action="store_true",
        dest="force",
        help="Force re-analysis, ignoring cache",
    )
    ins_p.add_argument(
        "--concurrency",
        type=int,
        default=None,
        metavar="N",
        help="Max parallel LLM workers (default: min(cpu_count, 8))",
    )
    ins_p.add_argument(
        "--output",
        default="./opencode-insights.html",
        metavar="PATH",
        help="Output path for HTML report",
    )

    # ── help ────────────────────────────────────────────────
    help_p = sub.add_parser("help", help="Show help for a command")
    help_p.add_argument(
        "command",
        nargs="?",
        choices=("run", "insights", "providers", "models"),
        help="Command to show help for (omit for general help)",
    )

    # ── providers ───────────────────────────────────────────
    prov_p = sub.add_parser(
        "providers",
        help="List provider IDs (from 'opencode models')",
        description=(
            "List provider IDs usable with --provider / --exclude-provider. "
            "Providers marked with '*' have credentials in opencode's auth.json."
        ),
    )
    prov_p.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )

    # ── models ──────────────────────────────────────────────
    mod_p = sub.add_parser(
        "models",
        help="List model IDs (from 'opencode models')",
        description=(
            "List provider/model IDs usable with --model / --provider. "
            "Use --id to show the bare model ID as stored in the database."
        ),
    )
    mod_p.add_argument(
        "--provider",
        action="append",
        default=None,
        metavar="ID",
        help="Only list models of this provider (repeatable)",
    )
    mod_p.add_argument(
        "--id",
        action="store_true",
        help="Show only the model ID, without the provider prefix",
    )
    mod_p.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )

    return p


def _resolve_since(args: argparse.Namespace) -> tuple[datetime | None, str]:
    """Resolve the effective 'since' datetime and a human-readable period label."""
    now = datetime.now().astimezone()

    if args.since is not None:
        return args.since, f"Since {args.since.strftime('%Y-%m-%d')}"

    if args.days is not None:
        since = now - timedelta(days=args.days)
        return since, f"Last {args.days} days"

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


def _apply_config_defaults(args: argparse.Namespace, cfg: Config) -> None:
    """Fill config defaults into *args* where no CLI flag was given."""
    if args.since is None and all(
        getattr(args, attr, None) is None for attr in ("days", "weeks", "months")
    ):
        for attr in ("days", "weeks", "months"):
            value = getattr(cfg, attr, None)
            if value is not None:
                setattr(args, attr, value)
                break


def _cmd_run(args: argparse.Namespace, cfg: Config) -> None:
    """Execute the ``run`` subcommand."""
    try:
        db = OpenCodeDB()
    except FileNotFoundError as e:
        render.console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    _apply_config_defaults(args, cfg)
    since, period = _resolve_since(args)
    group_by = args.by or cfg.by or "day"

    now = datetime.now().astimezone()
    prev_since = None
    if args.compare and since is not None:
        period_length = now - since
        prev_since = since - period_length

    rows = _fetch_rows(db, group_by, since=since, limit=args.limit)
    total = db.totals(since=since)

    prev_total = None
    prev_rows: list[UsageRow] = []
    if prev_since is not None:
        prev_total = db.totals(since=prev_since, until=since)
        if group_by != "day":
            prev_rows = _fetch_rows(db, group_by, since=prev_since, until=since, limit=args.limit)

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

    render_summary(total, period, prev_total=prev_total)
    render.console.print()

    deltas = _compute_deltas(rows, prev_rows) if prev_rows else None

    if group_by == "day":
        render_daily(rows, period)
    else:
        render_grouped(rows, group_by, period, deltas=deltas)


def _cmd_insights(args: argparse.Namespace, cfg: Config) -> None:
    """Execute the ``insights`` subcommand."""
    _apply_config_defaults(args, cfg)
    if args.model is None:
        from .models import select_model_interactive

        args.model = select_model_interactive(render.console, cfg)

    from .insights.orchestrator import run_insights

    run_insights(args)


def _cmd_help(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Show help for *args.command*, or the general help when omitted."""
    if args.command:
        _build_parser().parse_args([args.command, "--help"])
    parser.print_help()


def _list_opencode_models() -> list[str]:
    """Return ``opencode models`` output, exiting with an error if unavailable."""
    from ._opencode_cli import run_models

    models = run_models()
    if not models:
        render.console.print(
            "[red]Error:[/red] Could not list models — is [bold]opencode[/bold] installed?"
        )
        sys.exit(1)
    return models


def _cmd_providers(args: argparse.Namespace) -> None:
    """Execute the ``providers`` subcommand."""
    import json as _json

    from ._opencode_cli import get_auth_path

    models = _list_opencode_models()
    providers = sorted({m.split("/", 1)[0] for m in models if "/" in m})

    connected: set[str] = set()
    try:
        with open(get_auth_path()) as f:
            connected = set(_json.load(f).keys())
    except (OSError, ValueError):
        pass

    if args.json_output:
        print(_json.dumps(providers, indent=2))
        return

    for provider in providers:
        mark = "*" if provider in connected else " "
        print(f"{mark} {provider}")
    if connected:
        render.console.print()
        render.console.print("[dim]* = connected (credentials present)[/dim]")


def _cmd_models(args: argparse.Namespace) -> None:
    """Execute the ``models`` subcommand."""
    import json as _json

    models = _list_opencode_models()

    if args.provider:
        wanted = set(args.provider)
        models = [m for m in models if m.split("/", 1)[0] in wanted]
    models = sorted(models)

    if args.json_output:
        print(_json.dumps([m.split("/", 1)[1] if args.id else m for m in models], indent=2))
        return

    for m in models:
        print(m.split("/", 1)[1] if args.id else m)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    raw = argv if argv is not None else sys.argv[1:]

    if not raw or raw[0] not in (
        "run",
        "insights",
        "help",
        "providers",
        "models",
        "-h",
        "--help",
        "-V",
        "--version",
    ):
        raw = ["run", *raw]

    args = parser.parse_args(raw)
    cfg = load_config()

    if args.subcommand == "help":
        _cmd_help(parser, args)
    elif args.subcommand == "insights":
        _cmd_insights(args, cfg)
    elif args.subcommand == "providers":
        _cmd_providers(args)
    elif args.subcommand == "models":
        _cmd_models(args)
    else:
        _cmd_run(args, cfg)
