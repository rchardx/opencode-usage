"""Tests for opencode_usage.models — model discovery, ranking, and selection."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from opencode_usage.models import (
    _PREFERRED,
    _tier,
    list_models,
    rank_models,
    search_models,
    select_model_interactive,
)

# ── sample data ──────────────────────────────────────────────

_SAMPLE_MODELS = [
    "poe/gemini-2.5-pro",
    "github-copilot/claude-sonnet-4",
    "opencode/minimax-m2.5-free",
    "opencode/deepseek-r1",
    "github-copilot/gpt-5.2",
    "opencode/kimi-k2.5",
    "opencode/glm-5",
    "poe/llama-4-maverick",
]


# ── list_models ──────────────────────────────────────────────


class TestListModels:
    def test_delegates_to_run_models(self):
        with patch("opencode_usage.models.run_models", return_value=["a", "b"]):
            assert list_models() == ["a", "b"]

    def test_empty_when_opencode_unavailable(self):
        with patch("opencode_usage.models.run_models", return_value=[]):
            assert list_models() == []


# ── search_models ────────────────────────────────────────────


class TestSearchModels:
    def test_substring_match(self):
        result = search_models(_SAMPLE_MODELS, "minimax")
        assert result == ["opencode/minimax-m2.5-free"]

    def test_case_insensitive(self):
        result = search_models(_SAMPLE_MODELS, "MINIMAX")
        assert result == ["opencode/minimax-m2.5-free"]

    def test_no_match(self):
        assert search_models(_SAMPLE_MODELS, "nonexistent") == []

    def test_empty_query_matches_all(self):
        assert search_models(_SAMPLE_MODELS, "") == _SAMPLE_MODELS

    def test_multiple_matches(self):
        result = search_models(_SAMPLE_MODELS, "opencode/")
        assert len(result) == 4
        assert all(m.startswith("opencode/") for m in result)

    def test_partial_match(self):
        result = search_models(_SAMPLE_MODELS, "k2.5")
        assert result == ["opencode/kimi-k2.5"]

    def test_empty_models_list(self):
        assert search_models([], "anything") == []


# ── _tier ────────────────────────────────────────────────────


class TestTier:
    def test_preferred_tier_zero(self):
        tier, idx = _tier("opencode/minimax-m2.5-free")
        assert tier == 0
        assert idx == _PREFERRED.index("minimax-m2.5-free")

    def test_preferred_order_preserved(self):
        results = [_tier(f"opencode/{p}") for p in _PREFERRED]
        for i, (tier, idx) in enumerate(results):
            assert tier == 0
            assert idx == i

    def test_preferred_case_insensitive(self):
        tier, _ = _tier("OPENCODE/MINIMAX-M2.5-FREE")
        assert tier == 0

    def test_opencode_tier_one(self):
        tier, idx = _tier("opencode/deepseek-r1")
        assert tier == 1
        assert idx == 0

    def test_github_copilot_tier_two(self):
        # github-copilot/claude-sonnet-4 matches _PREFERRED "claude-sonnet-4" → tier 0
        tier, _ = _tier("github-copilot/some-random-model")
        assert tier == 2

    def test_other_tier_three(self):
        tier, idx = _tier("poe/llama-4-maverick")
        assert tier == 3
        assert idx == 0

    def test_preferred_in_non_opencode_provider(self):
        """A preferred substring match overrides provider-based tiers."""
        tier, idx = _tier("github-copilot/claude-sonnet-4")
        assert tier == 0
        assert idx == _PREFERRED.index("claude-sonnet-4")

    def test_preferred_in_poe_provider(self):
        tier, idx = _tier("poe/gpt-5.2-turbo")
        assert tier == 0
        assert idx == _PREFERRED.index("gpt-5.2")


# ── rank_models ──────────────────────────────────────────────


class TestRankModels:
    def test_preferred_come_first(self):
        ranked = rank_models(_SAMPLE_MODELS)
        # All tier-0 models should precede tier-1+
        preferred_ids = {m for m in _SAMPLE_MODELS if _tier(m)[0] == 0}
        first_n = ranked[: len(preferred_ids)]
        assert set(first_n) == preferred_ids

    def test_preferred_internal_order(self):
        ranked = rank_models(_SAMPLE_MODELS)
        tier0 = [m for m in ranked if _tier(m)[0] == 0]
        indices = [_tier(m)[1] for m in tier0]
        assert indices == sorted(indices)

    def test_opencode_before_github_copilot(self):
        ranked = rank_models(_SAMPLE_MODELS)
        tier1 = [m for m in ranked if _tier(m)[0] == 1]
        tier2 = [m for m in ranked if _tier(m)[0] == 2]
        if tier1 and tier2:
            assert ranked.index(tier1[0]) < ranked.index(tier2[0])

    def test_github_copilot_before_others(self):
        ranked = rank_models(_SAMPLE_MODELS)
        tier2 = [m for m in ranked if _tier(m)[0] == 2]
        tier3 = [m for m in ranked if _tier(m)[0] == 3]
        if tier2 and tier3:
            assert ranked.index(tier2[0]) < ranked.index(tier3[0])

    def test_alphabetical_within_tier(self):
        models = ["opencode/zeta", "opencode/alpha", "opencode/beta"]
        ranked = rank_models(models)
        assert ranked == ["opencode/alpha", "opencode/beta", "opencode/zeta"]

    def test_empty_list(self):
        assert rank_models([]) == []

    def test_single_model(self):
        assert rank_models(["opencode/foo"]) == ["opencode/foo"]


# ── select_model_interactive ─────────────────────────────────


class TestSelectModelInteractive:
    def test_exits_when_no_models(self):
        from io import StringIO

        from rich.console import Console

        console = Console(file=StringIO())
        with patch("opencode_usage.models.list_models", return_value=[]):
            with pytest.raises(SystemExit) as exc:
                select_model_interactive(console)
            assert exc.value.code == 1

    def test_numeric_selection(self):
        from io import StringIO

        from rich.console import Console

        console = Console(file=StringIO())
        models = _SAMPLE_MODELS.copy()
        ranked = rank_models(models)
        top = ranked[:5]

        with (
            patch("opencode_usage.models.list_models", return_value=models),
            patch("opencode_usage.models.Prompt.ask", return_value="1"),
        ):
            result = select_model_interactive(console)
        assert result == top[0]

    def test_numeric_selection_third(self):
        from io import StringIO

        from rich.console import Console

        console = Console(file=StringIO())
        models = _SAMPLE_MODELS.copy()
        ranked = rank_models(models)
        top = ranked[:5]

        with (
            patch("opencode_usage.models.list_models", return_value=models),
            patch("opencode_usage.models.Prompt.ask", return_value="3"),
        ):
            result = select_model_interactive(console)
        assert result == top[2]

    def test_search_flow_selection(self):
        from io import StringIO

        from rich.console import Console

        console = Console(file=StringIO())
        models = _SAMPLE_MODELS.copy()

        # First call: user types "s" to search
        # Second call: user types "deepseek" as search query
        # Third call: user picks "1" from search results
        with (
            patch("opencode_usage.models.list_models", return_value=models),
            patch(
                "opencode_usage.models.Prompt.ask",
                side_effect=["s", "deepseek", "1"],
            ),
        ):
            result = select_model_interactive(console)
        assert result == "opencode/deepseek-r1"

    def test_invalid_then_valid_selection(self):
        from io import StringIO

        from rich.console import Console

        console = Console(file=StringIO())
        models = _SAMPLE_MODELS.copy()
        ranked = rank_models(models)
        top = ranked[:5]

        with (
            patch("opencode_usage.models.list_models", return_value=models),
            patch("opencode_usage.models.Prompt.ask", side_effect=["99", "1"]),
        ):
            result = select_model_interactive(console)
        assert result == top[0]

    def test_search_no_match_returns_to_menu(self):
        from io import StringIO

        from rich.console import Console

        console = Console(file=StringIO())
        models = _SAMPLE_MODELS.copy()
        ranked = rank_models(models)
        top = ranked[:5]

        # "s" → search, "zzzzz" → no match → back to menu, "1" → pick first
        with (
            patch("opencode_usage.models.list_models", return_value=models),
            patch(
                "opencode_usage.models.Prompt.ask",
                side_effect=["s", "zzzzz", "1"],
            ),
        ):
            result = select_model_interactive(console)
        assert result == top[0]

    def test_search_empty_query_returns_to_menu(self):
        from io import StringIO

        from rich.console import Console

        console = Console(file=StringIO())
        models = _SAMPLE_MODELS.copy()
        ranked = rank_models(models)
        top = ranked[:5]

        # "s" → search, "" → empty → back to menu, "2" → pick second
        with (
            patch("opencode_usage.models.list_models", return_value=models),
            patch(
                "opencode_usage.models.Prompt.ask",
                side_effect=["s", "", "2"],
            ),
        ):
            result = select_model_interactive(console)
        assert result == top[1]
