"""HTML report generation for OpenCode usage insights."""

from __future__ import annotations

from datetime import datetime, timezone

from opencode_usage.insights.types import AggregatedStats


def generate_css() -> str:
    """Terminal-hacker-aesthetic CSS for the insights report."""
    return """
:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #21262d;
    --text-primary: #c9d1d9;
    --text-muted: #8b949e;
    --border: #30363d;
    --accent-green: #3fb950;
    --accent-cyan: #58a6ff;
    --accent-amber: #d29922;
    --accent-red: #f85149;
    --accent-purple: #bc8cff;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 14px;
    line-height: 1.6;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 24px;
}

nav {
    position: sticky;
    top: 0;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border);
    padding: 12px 0;
    z-index: 100;
}

nav .container {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    align-items: center;
}

nav a {
    color: var(--text-muted);
    text-decoration: none;
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 4px;
    transition: color 0.2s;
}

nav a:hover { color: var(--accent-cyan); }

header {
    padding: 48px 0 32px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 48px;
}

header h1 {
    font-size: 24px;
    color: var(--accent-green);
    margin-bottom: 8px;
}

header p { color: var(--text-muted); }

section {
    margin-bottom: 48px;
}

h2 {
    font-size: 18px;
    color: var(--accent-cyan);
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
}

h3 {
    font-size: 14px;
    color: var(--text-primary);
    margin-bottom: 8px;
}

.card {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 16px;
    margin-bottom: 12px;
}

.stat-card {
    text-align: center;
    padding: 20px 16px;
}

.stat-value {
    font-size: 28px;
    font-weight: 700;
    color: var(--accent-green);
    display: block;
}

.stat-label {
    font-size: 11px;
    text-transform: uppercase;
    color: var(--text-muted);
    letter-spacing: 0.05em;
    margin-top: 4px;
    display: block;
}

.stat-subtitle {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 4px;
}

.stats-row {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 24px;
}

.stats-row .stat-card {
    flex: 1;
    min-width: 120px;
}

.bar-chart { margin-bottom: 16px; }

.bar-chart-title {
    font-size: 12px;
    color: var(--text-muted);
    text-transform: uppercase;
    margin-bottom: 8px;
}

.bar-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
}

.bar-label {
    width: 120px;
    font-size: 12px;
    color: var(--text-primary);
    text-align: right;
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.bar-track {
    flex: 1;
    height: 8px;
    background: var(--bg-tertiary);
    border-radius: 4px;
    overflow: hidden;
}

.bar-fill {
    height: 100%;
    border-radius: 4px;
}

.bar-value {
    width: 60px;
    font-size: 11px;
    color: var(--text-muted);
    flex-shrink: 0;
}

.narrative { margin-bottom: 16px; }

.narrative p {
    color: var(--text-primary);
    margin-bottom: 8px;
}

.key-insight {
    background: var(--bg-tertiary);
    border-left: 3px solid var(--accent-amber);
    padding: 12px 16px;
    margin-top: 12px;
    border-radius: 0 4px 4px 0;
    font-size: 13px;
    color: var(--accent-amber);
}

.accent-card {
    border-left: 3px solid var(--accent-green);
}

.list-items { list-style: none; padding: 0; }

.list-items li {
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
    color: var(--text-primary);
}

.list-items li:last-child { border-bottom: none; }

.list-items li::before {
    content: '\\25b8 ';
    color: var(--accent-green);
}

.tag {
    display: inline-block;
    background: var(--bg-tertiary);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2px 8px;
    font-size: 11px;
    color: var(--text-muted);
    margin: 2px;
}

footer {
    border-top: 1px solid var(--border);
    padding: 24px 0;
    margin-top: 48px;
    color: var(--text-muted);
    font-size: 12px;
    text-align: center;
}
"""


def generate_html_skeleton(title: str, body_html: str) -> str:
    """Wrap body HTML in a complete HTML document with embedded CSS."""
    css = generate_css()
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        "<style>\n"
        f"{css}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body_html}\n"
        "</body>\n"
        "</html>"
    )


def render_stat_card(label: str, value: str, subtitle: str = "") -> str:
    """Render a single stat card with a prominent value."""
    sub = f'<span class="stat-subtitle">{subtitle}</span>' if subtitle else ""
    return (
        '<div class="card stat-card">'
        f'<span class="stat-value">{value}</span>'
        f'<span class="stat-label">{label}</span>'
        f"{sub}"
        "</div>"
    )


def render_bar_chart(title: str, items: list[tuple[str, float, str]]) -> str:
    """Render a CSS-only horizontal bar chart. items = [(label, value, color)]."""
    if not items:
        return (
            f'<div class="bar-chart">'
            f'<p class="bar-chart-title">{title}</p>'
            '<p style="color:var(--text-muted)">No data</p>'
            "</div>"
        )
    max_val = max(v for _, v, _ in items) or 1
    rows = []
    for label, value, color in items:
        pct = round((value / max_val) * 100)
        rows.append(
            '<div class="bar-row">'
            f'<span class="bar-label">{label}</span>'
            '<div class="bar-track">'
            f'<div class="bar-fill" style="width:{pct}%;background:{color}"></div>'
            "</div>"
            f'<span class="bar-value">{int(value):,}</span>'
            "</div>"
        )
    return f'<div class="bar-chart"><p class="bar-chart-title">{title}</p>{"".join(rows)}</div>'


def render_stats_row(stats: list[tuple[str, str]]) -> str:
    """Render a flex row of stat cards."""
    cards = "".join(render_stat_card(label, value) for label, value in stats)
    return f'<div class="stats-row">{cards}</div>'


def render_section(section_id: str, title: str, content_html: str) -> str:
    """Render a report section with anchor id and h2 heading."""
    return f'<section id="{section_id}"><h2>{title}</h2>{content_html}</section>'


def render_narrative(paragraphs: list[str], key_insight: str = "") -> str:
    """Render narrative paragraphs with optional highlighted key insight."""
    paras = "".join(f"<p>{p}</p>" for p in paragraphs)
    insight_html = f'<div class="key-insight">{key_insight}</div>' if key_insight else ""
    return f'<div class="narrative">{paras}{insight_html}</div>'


def render_card(title: str, description: str, accent_color: str = "") -> str:
    """Render a generic info card with optional left-border accent."""
    style = (
        f' style="border-left-color:{accent_color};border-left-width:3px;border-left-style:solid"'
    )
    accent_cls = " accent-card" if accent_color else ""
    border_style = style if accent_color else ""
    return f'<div class="card{accent_cls}"{border_style}><h3>{title}</h3><p>{description}</p></div>'


def render_nav_toc(sections: list[tuple[str, str]]) -> str:
    """Render a sticky nav bar with section links."""
    links = "".join(f'<a href="#{sid}">{label}</a>' for sid, label in sections)
    return f'<nav><div class="container">{links}</div></nav>'


def _fmt_cost(cost: float) -> str:
    """Format cost as dollar string."""
    if cost == 0:
        return "$0.00"
    return f"${cost:.2f}"


def _fmt_date_range(date_range: tuple[int, int]) -> str:
    """Format ms epoch date range as human-readable string."""
    try:
        start = datetime.fromtimestamp(date_range[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        end = datetime.fromtimestamp(date_range[1] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        return f"{start} \u2192 {end}"
    except Exception:
        return "\u2014"


def generate_report(insights_data: dict) -> str:
    """Assemble the full 9-section terminal-style HTML report."""
    stats: AggregatedStats = insights_data.get("aggregated_stats") or AggregatedStats(
        total_sessions=0,
        analyzed_sessions=0,
        date_range=(0, 0),
        total_messages=0,
        total_cost=0.0,
    )
    at_a_glance = insights_data.get("at_a_glance") or {}
    project_areas = insights_data.get("project_areas") or {}
    interaction_style = insights_data.get("interaction_style") or {}
    agent_performance = insights_data.get("agent_performance") or {}
    friction = insights_data.get("friction") or {}
    suggestions = insights_data.get("suggestions") or {}
    tool_health = insights_data.get("tool_health") or {}
    horizon = insights_data.get("horizon") or {}
    delegation_stats = insights_data.get("delegation_stats") or {}

    nav_sections = [
        ("at-a-glance", "At a Glance"),
        ("work-areas", "Work Areas"),
        ("agent-performance", "Agents"),
        ("cost-intelligence", "Cost"),
        ("interaction-friction", "Interaction"),
        ("suggestions", "Suggestions"),
        ("delegation-topology", "Delegation"),
        ("tool-health", "Tools"),
        ("horizon", "Horizon"),
    ]

    nav_html = render_nav_toc(nav_sections)

    date_str = _fmt_date_range(stats.date_range)
    header_html = (
        '<header><div class="container">'
        "<h1>\u25b8 OpenCode Usage Insights</h1>"
        f"<p>{date_str} \u00b7 {stats.total_sessions} sessions"
        f" \u00b7 {stats.total_messages} messages"
        f" \u00b7 {_fmt_cost(stats.total_cost)}</p>"
        "</div></header>"
    )

    stats_html = render_stats_row(
        [
            ("Sessions", str(stats.total_sessions)),
            ("Analyzed", str(stats.analyzed_sessions)),
            ("Messages", f"{stats.total_messages:,}"),
            ("Total Cost", _fmt_cost(stats.total_cost)),
        ]
    )

    # Section 1: At a Glance
    if at_a_glance:
        working = at_a_glance.get("whats_working", "")
        hindering = at_a_glance.get("whats_hindering", "")
        quick_wins = at_a_glance.get("quick_wins") or []
        ambitious = at_a_glance.get("ambitious_workflows") or []
        wins_html = ""
        if quick_wins:
            items = "".join(f"<li>{w}</li>" for w in quick_wins)
            wins_html = f'<h3>Quick Wins</h3><ul class="list-items">{items}</ul>'
        amb_html = ""
        if ambitious:
            items = "".join(f"<li>{a}</li>" for a in ambitious)
            amb_html = f'<h3>Ambitious Workflows</h3><ul class="list-items">{items}</ul>'
        aag_content = (
            stats_html
            + (render_card("What's Working", working, "#3fb950") if working else "")
            + (render_card("What's Hindering", hindering, "#f85149") if hindering else "")
            + wins_html
            + amb_html
        )
    else:
        aag_content = (
            stats_html
            + '<p style="color:var(--text-muted)">Install opencode for AI-powered analysis</p>'
        )
    s1 = render_section("at-a-glance", "At a Glance", aag_content)

    # Section 2: What You Work On
    areas = project_areas.get("areas") or []
    if areas:
        area_cards = "".join(
            render_card(
                a.get("name", ""),
                f"{a.get('session_count', 0)} sessions \u2014 {a.get('description', '')}",
                "#58a6ff",
            )
            for a in areas
        )
        s2_content = area_cards
    else:
        s2_content = '<p style="color:var(--text-muted)">No project area data available</p>'
    s2 = render_section("work-areas", "What You Work On", s2_content)

    # Section 3: Agent Performance
    agent_items = [(a, float(c), "#3fb950") for a, c in stats.top_agents]
    agent_chart = render_bar_chart("Agent Usage (calls)", agent_items) if agent_items else ""
    agent_insight = agent_performance.get("insights", "")
    s3_content = agent_chart + (
        f'<div class="card"><p>{agent_insight}</p></div>' if agent_insight else ""
    )
    s3 = render_section("agent-performance", "Agent Performance", s3_content)

    # Section 4: Cost Intelligence
    model_items = [(m, float(c), "#58a6ff") for m, c in stats.top_models]
    model_chart = render_bar_chart("Model Usage (calls)", model_items) if model_items else ""
    s4_content = (
        render_stats_row(
            [("Total Cost", _fmt_cost(stats.total_cost)), ("Sessions", str(stats.total_sessions))]
        )
        + model_chart
    )
    s4 = render_section("cost-intelligence", "Cost Intelligence", s4_content)

    # Section 5: Interaction & Friction
    narrative_text = interaction_style.get("narrative", "")
    key_pattern = interaction_style.get("key_pattern", "")
    narrative_html = render_narrative([narrative_text], key_pattern) if narrative_text else ""
    friction_cats = friction.get("categories") or []
    friction_html = ""
    if friction_cats:
        cards = "".join(
            render_card(
                c.get("name", ""),
                f"Count: {c.get('count', 0)} \u2014 {c.get('example', '')}",
                "#f85149",
            )
            for c in friction_cats
        )
        friction_html = f"<h3>Friction Patterns</h3>{cards}"
    s5_content = narrative_html + friction_html or (
        '<p style="color:var(--text-muted)">No interaction data available</p>'
    )
    s5 = render_section("interaction-friction", "Interaction &amp; Friction", s5_content)

    # Section 6: Suggestions
    agents_md = suggestions.get("agents_md_additions") or []
    skills = suggestions.get("skill_candidates") or []
    workflows = suggestions.get("workflow_patterns") or []
    s6_parts = []
    if agents_md:
        items = "".join(f"<li>{s}</li>" for s in agents_md)
        s6_parts.append(f'<h3>AGENTS.md Additions</h3><ul class="list-items">{items}</ul>')
    if skills:
        tags = "".join(f'<span class="tag">{s}</span>' for s in skills)
        s6_parts.append(f"<h3>Skill Candidates</h3><p>{tags}</p>")
    if workflows:
        items = "".join(f"<li>{w}</li>" for w in workflows)
        s6_parts.append(f'<h3>Workflow Patterns</h3><ul class="list-items">{items}</ul>')
    s6_content = "".join(s6_parts) or (
        '<p style="color:var(--text-muted)">No suggestions available</p>'
    )
    s6 = render_section("suggestions", "Suggestions", s6_content)

    # Section 7: Delegation Topology
    sub_types = delegation_stats.get("sub_types") or {}
    deleg_items = [(k, float(v), "#bc8cff") for k, v in sub_types.items()]
    deleg_chart = render_bar_chart("Sub-session Types", deleg_items) if deleg_items else ""
    deleg_stats_html = render_stats_row(
        [
            ("Root Sessions", str(delegation_stats.get("root_sessions", 0))),
            ("Sub-sessions", str(delegation_stats.get("sub_sessions", 0))),
            ("Max Depth", str(delegation_stats.get("max_depth", 0))),
        ]
    )
    s7 = render_section(
        "delegation-topology", "Delegation Topology", deleg_stats_html + deleg_chart
    )

    # Section 8: Tool Health
    tool_items = [(t, float(c), "#d29922") for t, c in stats.top_tools]
    tool_chart = render_bar_chart("Tool Usage (calls)", tool_items) if tool_items else ""
    tool_insight = tool_health.get("insights", "")
    tool_tips = tool_health.get("tips") or []
    tips_html = ""
    if tool_tips:
        items = "".join(f"<li>{t}</li>" for t in tool_tips)
        tips_html = f'<ul class="list-items">{items}</ul>'
    s8_content = (
        tool_chart
        + (f'<div class="card"><p>{tool_insight}</p></div>' if tool_insight else "")
        + tips_html
    )
    s8 = render_section("tool-health", "Tool Health", s8_content)

    # Section 9: On the Horizon
    opportunities = horizon.get("opportunities") or []
    if opportunities:
        opp_cards = "".join(
            render_card(o.get("title", ""), o.get("description", ""), "#bc8cff")
            for o in opportunities
        )
        s9_content = opp_cards
    else:
        s9_content = '<p style="color:var(--text-muted)">No horizon data available</p>'
    s9 = render_section("horizon", "On the Horizon", s9_content)

    footer_html = (
        '<footer><div class="container"><p>Generated by opencode-usage insights</p></div></footer>'
    )

    body = (
        nav_html
        + header_html
        + f'<main class="container">{s1}{s2}{s3}{s4}{s5}{s6}{s7}{s8}{s9}</main>'
        + footer_html
    )
    return generate_html_skeleton("OpenCode Usage Insights", body)
