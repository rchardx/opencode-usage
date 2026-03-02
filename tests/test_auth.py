"""Tests for auth credential resolution."""

from __future__ import annotations

import json

import pytest

from opencode_usage.auth import list_providers, resolve_credentials

# ── TestLoadCredentials ──────────────────────────────────────────────────────


class TestLoadCredentials:
    def test_valid_auth_json(self, tmp_path, monkeypatch):
        """Resolve credentials from valid auth.json with api type."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        auth = {"openai": {"type": "api", "key": "sk-test-key"}}
        config = {"provider": {"openai": {"options": {"baseURL": "https://api.openai.com/v1"}}}}
        oc_dir = tmp_path / "opencode"
        oc_dir.mkdir()
        (oc_dir / "auth.json").write_text(json.dumps(auth))
        (oc_dir / "opencode.json").write_text(json.dumps(config))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        creds = resolve_credentials("openai")
        assert creds.api_key == "sk-test-key"
        assert creds.base_url == "https://api.openai.com/v1"

    def test_oauth_type_skipped(self, tmp_path, monkeypatch):
        """OAuth providers raise RuntimeError."""
        monkeypatch.delenv("GITHUB-COPILOT_API_KEY", raising=False)
        auth = {"github-copilot": {"type": "oauth", "key": "gho_token"}}
        oc_dir = tmp_path / "opencode"
        oc_dir.mkdir()
        (oc_dir / "auth.json").write_text(json.dumps(auth))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        with pytest.raises(RuntimeError, match="No API credentials"):
            resolve_credentials("github-copilot")

    def test_missing_auth_json(self, tmp_path, monkeypatch):
        """Missing auth.json raises RuntimeError."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        with pytest.raises(RuntimeError, match="Auth file not found"):
            resolve_credentials("openai")

    def test_env_var_fallback(self, monkeypatch):
        """Env vars take priority over auth files."""
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost/v1")
        creds = resolve_credentials("openai")
        assert creds.api_key == "env-key"
        assert creds.base_url == "http://localhost/v1"

    def test_list_providers(self, tmp_path, monkeypatch):
        """list_providers returns only api-type providers."""
        auth = {
            "openai": {"type": "api", "key": "sk-1"},
            "copilot": {"type": "oauth", "key": "gho_1"},
            "anthropic": {"type": "api", "key": "sk-2"},
        }
        oc_dir = tmp_path / "opencode"
        oc_dir.mkdir()
        (oc_dir / "auth.json").write_text(json.dumps(auth))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        providers = list_providers()
        assert "openai" in providers
        assert "anthropic" in providers
        assert "copilot" not in providers

    def test_model_override(self, monkeypatch):
        """Explicit model param overrides default gpt-4o-mini."""
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        creds = resolve_credentials("openai", model="gpt-4o")
        assert creds.model == "gpt-4o"

    def test_default_model(self, monkeypatch):
        """Default model is gpt-4o-mini when not specified."""
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        creds = resolve_credentials("openai")
        assert creds.model == "gpt-4o-mini"
