"""Model discovery, ranking, and interactive selection via ``opencode models``."""

from __future__ import annotations

import sys

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from ._opencode_cli import run_models

_PREFERRED: list[str] = [
    "minimax-m2.5-free",
    "kimi-k2.5",
    "glm-5",
    "claude-sonnet-4",
    "gpt-5.2",
]

_TOP_N = 5


def list_models() -> list[str]:
    """Return all connected model IDs from ``opencode models``."""
    return run_models()


def search_models(models: list[str], query: str) -> list[str]:
    """Filter *models* by case-insensitive substring match on *query*."""
    q = query.lower()
    return [m for m in models if q in m.lower()]


def _tier(model_id: str) -> tuple[int, int]:
    """Return ``(tier, preferred_index)`` for sorting.

    Tier 0 — matches a *_PREFERRED* substring (sub-sorted by preference order).
    Tier 1 — ``opencode/*`` models not in the preferred list.
    Tier 2 — ``github-copilot/*`` models.
    Tier 3 — everything else.
    """
    lower = model_id.lower()
    for idx, pattern in enumerate(_PREFERRED):
        if pattern.lower() in lower:
            return 0, idx
    if lower.startswith("opencode/"):
        return 1, 0
    if lower.startswith("github-copilot/"):
        return 2, 0
    return 3, 0


def rank_models(models: list[str]) -> list[str]:
    """Sort *models* by tier then alphabetically within each tier."""
    return sorted(models, key=lambda m: (*_tier(m), m.lower()))


def select_model_interactive(console: Console) -> str:
    """Interactive model picker — exits with code 1 if opencode is unavailable."""
    all_models = list_models()
    if not all_models:
        console.print(
            "[red]Error:[/red] Could not list models — is [bold]opencode[/bold] installed?"
        )
        sys.exit(1)

    ranked = rank_models(all_models)
    top = ranked[:_TOP_N]

    console.print()
    console.print("[cyan]Select a model for insights analysis:[/cyan]")
    _print_choices(console, top)
    console.print(f"  [dim]s[/dim]  Search from all {len(all_models)} models")
    console.print()

    while True:
        answer = Prompt.ask("Choice", console=console).strip()

        if answer.lower() == "s":
            model = _search_flow(console, ranked)
            if model is not None:
                return model
            console.print()
            _print_choices(console, top)
            console.print(f"  [dim]s[/dim]  Search from all {len(all_models)} models")
            console.print()
            continue

        try:
            idx = int(answer) - 1
            if 0 <= idx < len(top):
                selected = top[idx]
                console.print(f"  → [green]{selected}[/green]")
                return selected
        except ValueError:
            pass

        console.print(f"[yellow]Invalid choice.[/yellow] Enter 1-{len(top)} or 's' to search.")


def _print_choices(console: Console, models: list[str]) -> None:
    """Print a numbered list of model IDs."""
    for i, m in enumerate(models, 1):
        console.print(f"  [bold]{i}[/bold]  {m}")


def _search_flow(console: Console, ranked: list[str]) -> str | None:
    """Prompt for a search query, display matches, and let user pick one."""
    query = Prompt.ask("Search", console=console).strip()
    if not query:
        return None

    matches = search_models(ranked, query)
    if not matches:
        console.print(f"[yellow]No models matching '{query}'.[/yellow]")
        return None

    show = matches[:15]
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold", width=4, justify="right")
    table.add_column()
    for i, m in enumerate(show, 1):
        table.add_row(str(i), m)
    console.print(table)

    if len(matches) > 15:
        console.print(f"  [dim]… and {len(matches) - 15} more[/dim]")

    console.print()
    pick = Prompt.ask("Pick (or Enter to go back)", default="", console=console).strip()
    if not pick:
        return None

    try:
        idx = int(pick) - 1
        if 0 <= idx < len(show):
            selected = show[idx]
            console.print(f"  → [green]{selected}[/green]")
            return selected
    except ValueError:
        pass

    console.print("[yellow]Invalid choice.[/yellow]")
    return None
