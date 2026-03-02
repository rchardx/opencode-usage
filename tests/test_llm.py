"""Tests for the LLM HTTP client."""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from opencode_usage.insights import Credentials
from opencode_usage.llm import chat_complete, chat_complete_json

# ── TestLlmClient ────────────────────────────────────────────────────────────


class TestLlmClient:
    def _make_credentials(self) -> Credentials:
        return Credentials(
            api_key="sk-test",
            base_url="https://api.example.com/v1",
            model="gpt-4o-mini",
        )

    def _mock_response(self, content: str) -> MagicMock:
        """Build a mock urlopen response returning content."""
        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {"choices": [{"message": {"content": content}}]}
        ).encode()
        return resp

    def test_chat_completion_request(self):
        """Sends correct URL, headers, and body."""
        mock_resp = self._mock_response("Hello!")
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = chat_complete(
                self._make_credentials(),
                [{"role": "user", "content": "hi"}],
            )
            assert result == "Hello!"
            req = mock_urlopen.call_args[0][0]
            assert "chat/completions" in req.full_url
            assert req.get_header("Authorization") == "Bearer sk-test"

    def test_response_parsing(self):
        """Parses response JSON and returns content string."""
        with patch(
            "urllib.request.urlopen",
            return_value=self._mock_response("Test response"),
        ):
            result = chat_complete(
                self._make_credentials(),
                [{"role": "user", "content": "test"}],
            )
            assert result == "Test response"

    def test_http_error_401(self):
        """401 raises RuntimeError with auth message."""
        err = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
        with (
            patch("urllib.request.urlopen", side_effect=err),
            pytest.raises(RuntimeError, match="Authentication failed"),
        ):
            chat_complete(
                self._make_credentials(),
                [{"role": "user", "content": "hi"}],
            )

    def test_http_error_429(self):
        """429 raises RuntimeError with rate-limit message."""
        err = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
        with (
            patch("urllib.request.urlopen", side_effect=err),
            pytest.raises(RuntimeError, match="Rate limit exceeded"),
        ):
            chat_complete(
                self._make_credentials(),
                [{"role": "user", "content": "hi"}],
            )

    def test_network_error(self):
        """URLError raises RuntimeError with network message."""
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError("connection refused"),
            ),
            pytest.raises(RuntimeError, match="Network error"),
        ):
            chat_complete(
                self._make_credentials(),
                [{"role": "user", "content": "hi"}],
            )

    def test_chat_complete_json_parses_dict(self):
        """chat_complete_json returns parsed dict."""
        with patch(
            "urllib.request.urlopen",
            return_value=self._mock_response('{"key": "value"}'),
        ):
            result = chat_complete_json(
                self._make_credentials(),
                [{"role": "user", "content": "test"}],
            )
            assert result == {"key": "value"}

    def test_json_strips_code_fences(self):
        """chat_complete_json strips markdown code fences."""
        fenced = '```json\n{"key": "value"}\n```'
        with patch(
            "urllib.request.urlopen",
            return_value=self._mock_response(fenced),
        ):
            result = chat_complete_json(
                self._make_credentials(),
                [{"role": "user", "content": "test"}],
            )
            assert result == {"key": "value"}

    def test_non_json_response_raises(self):
        """Non-JSON response from LLM raises RuntimeError."""
        with (
            patch(
                "urllib.request.urlopen",
                return_value=self._mock_response("not json at all"),
            ),
            pytest.raises(RuntimeError, match="LLM returned non-JSON"),
        ):
            chat_complete_json(
                self._make_credentials(),
                [{"role": "user", "content": "test"}],
            )
