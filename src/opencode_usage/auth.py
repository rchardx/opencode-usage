"""Credential resolution for OpenCode insights service."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ._insights_legacy import Credentials


def _default_auth_path() -> Path:
    """Resolve the OpenCode auth.json path per platform."""
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "opencode" / "auth.json"


def _default_config_path() -> Path:
    """Resolve the OpenCode opencode.json config path per platform."""
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "opencode" / "opencode.json"


def resolve_credentials(provider: str = "openai", *, model: str | None = None) -> Credentials:
    """Resolve API credentials from environment, auth.json, and opencode.json."""
    env_key = f"{provider.upper()}_API_KEY"
    env_url = f"{provider.upper()}_BASE_URL"
    if api_key := os.environ.get(env_key):
        return Credentials(
            api_key=api_key,
            base_url=os.environ.get(env_url, ""),
            model=model or "gpt-4o-mini",
        )

    auth_path = _default_auth_path()
    if not auth_path.exists():
        raise RuntimeError(f"Auth file not found at {auth_path}")
    with open(auth_path) as f:
        auth_data = json.load(f)

    if provider not in auth_data or auth_data[provider].get("type") != "api":
        available = list_providers()
        raise RuntimeError(
            f"No API credentials for '{provider}'. Available: "
            f"{', '.join(available) if available else 'none'}"
        )

    api_key = auth_data[provider].get("key")
    base_url = ""
    config_path = _default_config_path()
    if config_path.exists():
        with open(config_path) as f:
            config_data = json.load(f)
            base_url = (
                config_data.get("provider", {})
                .get(provider, {})
                .get("options", {})
                .get("baseURL", "")
            )
    return Credentials(api_key=api_key, base_url=base_url, model=model or "gpt-4o-mini")


def list_providers() -> list[str]:
    """List available API providers from auth.json."""
    auth_path = _default_auth_path()
    if not auth_path.exists():
        return []
    with open(auth_path) as f:
        auth_data = json.load(f)
    return [
        name
        for name, entry in auth_data.items()
        if isinstance(entry, dict) and entry.get("type") == "api"
    ]
