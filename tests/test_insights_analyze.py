"""Tests for opencode_usage.insights.analyze — LLM runner."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from opencode_usage.insights.analyze import (
    extract_json_from_response,
    parse_ndjson,
    run_llm,
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
