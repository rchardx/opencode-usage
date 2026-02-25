"""Tests for opencode_usage.render helpers."""

from __future__ import annotations

import opencode_usage.render as render_mod
from opencode_usage.render import (
    _fmt_cost,
    _fmt_delta,
    _fmt_tokens,
    _short_model,
    _spark_bar,
    configure_console,
)

# ── _fmt_tokens ──────────────────────────────────────────────


class TestFmtTokens:
    def test_zero(self):
        assert _fmt_tokens(0) == "0"

    def test_below_thousand(self):
        assert _fmt_tokens(999) == "999"

    def test_exactly_thousand(self):
        assert _fmt_tokens(1000) == "1.0K"

    def test_fifteen_hundred(self):
        assert _fmt_tokens(1500) == "1.5K"

    def test_million(self):
        assert _fmt_tokens(1_000_000) == "1.0M"

    def test_one_point_five_million(self):
        assert _fmt_tokens(1_500_000) == "1.5M"

    def test_billion(self):
        assert _fmt_tokens(1_500_000_000) == "1.5B"

    def test_exactly_billion(self):
        assert _fmt_tokens(1_000_000_000) == "1.0B"


# ── _fmt_cost ────────────────────────────────────────────────


class TestFmtCost:
    def test_zero_returns_dash(self):
        assert _fmt_cost(0) == "-"

    def test_small_value_four_decimals(self):
        assert _fmt_cost(0.001) == "$0.0010"

    def test_below_penny_four_decimals(self):
        assert _fmt_cost(0.009) == "$0.0090"

    def test_exactly_penny_two_decimals(self):
        assert _fmt_cost(0.01) == "$0.01"

    def test_normal_value_two_decimals(self):
        assert _fmt_cost(1.50) == "$1.50"

    def test_large_cost(self):
        assert _fmt_cost(123.456) == "$123.46"


# ── _short_model ─────────────────────────────────────────────


class TestShortModel:
    def test_vendor_prefix_stripping(self):
        # "anthropic-claude-3-5-20241022" → "claude-3-5"
        assert _short_model("anthropic-claude-3-5-20241022") == "claude-3-5"

    def test_vendor_prefix_no_date(self):
        # "vendor-variant-1-2" → "variant-1-2"
        assert _short_model("vendor-variant-1-2") == "variant-1-2"

    def test_preview_removal(self):
        assert _short_model("gemini-3-pro-preview") == "gemini-3-pro"

    def test_grok_code_removal(self):
        assert _short_model("grok-code-fast-1") == "grok-fast-1"

    def test_free_removal(self):
        assert _short_model("minimax-m2.5-free") == "minimax-m2.5"

    def test_passthrough_unmatched(self):
        assert _short_model("deepseek-r1") == "deepseek-r1"

    def test_combined_preview_and_free(self):
        # -free is removed first by replace, then -preview by sub
        assert _short_model("some-model-free") == "some-model"


# ── _spark_bar ───────────────────────────────────────────────


class TestSparkBar:
    def test_zero_zero_returns_min(self):
        assert _spark_bar(0, 0) == "▁"

    def test_max_equals_value_returns_full(self):
        assert _spark_bar(100, 100) == "█"

    def test_negative_value_returns_min(self):
        assert _spark_bar(-5, 100) == "▁"

    def test_negative_max_returns_min(self):
        assert _spark_bar(50, -10) == "▁"

    def test_zero_value_positive_max(self):
        assert _spark_bar(0, 100) == "▁"

    def test_mid_value(self):
        # 50/100 * 7 = 3.5 → int(3.5) = 3 → index 3 = "▄"
        assert _spark_bar(50, 100) == "▄"

    def test_small_fraction(self):
        # 1/100 * 7 = 0.07 → int(0.07) = 0 → index 0 = "▁"
        assert _spark_bar(1, 100) == "▁"

    def test_value_exceeds_max_clamped(self):
        # 200/100 * 7 = 14 → min(14, 7) = 7 → "█"
        assert _spark_bar(200, 100) == "█"


# ── _fmt_delta ───────────────────────────────────────────────


class TestFmtDelta:
    def test_positive_shows_red_up(self):
        result = _fmt_delta(50.0)
        assert "red" in result
        assert "↑" in result
        assert "50%" in result

    def test_negative_shows_green_down(self):
        result = _fmt_delta(-30.0)
        assert "green" in result
        assert "↓" in result
        assert "30%" in result

    def test_zero_shows_dim_arrow(self):
        result = _fmt_delta(0.0)
        assert "dim" in result
        assert "→0%" in result

    def test_large_positive(self):
        result = _fmt_delta(999.0)
        assert "↑999%" in result

    def test_small_negative(self):
        result = _fmt_delta(-1.0)
        assert "↓1%" in result


# ── configure_console ────────────────────────────────────────


class TestConfigureConsole:
    def test_replaces_module_console_no_color(self):
        original = render_mod.console
        try:
            configure_console(no_color=True)
            assert render_mod.console is not original
            assert render_mod.console.no_color is True
        finally:
            configure_console(no_color=False)

    def test_replaces_module_console_color(self):
        configure_console(no_color=True)
        mid = render_mod.console
        configure_console(no_color=False)
        assert render_mod.console is not mid
        assert render_mod.console.no_color is False
