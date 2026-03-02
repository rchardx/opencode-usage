"""Tests for opencode_usage.insights.analyze — LLM runner."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from opencode_usage.insights.analyze import (
    extract_facets,
    extract_json_from_response,
    generate_at_a_glance,
    parse_ndjson,
    run_aggregate_analysis,
    run_llm,
)
from opencode_usage.insights.types import (
    AggregatedStats,
    InsightsConfig,
    SessionFacet,
    SessionMeta,
)

# ── parse_ndjson ─────────────────────────────────────────────────────────────


class TestParseNdjson:
    def test_extracts_text_from_text_events(self):
        output = (
            '{"type":"text","part":{"text":"Hello "}}\n{"type":"text","part":{"text":"world"}}\n'
        )
        text, _cost, _tokens = parse_ndjson(output)
        assert text == "Hello world"

    def test_extracts_cost_from_step_finish(self):
        output = (
            '{"type":"step_finish","part":{"cost":0.0012,"tokens":{"input":500,"output":200}}}\n'
        )
        _text, cost, tokens = parse_ndjson(output)
        assert cost == pytest.approx(0.0012)
        assert tokens["input"] == 500
        assert tokens["output"] == 200

    def test_skips_non_json_lines(self):
        output = (
            "[config-context] Loading config from /Users/foo/.config/opencode\n"
            '{"type":"text","part":{"text":"result"}}\n'
        )
        text, _cost, _tokens = parse_ndjson(output)
        assert text == "result"

    def test_skips_unknown_event_types(self):
        output = (
            '{"type":"step_start","part":{"sessionID":"abc"}}\n'
            '{"type":"text","part":{"text":"answer"}}\n'
        )
        text, _cost, _tokens = parse_ndjson(output)
        assert text == "answer"

    def test_empty_output(self):
        text, cost, tokens = parse_ndjson("")
        assert text == ""
        assert cost == 0.0
        assert tokens == {}

    def test_multiple_text_events_concatenated(self):
        output = "\n".join(
            [
                '{"type":"text","part":{"text":"part1"}}',
                '{"type":"text","part":{"text":" part2"}}',
                '{"type":"text","part":{"text":" part3"}}',
            ]
        )
        text, _, _ = parse_ndjson(output)
        assert text == "part1 part2 part3"

    def test_full_ndjson_stream(self):
        output = (
            "[config-context] Loading config\n"
            '{"type":"step_start","part":{"sessionID":"xyz"}}\n'
            '{"type":"text","part":{"text":"{\\"key\\": \\"value\\"}"}}' + "\n"
            '{"type":"step_finish","part":{"cost":0.005,"tokens":{"input":100,"output":50}}}\n'
        )
        text, cost, tokens = parse_ndjson(output)
        assert '"key"' in text
        assert cost == pytest.approx(0.005)
        assert tokens["input"] == 100


# ── extract_json_from_response ───────────────────────────────────────────────


class TestExtractJsonFromResponse:
    def test_plain_json_passthrough(self):
        result = extract_json_from_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_strips_json_fence(self):
        text = '```json\n{"key": "value"}\n```'
        result = extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_strips_plain_fence(self):
        text = '```\n{"key": "value"}\n```'
        result = extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_strips_fence_without_newline(self):
        text = '```json{"key": "value"}```'
        result = extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_raises_on_invalid_json(self):
        with pytest.raises(ValueError, match="non-JSON"):
            extract_json_from_response("not valid json at all")

    def test_raises_on_non_dict_json(self):
        with pytest.raises(ValueError):
            extract_json_from_response("[1, 2, 3]")

    def test_nested_json(self):
        text = '{"outer": {"inner": [1, 2, 3]}}'
        result = extract_json_from_response(text)
        assert result["outer"]["inner"] == [1, 2, 3]


# ── run_llm ──────────────────────────────────────────────────────────────────


class TestRunLlm:
    def _make_result(self, returncode=0, stdout="", stderr=""):
        mock = MagicMock()
        mock.returncode = returncode
        mock.stdout = stdout
        mock.stderr = stderr
        return mock

    def test_calls_subprocess_with_correct_args(self):
        ndjson = '{"type":"text","part":{"text":"{\\"result\\": true}"}}\n'
        with patch("subprocess.run", return_value=self._make_result(stdout=ndjson)) as mock_run:
            run_llm("analyze this", model="opencode/test-model")
            args = mock_run.call_args[0][0]
            assert args[0] == "opencode"
            assert args[1] == "run"
            assert args[2] == "analyze this"
            assert "--format" in args
            assert "json" in args
            assert "--model" in args
            assert "opencode/test-model" in args
            assert "--dir" in args

    def test_raises_file_not_found_on_127(self):
        with (
            patch("subprocess.run", return_value=self._make_result(returncode=127)),
            pytest.raises(FileNotFoundError, match="opencode binary not found"),
        ):
            run_llm("prompt")

    def test_raises_permission_error_on_126(self):
        with (
            patch("subprocess.run", return_value=self._make_result(returncode=126)),
            pytest.raises(PermissionError, match="not executable"),
        ):
            run_llm("prompt")

    def test_raises_runtime_error_on_other_nonzero(self):
        mock_result = self._make_result(returncode=1, stderr="error")
        with (
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(RuntimeError, match="failed with code 1"),
        ):
            run_llm("prompt")

    def test_retries_on_timeout_and_raises_after_3(self):
        with (
            patch(
                "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="opencode", timeout=120)
            ),
            patch("time.sleep"),
            pytest.raises(TimeoutError, match="timed out after 3 attempts"),
        ):
            run_llm("prompt", timeout=1)

    def test_retries_sleep_with_backoff(self):
        sleep_calls = []
        with (
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="opencode", timeout=120),
            ),
            patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)),
            pytest.raises(TimeoutError),
        ):
            run_llm("prompt", timeout=1)
        # Should sleep twice (after attempt 0 and attempt 1, not after attempt 2)
        assert len(sleep_calls) == 2
        # Exponential backoff: 2^0 * 2 = 2, 2^1 * 2 = 4
        assert sleep_calls[0] == 2
        assert sleep_calls[1] == 4

    def test_returns_parsed_json_on_success(self):
        ndjson = '{"type":"text","part":{"text":"{\\"answer\\": 42}"}}\n'
        with patch("subprocess.run", return_value=self._make_result(stdout=ndjson)):
            result = run_llm("prompt")
            assert result == {"answer": 42}

    def test_uses_default_model(self):
        ndjson = '{"type":"text","part":{"text":"{\\"ok\\": true}"}}\n'
        with patch("subprocess.run", return_value=self._make_result(stdout=ndjson)) as mock_run:
            run_llm("prompt")
            args = mock_run.call_args[0][0]
            assert "opencode/minimax-m2.5-free" in args


# ── extract_facets ──────────────────────────────────────────────────────────


_MOCK_FACET_RESULT = {
    "underlying_goal": "implement a feature",
    "goal_categories": {"implement_feature": 1},
    "outcome": "fully_achieved",
    "satisfaction": {"satisfied": 1},
    "helpfulness": "very_helpful",
    "session_type": "single_task",
    "friction_counts": {"tool_failed": 0},
    "friction_detail": "",
    "primary_success": "correct_code_edits",
    "brief_summary": "User implemented a new feature",
}


class TestFacetExtraction:
    def _make_mock_cache(self, has_sessions=None):
        has_sessions = has_sessions or set()
        cache = MagicMock()
        cache.has.side_effect = lambda sid: sid in has_sessions
        cache.get.side_effect = lambda sid: (
            SessionFacet(session_id=sid, underlying_goal="cached") if sid in has_sessions else None
        )
        return cache

    def _make_config(self, force=False):
        return InsightsConfig(force=force)

    @patch("opencode_usage.insights.analyze.run_llm", return_value=_MOCK_FACET_RESULT)
    @patch("opencode_usage.insights.analyze.extract_session_meta")
    @patch("opencode_usage.insights.analyze.reconstruct_transcript", return_value="transcript")
    def test_extract_facets_calls_run_llm_for_uncached(self, mock_transcript, mock_meta, mock_llm):
        mock_meta.return_value = SessionMeta(id="s1", title="S1")
        cache = self._make_mock_cache(has_sessions=set())
        result = extract_facets("/tmp/db", ["s1"], self._make_config(), cache=cache)
        mock_llm.assert_called_once()
        assert "s1" in result

    @patch("opencode_usage.insights.analyze.run_llm")
    def test_extract_facets_skips_cached_sessions(self, mock_llm):
        cache = self._make_mock_cache(has_sessions={"s1"})
        result = extract_facets("/tmp/db", ["s1"], self._make_config(), cache=cache)
        mock_llm.assert_not_called()
        assert "s1" in result
        assert result["s1"].underlying_goal == "cached"

    @patch("opencode_usage.insights.analyze.run_llm", return_value=_MOCK_FACET_RESULT)
    @patch("opencode_usage.insights.analyze.extract_session_meta")
    @patch("opencode_usage.insights.analyze.reconstruct_transcript", return_value="transcript")
    def test_extract_facets_stores_in_cache(self, mock_transcript, mock_meta, mock_llm):
        mock_meta.return_value = SessionMeta(id="s1", title="S1")
        cache = self._make_mock_cache(has_sessions=set())
        extract_facets("/tmp/db", ["s1"], self._make_config(), cache=cache)
        cache.put.assert_called_once()
        assert cache.put.call_args[0][0] == "s1"

    @patch(
        "opencode_usage.insights.analyze.run_llm",
        side_effect=RuntimeError("LLM failed"),
    )
    @patch("opencode_usage.insights.analyze.extract_session_meta")
    @patch("opencode_usage.insights.analyze.reconstruct_transcript", return_value="transcript")
    def test_extract_facets_handles_llm_failure_gracefully(
        self, mock_transcript, mock_meta, mock_llm
    ):
        mock_meta.return_value = SessionMeta(id="s1", title="S1")
        cache = self._make_mock_cache(has_sessions=set())
        result = extract_facets("/tmp/db", ["s1"], self._make_config(), cache=cache)
        assert "s1" not in result

    @patch("opencode_usage.insights.analyze.run_llm", return_value=_MOCK_FACET_RESULT)
    @patch("opencode_usage.insights.analyze.extract_session_meta")
    @patch("opencode_usage.insights.analyze.reconstruct_transcript", return_value="transcript")
    def test_extract_facets_limits_to_50_new_sessions(self, mock_transcript, mock_meta, mock_llm):
        mock_meta.side_effect = lambda _db, sid: SessionMeta(id=sid, title=sid)
        cache = self._make_mock_cache(has_sessions=set())
        session_ids = [f"s{i}" for i in range(60)]
        extract_facets("/tmp/db", session_ids, self._make_config(), cache=cache)
        assert mock_llm.call_count == 50

    @patch("opencode_usage.insights.analyze.run_llm", return_value=_MOCK_FACET_RESULT)
    @patch("opencode_usage.insights.analyze.extract_session_meta")
    @patch("opencode_usage.insights.analyze.reconstruct_transcript", return_value="transcript")
    def test_extract_facets_force_reanalyzes_cached(self, mock_transcript, mock_meta, mock_llm):
        mock_meta.return_value = SessionMeta(id="s1", title="S1")
        cache = self._make_mock_cache(has_sessions={"s1"})
        result = extract_facets("/tmp/db", ["s1"], self._make_config(force=True), cache=cache)
        mock_llm.assert_called_once()
        assert "s1" in result


# ── run_aggregate_analysis ──────────────────────────────────────────────────


class TestAggregatedAnalysis:
    def _make_facets(self):
        return {
            "s1": SessionFacet(
                session_id="s1",
                underlying_goal="implement feature",
                outcome="fully_achieved",
                satisfaction={"satisfied": 1},
                friction_counts={"tool_failed": 1},
                goal_categories={"implement_feature": 1},
                brief_summary="Implemented a feature",
            ),
        }

    def _make_stats(self):
        return AggregatedStats(
            total_sessions=1,
            analyzed_sessions=1,
            date_range=(0, 1000),
            total_messages=10,
            total_cost=0.005,
            top_agents=[("build", 5)],
            top_models=[("test-model", 5)],
            top_tools=[("read", 3)],
        )

    def _make_config(self):
        return InsightsConfig()

    @patch("opencode_usage.insights.analyze.run_llm", return_value={"result": "ok"})
    def test_run_aggregate_analysis_calls_all_7_prompts(self, mock_llm):
        run_aggregate_analysis(self._make_facets(), self._make_stats(), self._make_config())
        assert mock_llm.call_count == 7

    @patch("opencode_usage.insights.analyze.run_llm", return_value={"result": "ok"})
    def test_run_aggregate_analysis_returns_all_keys(self, mock_llm):
        result = run_aggregate_analysis(
            self._make_facets(), self._make_stats(), self._make_config()
        )
        expected_keys = {
            "project_areas",
            "interaction_style",
            "agent_performance",
            "friction",
            "suggestions",
            "tool_health",
            "horizon",
        }
        assert set(result.keys()) == expected_keys

    @patch("opencode_usage.insights.analyze.run_llm")
    def test_run_aggregate_analysis_handles_prompt_failure(self, mock_llm):
        call_count = 0

        def side_effect(prompt, model=None):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise RuntimeError("LLM failed")
            return {"result": "ok"}

        mock_llm.side_effect = side_effect
        result = run_aggregate_analysis(
            self._make_facets(), self._make_stats(), self._make_config()
        )
        failed = [k for k, v in result.items() if v == {}]
        succeeded = [k for k, v in result.items() if v == {"result": "ok"}]
        assert len(failed) == 1
        assert len(succeeded) == 6


# ── generate_at_a_glance ───────────────────────────────────────────────────


class TestAtAGlance:
    def _make_stats(self):
        return AggregatedStats(
            total_sessions=1,
            analyzed_sessions=1,
            date_range=(0, 1000),
            total_messages=10,
            total_cost=0.005,
        )

    def _make_config(self):
        return InsightsConfig()

    @patch(
        "opencode_usage.insights.analyze.run_llm",
        return_value={"summary": "all good"},
    )
    def test_generate_at_a_glance_calls_run_llm(self, mock_llm):
        generate_at_a_glance({"key": {}}, self._make_stats(), self._make_config())
        mock_llm.assert_called_once()

    @patch(
        "opencode_usage.insights.analyze.run_llm",
        return_value={"summary": "all good"},
    )
    def test_generate_at_a_glance_returns_dict(self, mock_llm):
        result = generate_at_a_glance({"key": {}}, self._make_stats(), self._make_config())
        assert isinstance(result, dict)
        assert result == {"summary": "all good"}

    @patch(
        "opencode_usage.insights.analyze.run_llm",
        side_effect=RuntimeError("fail"),
    )
    def test_generate_at_a_glance_handles_failure(self, mock_llm):
        result = generate_at_a_glance({"key": {}}, self._make_stats(), self._make_config())
        assert result == {}
