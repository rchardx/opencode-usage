"""Thin wrapper around the ``opencode`` CLI for dynamic path/config resolution.

Results are cached per-process so the CLI is invoked at most once per command.
Every function falls back to the legacy XDG-based heuristic when the binary is
not installed or the command fails.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

# ── low-level helpers ────────────────────────────────────────


def _find_opencode() -> str | None:
    """Return the absolute path to the ``opencode`` binary, or *None*."""
    return shutil.which("opencode")


@lru_cache(maxsize=1)
def _run_db_path() -> str | None:
    """Run ``opencode db path`` and return the trimmed output."""
    binary = _find_opencode()
    if binary is None:
        return None
    try:
        result = subprocess.run(
            [binary, "db", "path"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


@lru_cache(maxsize=1)
def _run_debug_paths() -> dict[str, str]:
    """Run ``opencode debug paths`` and parse the TSV output into a dict.

    Example CLI output::

        home       /home/user
        data       /home/user/.local/share/opencode
        config     /home/user/.config/opencode
        ...

    Returns an empty dict on failure.
    """
    binary = _find_opencode()
    if binary is None:
        return {}
    try:
        result = subprocess.run(
            [binary, "debug", "paths"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {}
        paths: dict[str, str] = {}
        for line in result.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                paths[parts[0]] = parts[1]
        return paths
    except (OSError, subprocess.TimeoutExpired):
        return {}


# ── XDG fallbacks (legacy behaviour) ────────────────────────


def _xdg_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def _xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


# ── public API ───────────────────────────────────────────────


def get_db_path() -> Path:
    """Return the OpenCode database path.

    Resolution order:
    1. ``OPENCODE_DB`` environment variable (explicit override).
    2. ``opencode db path`` CLI output.
    3. Legacy XDG-based default.
    """
    if custom := os.environ.get("OPENCODE_DB"):
        return Path(custom)
    cli_path = _run_db_path()
    if cli_path:
        return Path(cli_path)
    return _xdg_data_home() / "opencode" / "opencode.db"


def get_data_dir() -> Path:
    """Return the OpenCode data directory (e.g. ``~/.local/share/opencode``)."""
    paths = _run_debug_paths()
    if data := paths.get("data"):
        return Path(data)
    return _xdg_data_home() / "opencode"


def get_config_dir() -> Path:
    """Return the OpenCode config directory (e.g. ``~/.config/opencode``)."""
    paths = _run_debug_paths()
    if config := paths.get("config"):
        return Path(config)
    return _xdg_config_home() / "opencode"


def get_auth_path() -> Path:
    """Return the path to OpenCode's ``auth.json``."""
    return get_data_dir() / "auth.json"


def get_config_path() -> Path:
    """Return the path to OpenCode's ``opencode.json`` config file."""
    return get_config_dir() / "opencode.json"


@lru_cache(maxsize=1)
def run_models() -> list[str]:
    """Run ``opencode models`` and return the list of model identifiers."""
    binary = _find_opencode()
    if binary is None:
        return []
    try:
        result = subprocess.run(
            [binary, "models"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return []
