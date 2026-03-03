"""Tests for opencode_usage.insights.orchestrator pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from opencode_usage.insights.orchestrator import _default_db_path, _resolve_since, run_insights
from opencode_usage.insights.types import AggregatedStats, InsightsConfig


def _make_args(**kwargs: object) -> argparse.Namespace:
    """Build a Namespace with sensible defaults for insights."""
    defaults: dict[str, object] = {
        "model": "opencode/minimax-m2.5-free",
        "days": 7,
        "since": None,
        "force": False,
        "output": "/tmp/test-insights.html",
        "command": "insights",
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _mock_stats() -> AggregatedStats:
    """Return a minimal AggregatedStats for test mocking."""
    return AggregatedStats(
        total_sessions=5,
        analyzed_sessions=5,
        date_range=(1700000000000, 1702592000000),
        total_messages=50,
        total_cost=1.0,
        top_tools=[("read", 20)],
        top_agents=[("build", 30)],
        top_models=[("deepseek-r1", 25)],
    )


# ── _resolve_since ────────────────────────────────────────────


class TestResolveSince:
    def test_uses_since_when_set(self):
        dt = datetime(2025, 1, 1).astimezone()
        config = InsightsConfig(model="test-model", since=dt)
        result = _resolve_since(config)
        assert result == dt

    def test_uses_days_when_set(self):
        config = InsightsConfig(model="test-model", days=7)
        result = _resolve_since(config)
        expected = datetime.now().astimezone() - timedelta(days=7)
        assert abs((result - expected).total_seconds()) < 5

    def test_defaults_to_30_days(self):
        config = InsightsConfig(model="test-model")
        result = _resolve_since(config)
        expected = datetime.now().astimezone() - timedelta(days=30)
        assert abs((result - expected).total_seconds()) < 5

    def test_since_takes_precedence_over_days(self):
        dt = datetime(2025, 6, 15).astimezone()
        config = InsightsConfig(model="test-model", since=dt, days=7)
        result = _resolve_since(config)
        assert result == dt

    def test_returns_datetime_type(self):
        config = InsightsConfig(model="test-model", days=14)
        result = _resolve_since(config)
        assert isinstance(result, datetime)


# ── _default_db_path ──────────────────────────────────────────


class TestDefaultDbPath:
    def test_returns_string(self):
        path = _default_db_path()
        assert isinstance(path, str)

    def test_ends_with_opencode_db(self):
        path = _default_db_path()
        assert path.endswith("opencode.db")

    def test_contains_opencode_dir(self):
        path = _default_db_path()
        assert "opencode" in path


# ── run_insights ──────────────────────────────────────────────


class TestRunInsights:
    @patch("opencode_usage.insights.orchestrator.generate_report")
    @patch("opencode_usage.insights.orchestrator.generate_at_a_glance")
    @patch("opencode_usage.insights.orchestrator.run_aggregate_analysis")
    @patch("opencode_usage.insights.orchestrator.extract_facets")
    @patch("opencode_usage.insights.orchestrator.aggregate_all")
    @patch("opencode_usage.insights.orchestrator.filter_sessions")
    def test_creates_html_file(
        self,
        mock_filter,
        mock_aggregate,
        mock_extract_facets,
        mock_run_aggregate,
        mock_at_a_glance,
        mock_generate_report,
        tmp_path,
    ):
        output_path = tmp_path / "test.html"
        mock_filter.return_value = ["s1", "s2"]
        mock_aggregate.return_value = _mock_stats()
        mock_extract_facets.return_value = {}
        mock_run_aggregate.return_value = {}
        mock_at_a_glance.return_value = {}
        mock_generate_report.return_value = "<html>test</html>"

        args = _make_args(output=str(output_path))
        run_insights(args)

        assert output_path.exists()
        assert output_path.read_text() == "<html>test</html>"

    @patch("opencode_usage.insights.orchestrator.generate_report")
    @patch("opencode_usage.insights.orchestrator.generate_at_a_glance")
    @patch("opencode_usage.insights.orchestrator.run_aggregate_analysis")
    @patch("opencode_usage.insights.orchestrator.extract_facets")
    @patch("opencode_usage.insights.orchestrator.aggregate_all")
    @patch("opencode_usage.insights.orchestrator.filter_sessions")
    def test_force_clears_cache(
        self,
        mock_filter,
        mock_aggregate,
        mock_extract_facets,
        mock_run_aggregate,
        mock_at_a_glance,
        mock_generate_report,
        tmp_path,
    ):
        output_path = tmp_path / "test.html"
        mock_filter.return_value = []
        mock_aggregate.return_value = _mock_stats()
        mock_extract_facets.return_value = {}
        mock_run_aggregate.return_value = {}
        mock_at_a_glance.return_value = {}
        mock_generate_report.return_value = "<html></html>"

        with patch("opencode_usage.insights.orchestrator.FacetCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache

            args = _make_args(output=str(output_path), force=True)
            run_insights(args)

            mock_cache.clear.assert_called_once()

    @patch("opencode_usage.insights.orchestrator.generate_report")
    @patch("opencode_usage.insights.orchestrator.generate_at_a_glance")
    @patch("opencode_usage.insights.orchestrator.run_aggregate_analysis")
    @patch("opencode_usage.insights.orchestrator.extract_facets")
    @patch("opencode_usage.insights.orchestrator.aggregate_all")
    @patch("opencode_usage.insights.orchestrator.filter_sessions")
    def test_no_force_does_not_clear_cache(
        self,
        mock_filter,
        mock_aggregate,
        mock_extract_facets,
        mock_run_aggregate,
        mock_at_a_glance,
        mock_generate_report,
        tmp_path,
    ):
        output_path = tmp_path / "test.html"
        mock_filter.return_value = []
        mock_aggregate.return_value = _mock_stats()
        mock_extract_facets.return_value = {}
        mock_run_aggregate.return_value = {}
        mock_at_a_glance.return_value = {}
        mock_generate_report.return_value = "<html></html>"

        with patch("opencode_usage.insights.orchestrator.FacetCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache

            args = _make_args(output=str(output_path), force=False)
            run_insights(args)

            mock_cache.clear.assert_not_called()

    @patch("opencode_usage.insights.orchestrator.generate_report")
    @patch("opencode_usage.insights.orchestrator.aggregate_all")
    @patch("opencode_usage.insights.orchestrator.filter_sessions")
    def test_graceful_degradation_on_file_not_found(
        self,
        mock_filter,
        mock_aggregate,
        mock_generate_report,
        tmp_path,
    ):
        """When opencode binary not found, still generates data-only report."""
        output_path = tmp_path / "test.html"
        mock_filter.return_value = ["s1"]
        mock_aggregate.return_value = _mock_stats()
        mock_generate_report.return_value = "<html>data-only</html>"

        with patch("opencode_usage.insights.orchestrator.extract_facets") as mock_ef:
            mock_ef.side_effect = FileNotFoundError("opencode not found")

            args = _make_args(output=str(output_path))
            run_insights(args)

            assert output_path.exists()
            assert "data-only" in output_path.read_text()

    @patch("opencode_usage.insights.orchestrator.generate_report")
    @patch("opencode_usage.insights.orchestrator.aggregate_all")
    @patch("opencode_usage.insights.orchestrator.filter_sessions")
    def test_graceful_degradation_on_generic_exception(
        self,
        mock_filter,
        mock_aggregate,
        mock_generate_report,
        tmp_path,
    ):
        """When LLM fails with generic error, still generates data-only report."""
        output_path = tmp_path / "test.html"
        mock_filter.return_value = ["s1"]
        mock_aggregate.return_value = _mock_stats()
        mock_generate_report.return_value = "<html>fallback</html>"

        with patch("opencode_usage.insights.orchestrator.extract_facets") as mock_ef:
            mock_ef.side_effect = RuntimeError("LLM service unavailable")

            args = _make_args(output=str(output_path))
            run_insights(args)

            assert output_path.exists()

    @patch("opencode_usage.insights.orchestrator.generate_report")
    @patch("opencode_usage.insights.orchestrator.generate_at_a_glance")
    @patch("opencode_usage.insights.orchestrator.run_aggregate_analysis")
    @patch("opencode_usage.insights.orchestrator.extract_facets")
    @patch("opencode_usage.insights.orchestrator.aggregate_all")
    @patch("opencode_usage.insights.orchestrator.filter_sessions")
    def test_uses_model_from_args(
        self,
        mock_filter,
        mock_aggregate,
        mock_extract_facets,
        mock_run_aggregate,
        mock_at_a_glance,
        mock_generate_report,
        tmp_path,
    ):
        output_path = tmp_path / "test.html"
        mock_filter.return_value = []
        mock_aggregate.return_value = _mock_stats()
        mock_extract_facets.return_value = {}
        mock_run_aggregate.return_value = {}
        mock_at_a_glance.return_value = {}
        mock_generate_report.return_value = "<html></html>"

        args = _make_args(output=str(output_path), model="opencode/custom-model")
        run_insights(args)

        # extract_facets receives config with the custom model
        call_args = mock_extract_facets.call_args
        config_arg = call_args[1].get("config") or call_args[0][2]
        assert config_arg.model == "opencode/custom-model"

    @patch("opencode_usage.insights.orchestrator.generate_report")
    @patch("opencode_usage.insights.orchestrator.generate_at_a_glance")
    @patch("opencode_usage.insights.orchestrator.run_aggregate_analysis")
    @patch("opencode_usage.insights.orchestrator.extract_facets")
    @patch("opencode_usage.insights.orchestrator.aggregate_all")
    @patch("opencode_usage.insights.orchestrator.filter_sessions")
    def test_uses_db_from_args(
        self,
        mock_filter,
        mock_aggregate,
        mock_extract_facets,
        mock_run_aggregate,
        mock_at_a_glance,
        mock_generate_report,
        tmp_path,
    ):
        output_path = tmp_path / "test.html"
        mock_filter.return_value = []
        mock_aggregate.return_value = _mock_stats()
        mock_extract_facets.return_value = {}
        mock_run_aggregate.return_value = {}
        mock_at_a_glance.return_value = {}
        mock_generate_report.return_value = "<html></html>"

        args = _make_args(output=str(output_path), db="/custom/path.db")
        run_insights(args)

        # filter_sessions receives the custom db path
        mock_filter.assert_called_once()
        assert mock_filter.call_args[0][0] == "/custom/path.db"

    @patch("opencode_usage.insights.orchestrator.generate_report")
    @patch("opencode_usage.insights.orchestrator.generate_at_a_glance")
    @patch("opencode_usage.insights.orchestrator.run_aggregate_analysis")
    @patch("opencode_usage.insights.orchestrator.extract_facets")
    @patch("opencode_usage.insights.orchestrator.aggregate_all")
    @patch("opencode_usage.insights.orchestrator.filter_sessions")
    def test_calls_generate_report_with_insights_data(
        self,
        mock_filter,
        mock_aggregate,
        mock_extract_facets,
        mock_run_aggregate,
        mock_at_a_glance,
        mock_generate_report,
        tmp_path,
    ):
        output_path = tmp_path / "test.html"
        mock_filter.return_value = ["s1"]
        mock_aggregate.return_value = _mock_stats()
        mock_extract_facets.return_value = {"s1": MagicMock()}
        mock_run_aggregate.return_value = {"project_areas": {"data": True}}
        mock_at_a_glance.return_value = {"whats_working": "test"}
        mock_generate_report.return_value = "<html></html>"

        args = _make_args(output=str(output_path))
        run_insights(args)

        mock_generate_report.assert_called_once()
        insights_data = mock_generate_report.call_args[0][0]
        assert insights_data["at_a_glance"] == {"whats_working": "test"}
        assert insights_data["project_areas"] == {"data": True}
        assert insights_data["aggregated_stats"].total_sessions == 5

    @patch("opencode_usage.insights.orchestrator.generate_report")
    @patch("opencode_usage.insights.orchestrator.generate_at_a_glance")
    @patch("opencode_usage.insights.orchestrator.run_aggregate_analysis")
    @patch("opencode_usage.insights.orchestrator.extract_facets")
    @patch("opencode_usage.insights.orchestrator.aggregate_all")
    @patch("opencode_usage.insights.orchestrator.filter_sessions")
    def test_delegation_stats_derived_from_top_agents(
        self,
        mock_filter,
        mock_aggregate,
        mock_extract_facets,
        mock_run_aggregate,
        mock_at_a_glance,
        mock_generate_report,
        tmp_path,
    ):
        output_path = tmp_path / "test.html"
        mock_filter.return_value = []
        stats = _mock_stats()
        mock_aggregate.return_value = stats
        mock_extract_facets.return_value = {}
        mock_run_aggregate.return_value = {}
        mock_at_a_glance.return_value = {}
        mock_generate_report.return_value = "<html></html>"

        args = _make_args(output=str(output_path))
        run_insights(args)

        insights_data = mock_generate_report.call_args[0][0]
        delegation = insights_data["delegation_stats"]
        assert delegation["root_sessions"] == 5
        assert delegation["sub_sessions"] == 30  # sum of top_agents counts
        assert delegation["sub_types"] == {"build": 30}

    def test_extract_phase_file_not_found_exits(self, tmp_path):
        """When DB not found in Phase 1, sys.exit(1) is called."""
        output_path = tmp_path / "test.html"

        with (
            patch(
                "opencode_usage.insights.orchestrator.filter_sessions",
                side_effect=FileNotFoundError("DB not found"),
            ),
            pytest.raises(SystemExit, match="1"),
        ):
            args = _make_args(output=str(output_path))
            run_insights(args)

    @patch("opencode_usage.insights.orchestrator.generate_report")
    @patch("opencode_usage.insights.orchestrator.generate_at_a_glance")
    @patch("opencode_usage.insights.orchestrator.run_aggregate_analysis")
    @patch("opencode_usage.insights.orchestrator.extract_facets")
    @patch("opencode_usage.insights.orchestrator.aggregate_all")
    @patch("opencode_usage.insights.orchestrator.filter_sessions")
    def test_output_path_from_config(
        self,
        mock_filter,
        mock_aggregate,
        mock_extract_facets,
        mock_run_aggregate,
        mock_at_a_glance,
        mock_generate_report,
        tmp_path,
    ):
        output_path = tmp_path / "custom-report.html"
        mock_filter.return_value = []
        mock_aggregate.return_value = _mock_stats()
        mock_extract_facets.return_value = {}
        mock_run_aggregate.return_value = {}
        mock_at_a_glance.return_value = {}
        mock_generate_report.return_value = "<html>custom</html>"

        args = _make_args(output=str(output_path))
        run_insights(args)

        assert output_path.exists()
        assert output_path.read_text() == "<html>custom</html>"
