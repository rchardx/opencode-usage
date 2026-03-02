"""Orchestrate the full insights pipeline: extract → analyze → report."""

from __future__ import annotations

import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .._opencode_cli import get_db_path
from .analyze import extract_facets, generate_at_a_glance, run_aggregate_analysis
from .cache import FacetCache
from .extract import aggregate_all, filter_sessions
from .report import generate_report
from .types import InsightsConfig

if TYPE_CHECKING:
    import argparse

console = Console()


def run_insights(args: argparse.Namespace) -> None:
    """Orchestrate the full insights pipeline: extract → analyze → report."""
    # Build config from args
    config = InsightsConfig(
        model=args.model or "opencode/minimax-m2.5-free",
        days=getattr(args, "days", None),
        since=getattr(args, "since", None),
        force=getattr(args, "force", False),
        output_path=getattr(args, "output", "./opencode-insights.html"),
        concurrency=getattr(args, "concurrency", None),
    )

    db_path = getattr(args, "db", None) or _default_db_path()

    # Resolve time range
    since_dt = _resolve_since(config)

    console.print("[cyan]▸ OpenCode Insights[/cyan]")
    console.print(f"  Model: [dim]{config.model}[/dim]")
    console.print(f"  Output: [dim]{config.output_path}[/dim]")
    console.print()

    # Phase 1: Extract data
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Extracting session data...", total=None)
        try:
            session_ids = filter_sessions(db_path, since=since_dt)
            stats = aggregate_all(db_path, session_ids, since=since_dt)
        except FileNotFoundError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)
        progress.update(task, description=f"Found {len(session_ids)} sessions")

    console.print(f"  Sessions: [green]{len(session_ids)}[/green]")

    # Phase 2: LLM analysis
    cache = FacetCache()
    if config.force:
        cache.clear()

    facets: dict[str, object] = {}
    aggregate_results: dict[str, object] = {}
    at_a_glance: dict[str, object] = {}
    llm_available = True

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Analyzing sessions (0/{len(session_ids)})...", total=len(session_ids)
            )

            def on_progress(current: int, total: int) -> None:
                progress.update(
                    task,
                    completed=current,
                    description=f"Analyzing sessions ({current}/{total})...",
                )

            facets = extract_facets(
                db_path, session_ids, config, cache=cache, on_progress=on_progress
            )
            progress.update(task, description="Running aggregate analysis...")
            aggregate_results = run_aggregate_analysis(facets, stats, config)
            progress.update(task, description="Generating summary...")
            at_a_glance = generate_at_a_glance(aggregate_results, stats, config)

    except FileNotFoundError:
        llm_available = False
        console.print(
            "[yellow]Warning:[/yellow] opencode not found — generating data-only report "
            "(install opencode for full analysis)"
        )
    except Exception as e:
        llm_available = False
        warnings.warn(f"LLM analysis failed: {e}", stacklevel=2)
        console.print(f"[yellow]Warning:[/yellow] LLM analysis failed: {e}")
        console.print("Generating data-only report.")

    # Phase 3: Generate report
    insights_data = {
        "at_a_glance": at_a_glance,
        "project_areas": aggregate_results.get("project_areas", {}),
        "interaction_style": aggregate_results.get("interaction_style", {}),
        "agent_performance": aggregate_results.get("agent_performance", {}),
        "friction": aggregate_results.get("friction", {}),
        "suggestions": aggregate_results.get("suggestions", {}),
        "tool_health": aggregate_results.get("tool_health", {}),
        "horizon": aggregate_results.get("horizon", {}),
        "aggregated_stats": stats,
        "delegation_stats": {
            "root_sessions": stats.total_sessions,
            "sub_sessions": sum(stats.top_agents[i][1] for i in range(len(stats.top_agents))),
            "sub_types": dict(stats.top_agents),
            "max_depth": 0,
            "avg_depth": 0.0,
        },
    }

    html = generate_report(insights_data)

    output_path = Path(config.output_path)
    output_path.write_text(html, encoding="utf-8")

    console.print()
    console.print(f"[green]✓[/green] Report saved to [bold]{output_path}[/bold]")
    console.print(f"  Sessions analyzed: [green]{len(facets)}[/green] / {len(session_ids)}")
    if not llm_available:
        console.print("  [dim]LLM sections: not available (data-only mode)[/dim]")


def _default_db_path() -> str:
    """Return the default OpenCode database path."""
    return str(get_db_path())


def _resolve_since(config: InsightsConfig) -> datetime | None:
    """Resolve the effective since datetime from config."""
    if config.since is not None:
        return config.since
    if config.days is not None:
        return datetime.now().astimezone() - timedelta(days=config.days)
    # Default: last 30 days
    return datetime.now().astimezone() - timedelta(days=30)
