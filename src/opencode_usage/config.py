"""Persistent configuration for opencode-usage.

Values are loaded from ``~/.config/opencode-usage/config.toml``
(or ``$XDG_CONFIG_HOME/opencode-usage/config.toml``). CLI flags always win
over config values, which in turn win over built-in defaults.

Example config file::

    [defaults]
    days = 7
    by = "day"
    sort = "tokens"

    [insights]
    preferred_models = ["opencode-go/kimi-k3"]
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import tomllib


@dataclass
class Config:
    """Effective configuration with built-in defaults."""

    days: int | None = None
    weeks: int | None = None
    months: int | None = None
    by: str | None = None
    sort: str = "tokens"
    preferred_models: list[str] = field(default_factory=list)


def config_dir() -> Path:
    """Return the config directory (``~/.config/opencode-usage``)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "opencode-usage"
    return Path.home() / ".config" / "opencode-usage"


def config_path() -> Path:
    """Return the path to the config file."""
    return config_dir() / "config.toml"


def load() -> Config:
    """Load the config file; missing or malformed files yield defaults."""
    cfg = Config()
    path = config_path()
    if not path.exists():
        return cfg
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return cfg

    defaults = data.get("defaults") or {}
    insights = data.get("insights") or {}

    if isinstance(defaults.get("days"), int) and defaults["days"] > 0:
        cfg.days = defaults["days"]
    if isinstance(defaults.get("weeks"), int) and defaults["weeks"] > 0:
        cfg.weeks = defaults["weeks"]
    if isinstance(defaults.get("months"), int) and defaults["months"] > 0:
        cfg.months = defaults["months"]
    if isinstance(defaults.get("by"), str) and defaults["by"]:
        cfg.by = defaults["by"]
    if isinstance(defaults.get("sort"), str) and defaults["sort"] in ("tokens", "cost", "calls"):
        cfg.sort = defaults["sort"]
    if isinstance(insights.get("preferred_models"), list):
        cfg.preferred_models = [str(m) for m in insights["preferred_models"]]
    return cfg
