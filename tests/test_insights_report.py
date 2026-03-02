from __future__ import annotations

from opencode_usage.insights.report import (
    generate_css,
    generate_html_skeleton,
    generate_report,
    render_bar_chart,
    render_card,
    render_narrative,
    render_nav_toc,
    render_section,
    render_stat_card,
    render_stats_row,
)
from opencode_usage.insights.types import AggregatedStats

MOCK_INSIGHTS_DATA = {
    "at_a_glance": {
        "whats_working": "Good agent delegation",
        "whats_hindering": "Too many retries",
        "quick_wins": ["Use caching", "Reduce context"],
        "ambitious_workflows": ["Automate PR reviews"],
    },
    "project_areas": {
        "areas": [{"name": "Backend API", "session_count": 10, "description": "REST endpoints"}]
    },
    "interaction_style": {
        "narrative": "You prefer iterative refinement.",
        "key_pattern": "Iterative",
    },
    "agent_performance": {"insights": "build agent is most efficient"},
    "friction": {"categories": [{"name": "Retries", "count": 5, "example": "timeout"}]},
    "suggestions": {
        "agents_md_additions": ["Add oracle for code review"],
        "skill_candidates": ["git-master"],
        "workflow_patterns": ["Use --force sparingly"],
    },
    "tool_health": {"insights": "read tool has 90 errors", "tips": ["Check file paths"]},
    "horizon": {"opportunities": [{"title": "Automate deploys", "description": "Use hooks"}]},
    "aggregated_stats": AggregatedStats(
        total_sessions=50,
        analyzed_sessions=45,
        date_range=(1700000000000, 1702592000000),
        total_messages=500,
        total_cost=12.50,
        top_tools=[("read", 200), ("edit", 150)],
        top_agents=[("build", 300), ("explore", 200)],
        top_models=[("deepseek-r1", 250)],
        outcome_dist={"fully_achieved": 30, "mostly_achieved": 15},
        satisfaction_dist={"satisfied": 25, "happy": 20},
        friction_dist={"timeout": 5, "retry": 3},
    ),
    "delegation_stats": {
        "root_sessions": 50,
        "sub_sessions": 200,
        "sub_types": {"explore": 80, "librarian": 60, "build": 60},
        "max_depth": 3,
        "avg_depth": 1.8,
    },
}


# ── TestHTMLSkeleton ──────────────────────────────────────────────────────────


class TestHTMLSkeleton:
    def test_generate_css_returns_string(self):
        css = generate_css()
        assert isinstance(css, str)
        assert len(css) > 100

    def test_generate_css_has_dark_bg(self):
        css = generate_css()
        assert "#0d1117" in css or "--bg-primary" in css

    def test_generate_css_has_monospace_font(self):
        css = generate_css()
        assert "monospace" in css

    def test_generate_css_has_accent_colors(self):
        css = generate_css()
        assert "#3fb950" in css
        assert "#58a6ff" in css

    def test_generate_html_skeleton_has_doctype(self):
        html = generate_html_skeleton("Test", "<p>body</p>")
        assert html.startswith("<!DOCTYPE html>")

    def test_generate_html_skeleton_has_charset(self):
        html = generate_html_skeleton("Test", "<p>body</p>")
        assert "charset" in html.lower()

    def test_generate_html_skeleton_embeds_css(self):
        html = generate_html_skeleton("Test", "<p>body</p>")
        assert "<style>" in html

    def test_generate_html_skeleton_has_container(self):
        html = generate_html_skeleton("Test", "<p>body</p>")
        assert "container" in html or "<main" in html


# ── TestVisualization ─────────────────────────────────────────────────────────


class TestVisualization:
    def test_render_stat_card_contains_value(self):
        html = render_stat_card("Sessions", "42", "last 30 days")
        assert "42" in html

    def test_render_stat_card_contains_label(self):
        html = render_stat_card("Sessions", "42", "last 30 days")
        assert "Sessions" in html

    def test_render_bar_chart_proportional_widths(self):
        html = render_bar_chart("Agents", [("build", 80, "#3fb950"), ("explore", 40, "#58a6ff")])
        assert "100%" in html
        assert "50%" in html

    def test_render_bar_chart_contains_labels(self):
        html = render_bar_chart("Agents", [("build", 80, "#3fb950"), ("explore", 40, "#58a6ff")])
        assert "build" in html
        assert "explore" in html

    def test_render_stats_row_contains_all_stats(self):
        html = render_stats_row([("Sessions", "50"), ("Messages", "500")])
        assert "Sessions" in html
        assert "500" in html

    def test_render_section_has_id(self):
        html = render_section("at-a-glance", "At a Glance", "<p>content</p>")
        assert 'id="at-a-glance"' in html

    def test_render_section_has_heading(self):
        html = render_section("at-a-glance", "At a Glance", "<p>content</p>")
        assert "At a Glance" in html

    def test_render_narrative_contains_insight(self):
        html = render_narrative(["para1"], "key insight")
        assert "key insight" in html

    def test_render_card_contains_title(self):
        html = render_card("My Card", "desc", "#3fb950")
        assert "My Card" in html

    def test_render_nav_toc_has_links(self):
        html = render_nav_toc([("at-a-glance", "At a Glance")])
        assert 'href="#at-a-glance"' in html


# ── TestFullReport ────────────────────────────────────────────────────────────


class TestFullReport:
    def test_generate_report_returns_string(self):
        html = generate_report(MOCK_INSIGHTS_DATA)
        assert isinstance(html, str)
        assert len(html) > 1000

    def test_generate_report_has_doctype(self):
        html = generate_report(MOCK_INSIGHTS_DATA)
        assert html.startswith("<!DOCTYPE html>")

    def test_generate_report_has_9_sections(self):
        html = generate_report(MOCK_INSIGHTS_DATA)
        for section_id in [
            "at-a-glance",
            "work-areas",
            "agent-performance",
            "cost-intelligence",
            "interaction-friction",
            "suggestions",
            "delegation-topology",
            "tool-health",
            "horizon",
        ]:
            assert f'id="{section_id}"' in html, f"Missing section: {section_id}"

    def test_generate_report_nav_has_9_links(self):
        html = generate_report(MOCK_INSIGHTS_DATA)
        assert html.count('href="#') >= 9

    def test_generate_report_no_claude_mention(self):
        html = generate_report(MOCK_INSIGHTS_DATA)
        assert "claude" not in html.lower()

    def test_generate_report_has_stats(self):
        html = generate_report(MOCK_INSIGHTS_DATA)
        assert "50" in html

    def test_generate_report_handles_empty_llm_sections(self):
        empty_data = {
            "at_a_glance": {},
            "project_areas": {},
            "interaction_style": {},
            "agent_performance": {},
            "friction": {},
            "suggestions": {},
            "tool_health": {},
            "horizon": {},
            "aggregated_stats": AggregatedStats(
                total_sessions=0,
                analyzed_sessions=0,
                date_range=(0, 0),
                total_messages=0,
                total_cost=0.0,
            ),
            "delegation_stats": {},
        }
        html = generate_report(empty_data)
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html
