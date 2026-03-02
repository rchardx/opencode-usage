"""Rich table rendering for usage stats."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from .db import UsageRow

console = Console()


def configure_console(*, no_color: bool = False) -> None:
    """Reconfigure the module-level console (e.g. for --no-color)."""
    global console
    console = Console(no_color=no_color)


def _fmt_tokens(n: int) -> str:
    """Human-readable token count."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_cost(c: float) -> str:
    if c == 0:
        return "-"
    if c < 0.01:
        return f"${c:.4f}"
    return f"${c:.2f}"


_BAR_FULL = "█"
_BAR_EMPTY = "░"
_BAR_WIDTH_DEFAULT = 8


def _spark_bar(value: int, max_value: int, width: int = _BAR_WIDTH_DEFAULT) -> str:
    """Horizontal bar proportional to value/max, fixed *width* characters."""
    if width < 1:
        width = 1
    if max_value <= 0 or value <= 0:
        return _BAR_EMPTY * width
    filled = max(1, round(value / max_value * width))
    filled = min(filled, width)
    return _BAR_FULL * filled + _BAR_EMPTY * (width - filled)


def _fmt_delta(pct: float) -> str:
    """Format a percentage delta with color and arrow."""
    if pct > 0:
        return f"[red]↑{pct:.0f}%[/]"
    if pct < 0:
        return f"[green]↓{abs(pct):.0f}%[/]"
    return "[dim]→0%[/]"


def _short_model(name: str) -> str:
    """Abbreviate common model names to save table width."""
    import re

    # Strip vendor prefix: "vendor-variant-1-2-20251016" → "variant-1-2"
    m = re.match(r"\w+-([a-z]\w+)-(\d+-\d+)(?:-\d+)?$", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    # gemini-3-pro-preview → gemini-3-pro
    name = re.sub(r"-preview$", "", name)
    # grok-code-fast-1 → grok-fast-1
    name = name.replace("grok-code-", "grok-")
    # minimax-m2.5-free → minimax-m2.5
    name = re.sub(r"-free$", "", name)
    return name


def _make_table(
    title: str,
    label_header: str,
    rows: list[UsageRow],
    show_breakdown: bool = True,
    show_detail: str | None = None,
    trend_values: list[int] | None = None,
    deltas: list[float | None] | None = None,
) -> Table:
    table = Table(
        title=title,
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        title_style="bold white",
        pad_edge=True,
    )

    label_max = 24 if show_detail else 30
    detail_max = 18 if show_detail else 0

    # Estimate fixed column widths (content + padding + borders)
    # Each column has ~3 chars overhead (padding + border).
    col_overhead = 3
    fixed_width = label_max + col_overhead  # label
    if show_detail:
        fixed_width += detail_max + col_overhead
    fixed_width += 5 + col_overhead  # Calls
    if show_breakdown:
        fixed_width += (6 + col_overhead) * 4  # Input, Output, Cache R, Cache W
    fixed_width += (7 + col_overhead) * 2  # Total, Cost
    if deltas is not None:
        fixed_width += 6 + col_overhead
    fixed_width += 4  # table outer borders + edge padding

    # Compute trend bar width from remaining terminal space
    term_width = console.width or 80
    bar_width = min(24, max(_BAR_WIDTH_DEFAULT, term_width - fixed_width - col_overhead))

    table.add_column(label_header, style="bold", no_wrap=True, max_width=label_max)
    if show_detail:
        table.add_column(show_detail, style="dim cyan", no_wrap=True, max_width=detail_max)
    table.add_column("Calls", justify="right", style="magenta", min_width=5)
    if show_breakdown:
        table.add_column("Input", justify="right", style="green", min_width=6)
        table.add_column("Output", justify="right", style="yellow", min_width=6)
        table.add_column("Cache R", justify="right", style="dim", min_width=6)
        table.add_column("Cache W", justify="right", style="dim", min_width=6)
    table.add_column("Total", justify="right", style="bold white", min_width=7)
    table.add_column("Cost", justify="right", style="bold red", min_width=7)
    if trend_values is not None:
        table.add_column("Trend", justify="left", style="cyan", no_wrap=True, min_width=bar_width)
    if deltas is not None:
        table.add_column("Δ", justify="right", min_width=6)

    # Precompute max for sparkline
    trend_max = max(trend_values) if trend_values else 0

    # Track previous label for deduplication + group separators
    prev_label = None
    for _i, r in enumerate(rows):
        # Insert blank separator between agent groups
        if show_detail and prev_label is not None and r.label != prev_label:
            table.add_section()

        display_label = r.label if r.label != prev_label else ""
        prev_label = r.label

        cols: list[str] = [display_label]
        if show_detail:
            cols.append(_short_model(r.detail) if r.detail else "")
        cols.append(str(r.calls))
        if show_breakdown:
            cols.extend(
                [
                    _fmt_tokens(r.tokens.input),
                    _fmt_tokens(r.tokens.output),
                    _fmt_tokens(r.tokens.cache_read),
                    _fmt_tokens(r.tokens.cache_write),
                ]
            )
        cols.extend([_fmt_tokens(r.tokens.total), _fmt_cost(r.cost)])
        if trend_values is not None:
            tv = trend_values[_i] if _i < len(trend_values) else 0
            cols.append(_spark_bar(tv, trend_max, bar_width))
        if deltas is not None:
            d = deltas[_i] if _i < len(deltas) else None
            cols.append(_fmt_delta(d) if d is not None else "[dim]-[/]")
        table.add_row(*cols)

    return table


def render_summary(
    total: UsageRow,
    period: str,
    prev_total: UsageRow | None = None,
) -> None:
    """Print a one-line summary panel."""
    text = Text()
    text.append("  Calls: ", style="dim")
    text.append(f"{total.calls:,}", style="bold magenta")
    if prev_total is not None and prev_total.calls > 0:
        pct = (total.calls - prev_total.calls) / prev_total.calls * 100
        text.append(Text.from_markup(f" {_fmt_delta(pct)}"))
    text.append("  │  Tokens: ", style="dim")
    text.append(_fmt_tokens(total.tokens.total), style="bold white")
    if prev_total is not None and prev_total.tokens.total > 0:
        pct = (total.tokens.total - prev_total.tokens.total) / prev_total.tokens.total * 100
        text.append(Text.from_markup(f" {_fmt_delta(pct)}"))
    text.append("  │  Cost: ", style="dim")
    text.append(_fmt_cost(total.cost), style="bold red")
    if prev_total is not None and prev_total.cost > 0:
        pct = (total.cost - prev_total.cost) / prev_total.cost * 100
        text.append(Text.from_markup(f" {_fmt_delta(pct)}"))
    console.print(Panel(text, title=f"[bold]OpenCode Usage — {period}[/bold]", border_style="blue"))


def render_daily(rows: list[UsageRow], period: str) -> None:
    """Render the daily breakdown table."""
    trend = [r.tokens.total for r in rows]
    table = _make_table(
        title=f"Daily Usage ({period})",
        label_header="Date",
        rows=rows,
        show_breakdown=True,
        trend_values=trend,
    )
    console.print(table)


def render_grouped(
    rows: list[UsageRow],
    group_by: str,
    period: str,
    deltas: list[float | None] | None = None,
) -> None:
    """Render a grouped breakdown table."""
    label_map = {
        "model": "Model",
        "agent": "Agent",
        "provider": "Provider",
        "session": "Session",
    }
    label_header = label_map.get(group_by, group_by.title())

    # Agent view has extra Model column — skip breakdown to save width
    show_breakdown = group_by not in ("session", "agent")

    # For agent view, show model as an extra column
    show_detail = "Model" if group_by == "agent" else None

    table = _make_table(
        title=f"Usage by {label_header} ({period})",
        label_header=label_header,
        rows=rows,
        show_breakdown=show_breakdown,
        show_detail=show_detail,
        deltas=deltas,
    )
    console.print(table)
