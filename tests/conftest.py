"""Shared fixtures for the opencode-usage test suite."""

from __future__ import annotations

import pytest

from opencode_usage._opencode_cli import _run_db_path, _run_debug_paths


@pytest.fixture(autouse=True)
def _clear_cli_caches() -> None:
    """Clear lru_cache on CLI helpers before every test.

    The ``_opencode_cli`` module caches subprocess results with ``lru_cache``.
    Without clearing between tests, a cached value from one test leaks into
    the next, causing non-deterministic failures.
    """
    _run_db_path.cache_clear()
    _run_debug_paths.cache_clear()
