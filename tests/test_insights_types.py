"""Tests for opencode_usage.insights.types dataclasses."""

from __future__ import annotations

from datetime import datetime

from opencode_usage.insights.types import (
    AggregatedStats,
    InsightsConfig,
    SessionFacet,
    SessionMeta,
)

# ── SessionFacet ─────────────────────────────────────────────────────────────


class TestSessionFacet:
    def test_required_fields(self):
        facet = SessionFacet(session_id="abc", underlying_goal="fix bug")
        assert facet.session_id == "abc"
        assert facet.underlying_goal == "fix bug"

    def test_default_dicts_are_empty(self):
        facet = SessionFacet(session_id="abc", underlying_goal="")
        assert facet.goal_categories == {}
        assert facet.satisfaction == {}
        assert facet.friction_counts == {}

    def test_default_strings_are_empty(self):
        facet = SessionFacet(session_id="abc", underlying_goal="")
        assert facet.outcome == ""
        assert facet.helpfulness == ""
        assert facet.session_type == ""
        assert facet.friction_detail == ""
        assert facet.primary_success == ""
        assert facet.brief_summary == ""

    def test_default_factories_are_independent(self):
        f1 = SessionFacet(session_id="a", underlying_goal="")
        f2 = SessionFacet(session_id="b", underlying_goal="")
        f1.goal_categories["x"] = 1
        assert "x" not in f2.goal_categories

    def test_all_fields_set(self):
        facet = SessionFacet(
            session_id="s1",
            underlying_goal="implement feature",
            goal_categories={"implement_feature": 1},
            outcome="fully_achieved",
            satisfaction={"satisfied": 2},
            helpfulness="very_helpful",
            session_type="single_task",
            friction_counts={"tool_failed": 1},
            friction_detail="read tool failed",
            primary_success="correct_code_edits",
            brief_summary="User implemented a new feature successfully.",
        )
        assert facet.outcome == "fully_achieved"
        assert facet.helpfulness == "very_helpful"
        assert facet.goal_categories["implement_feature"] == 1


# ── SessionMeta ──────────────────────────────────────────────────────────────


class TestSessionMeta:
    def test_required_fields(self):
        meta = SessionMeta(id="s1", title="My Session")
        assert meta.id == "s1"
        assert meta.title == "My Session"

    def test_defaults(self):
        meta = SessionMeta(id="s1", title="")
        assert meta.project_path is None
        assert meta.parent_id is None
        assert meta.duration_minutes == 0.0
        assert meta.user_msg_count == 0
        assert meta.assistant_msg_count == 0
        assert meta.input_tokens == 0
        assert meta.output_tokens == 0
        assert meta.total_tokens == 0
        assert meta.cost == 0.0
        assert meta.tool_counts == {}
        assert meta.languages == {}
        assert meta.agent_counts == {}
        assert meta.model_counts == {}
        assert meta.start_time == 0
        assert meta.end_time == 0

    def test_default_factories_are_independent(self):
        m1 = SessionMeta(id="a", title="")
        m2 = SessionMeta(id="b", title="")
        m1.tool_counts["read"] = 5
        assert "read" not in m2.tool_counts

    def test_all_fields_set(self):
        meta = SessionMeta(
            id="s1",
            title="Build feature",
            project_path="/home/user/project",
            parent_id=None,
            duration_minutes=45.5,
            user_msg_count=10,
            assistant_msg_count=12,
            input_tokens=5000,
            output_tokens=3000,
            total_tokens=8000,
            cost=0.05,
            tool_counts={"read": 10, "edit": 5},
            languages={"python": 8, "yaml": 2},
            agent_counts={"build": 3, "explore": 2},
            model_counts={"gpt-4o": 5},
            start_time=1700000000000,
            end_time=1700002730000,
        )
        assert meta.duration_minutes == 45.5
        assert meta.total_tokens == 8000
        assert meta.tool_counts["read"] == 10
        assert meta.languages["python"] == 8


# ── AggregatedStats ──────────────────────────────────────────────────────────


class TestAggregatedStats:
    def test_required_fields(self):
        stats = AggregatedStats(
            total_sessions=10,
            analyzed_sessions=8,
            date_range=(1700000000000, 1700100000000),
            total_messages=200,
            total_cost=1.50,
        )
        assert stats.total_sessions == 10
        assert stats.analyzed_sessions == 8
        assert stats.date_range == (1700000000000, 1700100000000)
        assert stats.total_messages == 200
        assert stats.total_cost == 1.50

    def test_defaults(self):
        stats = AggregatedStats(
            total_sessions=0,
            analyzed_sessions=0,
            date_range=(0, 0),
            total_messages=0,
            total_cost=0.0,
        )
        assert stats.top_tools == []
        assert stats.top_agents == []
        assert stats.top_models == []
        assert stats.outcome_dist == {}
        assert stats.satisfaction_dist == {}
        assert stats.friction_dist == {}

    def test_default_factories_are_independent(self):
        s1 = AggregatedStats(
            total_sessions=0,
            analyzed_sessions=0,
            date_range=(0, 0),
            total_messages=0,
            total_cost=0.0,
        )
        s2 = AggregatedStats(
            total_sessions=0,
            analyzed_sessions=0,
            date_range=(0, 0),
            total_messages=0,
            total_cost=0.0,
        )
        s1.top_tools.append(("read", 10))
        assert s2.top_tools == []

    def test_all_fields_set(self):
        stats = AggregatedStats(
            total_sessions=50,
            analyzed_sessions=45,
            date_range=(1700000000000, 1700100000000),
            total_messages=1000,
            total_cost=5.25,
            top_tools=[("read", 200), ("edit", 150)],
            top_agents=[("build", 30), ("explore", 20)],
            top_models=[("gpt-4o", 25)],
            outcome_dist={"fully_achieved": 30, "mostly_achieved": 10},
            satisfaction_dist={"satisfied": 25, "happy": 15},
            friction_dist={"tool_failed": 5},
        )
        assert stats.top_tools[0] == ("read", 200)
        assert stats.outcome_dist["fully_achieved"] == 30


# ── InsightsConfig ───────────────────────────────────────────────────────────


class TestInsightsConfig:
    def test_defaults(self):
        config = InsightsConfig(model="opencode/minimax-m2.5-free")
        assert config.model == "opencode/minimax-m2.5-free"
        assert config.days is None
        assert config.since is None
        assert config.force is False
        assert config.output_path == "./opencode-insights.html"

    def test_custom_values(self):
        dt = datetime(2025, 1, 1)
        config = InsightsConfig(
            model="opencode/gemini-3-flash",
            days=30,
            since=dt,
            force=True,
            output_path="/tmp/report.html",
        )
        assert config.model == "opencode/gemini-3-flash"
        assert config.days == 30
        assert config.since == dt
        assert config.force is True
        assert config.output_path == "/tmp/report.html"

    def test_importable(self):
        from opencode_usage.insights.types import (
            AggregatedStats,
            InsightsConfig,
            SessionFacet,
            SessionMeta,
        )

        assert SessionMeta is not None
        assert SessionFacet is not None
        assert AggregatedStats is not None
        assert InsightsConfig is not None
