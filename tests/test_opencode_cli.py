"""Tests for opencode_usage._opencode_cli path resolution."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from opencode_usage._opencode_cli import (
    _run_db_path,
    _run_debug_paths,
    get_auth_path,
    get_config_dir,
    get_config_path,
    get_data_dir,
    get_db_path,
)

# ── get_db_path ──────────────────────────────────────────────


class TestGetDbPath:
    def test_opencode_db_env_takes_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OPENCODE_DB env var overrides everything."""
        monkeypatch.setenv("OPENCODE_DB", "/custom/override.db")
        result = get_db_path()
        assert result == Path("/custom/override.db")

    def test_cli_used_when_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to opencode db path CLI output."""
        monkeypatch.delenv("OPENCODE_DB", raising=False)
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="/cli/opencode.db\n", stderr=""
        )
        with (
            patch("opencode_usage._opencode_cli.subprocess.run", return_value=mock_result),
            patch("opencode_usage._opencode_cli._find_opencode", return_value="/usr/bin/opencode"),
        ):
            result = get_db_path()
        assert result == Path("/cli/opencode.db")

    def test_xdg_fallback_when_cli_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to XDG_DATA_HOME when opencode binary not found."""
        monkeypatch.delenv("OPENCODE_DB", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", "/xdg/data")
        with patch("opencode_usage._opencode_cli._find_opencode", return_value=None):
            result = get_db_path()
        assert result == Path("/xdg/data/opencode/opencode.db")

    def test_home_fallback_when_nothing_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to ~/.local/share when no env vars and no CLI."""
        monkeypatch.delenv("OPENCODE_DB", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        with patch("opencode_usage._opencode_cli._find_opencode", return_value=None):
            result = get_db_path()
        assert result.name == "opencode.db"
        assert result.parent.name == "opencode"

    def test_cli_failure_falls_back_to_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to XDG when CLI returns non-zero."""
        monkeypatch.delenv("OPENCODE_DB", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", "/xdg/data")
        mock_result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="error")
        with (
            patch("opencode_usage._opencode_cli.subprocess.run", return_value=mock_result),
            patch("opencode_usage._opencode_cli._find_opencode", return_value="/usr/bin/opencode"),
        ):
            result = get_db_path()
        assert result == Path("/xdg/data/opencode/opencode.db")

    def test_cli_timeout_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back when CLI times out."""
        monkeypatch.delenv("OPENCODE_DB", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", "/xdg/data")
        with (
            patch(
                "opencode_usage._opencode_cli.subprocess.run",
                side_effect=subprocess.TimeoutExpired("opencode", 10),
            ),
            patch("opencode_usage._opencode_cli._find_opencode", return_value="/usr/bin/opencode"),
        ):
            result = get_db_path()
        assert result == Path("/xdg/data/opencode/opencode.db")


# ── get_data_dir / get_config_dir ────────────────────────────


class TestGetDataDir:
    def test_uses_cli_paths(self) -> None:
        """Uses opencode debug paths output."""
        paths = {"data": "/cli/data/opencode", "config": "/cli/config/opencode"}
        with (
            patch("opencode_usage._opencode_cli._find_opencode", return_value="/usr/bin/opencode"),
            patch("opencode_usage._opencode_cli._run_debug_paths", return_value=paths),
        ):
            assert get_data_dir() == Path("/cli/data/opencode")

    def test_xdg_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to XDG when CLI unavailable."""
        monkeypatch.setenv("XDG_DATA_HOME", "/xdg/data")
        with patch("opencode_usage._opencode_cli._run_debug_paths", return_value={}):
            assert get_data_dir() == Path("/xdg/data/opencode")


class TestGetConfigDir:
    def test_uses_cli_paths(self) -> None:
        """Uses opencode debug paths output."""
        paths = {"data": "/cli/data/opencode", "config": "/cli/config/opencode"}
        with patch("opencode_usage._opencode_cli._run_debug_paths", return_value=paths):
            assert get_config_dir() == Path("/cli/config/opencode")

    def test_xdg_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to XDG_CONFIG_HOME when CLI unavailable."""
        monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg/config")
        with patch("opencode_usage._opencode_cli._run_debug_paths", return_value={}):
            assert get_config_dir() == Path("/xdg/config/opencode")


# ── derived paths ────────────────────────────────────────────


class TestDerivedPaths:
    def test_auth_path(self) -> None:
        paths = {"data": "/cli/data/opencode"}
        with patch("opencode_usage._opencode_cli._run_debug_paths", return_value=paths):
            assert get_auth_path() == Path("/cli/data/opencode/auth.json")

    def test_config_path(self) -> None:
        paths = {"config": "/cli/config/opencode"}
        with patch("opencode_usage._opencode_cli._run_debug_paths", return_value=paths):
            assert get_config_path() == Path("/cli/config/opencode/opencode.json")


# ── _run_debug_paths parsing ─────────────────────────────────


class TestRunDebugPaths:
    def test_parses_tsv_output(self) -> None:
        """Correctly parses tab-separated key-value output."""
        output = (
            "home       /home/user\n"
            "data       /home/user/.local/share/opencode\n"
            "config     /home/user/.config/opencode\n"
            "cache      /home/user/.cache/opencode\n"
        )
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=output, stderr="")
        with (
            patch("opencode_usage._opencode_cli.subprocess.run", return_value=mock_result),
            patch("opencode_usage._opencode_cli._find_opencode", return_value="/usr/bin/opencode"),
        ):
            result = _run_debug_paths()
        assert result["data"] == "/home/user/.local/share/opencode"
        assert result["config"] == "/home/user/.config/opencode"
        assert result["home"] == "/home/user"
        assert result["cache"] == "/home/user/.cache/opencode"

    def test_empty_on_binary_missing(self) -> None:
        with patch("opencode_usage._opencode_cli._find_opencode", return_value=None):
            result = _run_debug_paths()
        assert result == {}


# ── caching ──────────────────────────────────────────────────


class TestCaching:
    def test_db_path_cached(self) -> None:
        """CLI is called only once even with multiple invocations."""
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="/cached/db.db\n", stderr=""
        )
        with (
            patch(
                "opencode_usage._opencode_cli.subprocess.run", return_value=mock_result
            ) as mock_run,
            patch("opencode_usage._opencode_cli._find_opencode", return_value="/usr/bin/opencode"),
        ):
            _run_db_path()
            _run_db_path()
            _run_db_path()
        assert mock_run.call_count == 1
