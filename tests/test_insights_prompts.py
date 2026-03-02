"""Tests for prompt builders — structure, content, and conventions."""

from __future__ import annotations

import re
from typing import Any

from opencode_usage.insights.prompts import (
    build_agent_performance_prompt,
    build_at_a_glance_prompt,
    build_facet_prompt,
    build_friction_prompt,
    build_horizon_prompt,
    build_interaction_style_prompt,
    build_project_areas_prompt,
    build_suggestions_prompt,
    build_tool_health_prompt,
)

# ── Sample data ──────────────────────────────────────────────────────

_TRANSCRIPT = "User: Fix the login bug\nAssistant: I'll investigate the auth module."
_META_SUMMARY = "Session ses_abc123 | 15 messages | 12 min | build agent | cost $0.02"
_DATA: dict[str, Any] = {"sessions": [{"id": "ses_1", "summary": "Refactored auth module"}]}
_ALL_INSIGHTS: dict[str, Any] = {"friction": {"top": "tool_failed"}, "style": {"narrative": "Fast"}}
_STATS_SUMMARY: dict[str, Any] = {"total_sessions": 42, "total_cost": 1.23}


def _all_prompts() -> list[str]:
    """Return output from all 9 prompt builders."""
    return [
        build_facet_prompt(_TRANSCRIPT, _META_SUMMARY),
        build_project_areas_prompt(_DATA),
        build_interaction_style_prompt(_DATA),
        build_agent_performance_prompt(_DATA),
        build_friction_prompt(_DATA),
        build_suggestions_prompt(_DATA),
        build_tool_health_prompt(_DATA),
        build_horizon_prompt(_DATA),
        build_at_a_glance_prompt(_ALL_INSIGHTS, _STATS_SUMMARY),
    ]


# ── build_facet_prompt ───────────────────────────────────────────────


class TestBuildFacetPrompt:
    """Tests for build_facet_prompt."""

    def test_build_facet_prompt_contains_transcript(self) -> None:
        result = build_facet_prompt(_TRANSCRIPT, _META_SUMMARY)
        assert _TRANSCRIPT in result

    def test_build_facet_prompt_contains_meta_summary(self) -> None:
        result = build_facet_prompt(_TRANSCRIPT, _META_SUMMARY)
        assert _META_SUMMARY in result

    def test_build_facet_prompt_contains_json_schema_keys(self) -> None:
        result = build_facet_prompt(_TRANSCRIPT, _META_SUMMARY)
        assert "underlying_goal" in result
        assert "outcome" in result
        assert "satisfaction" in result

    def test_build_facet_prompt_requests_json_only(self) -> None:
        result = build_facet_prompt(_TRANSCRIPT, _META_SUMMARY)
        assert "RESPOND WITH ONLY A VALID JSON OBJECT" in result

    def test_build_facet_prompt_contains_goal_categories(self) -> None:
        result = build_facet_prompt(_TRANSCRIPT, _META_SUMMARY)
        assert "debug_investigate" in result
        assert "implement_feature" in result
        assert "fix_bug" in result
        assert "write_script_tool" in result
        assert "refactor_code" in result
        assert "configure_system" in result
        assert "warmup_minimal" in result


# ── Cross-prompt conventions ─────────────────────────────────────────


class TestPromptConventions:
    """Tests for conventions shared across all prompt builders."""

    def test_no_claude_in_any_prompt(self) -> None:
        for prompt in _all_prompts():
            assert not re.search(r"claude", prompt, re.IGNORECASE), (
                f"Found 'claude' in prompt: {prompt[:80]}..."
            )

    def test_all_prompts_nonempty(self) -> None:
        for prompt in _all_prompts():
            assert len(prompt) > 0

    def test_all_prompts_end_with_json_suffix(self) -> None:
        for prompt in _all_prompts():
            assert prompt.rstrip().endswith(
                "RESPOND WITH ONLY A VALID JSON OBJECT. No markdown, no explanation, "
                "no code fences."
            )


# ── build_suggestions_prompt ─────────────────────────────────────────


class TestBuildSuggestionsPrompt:
    """Tests for build_suggestions_prompt."""

    def test_build_suggestions_prompt_references_opencode(self) -> None:
        result = build_suggestions_prompt(_DATA)
        assert "AGENTS.md" in result or "skill" in result.lower()

    def test_build_suggestions_prompt_mentions_agents_md(self) -> None:
        result = build_suggestions_prompt(_DATA)
        assert "AGENTS.md" in result

    def test_build_suggestions_prompt_mentions_skills(self) -> None:
        result = build_suggestions_prompt(_DATA)
        assert "Skills" in result or "skills" in result

    def test_build_suggestions_prompt_mentions_hooks(self) -> None:
        result = build_suggestions_prompt(_DATA)
        assert "Hooks" in result or "hooks" in result

    def test_build_suggestions_prompt_mentions_headless(self) -> None:
        result = build_suggestions_prompt(_DATA)
        assert "opencode run" in result


# ── build_at_a_glance_prompt ─────────────────────────────────────────


class TestBuildAtAGlancePrompt:
    """Tests for build_at_a_glance_prompt."""

    def test_build_at_a_glance_contains_whats_working_key(self) -> None:
        result = build_at_a_glance_prompt(_ALL_INSIGHTS, _STATS_SUMMARY)
        assert "whats_working" in result

    def test_build_at_a_glance_contains_insights_data(self) -> None:
        result = build_at_a_glance_prompt(_ALL_INSIGHTS, _STATS_SUMMARY)
        assert "tool_failed" in result

    def test_build_at_a_glance_contains_stats_data(self) -> None:
        result = build_at_a_glance_prompt(_ALL_INSIGHTS, _STATS_SUMMARY)
        assert "42" in result
