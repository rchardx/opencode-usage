"""Prompt builders for the OpenCode insights analysis pipeline."""

from __future__ import annotations

import json
from typing import Any

_JSON_SUFFIX = "RESPOND WITH ONLY A VALID JSON OBJECT. No markdown, no explanation, no code fences."

_GOAL_CATEGORIES = (
    "debug_investigate",
    "implement_feature",
    "fix_bug",
    "write_script_tool",
    "refactor_code",
    "configure_system",
    "create_pr_commit",
    "analyze_data",
    "understand_codebase",
    "write_tests",
    "write_docs",
    "deploy_infra",
    "warmup_minimal",
)


def build_facet_prompt(transcript: str, meta_summary: str) -> str:
    """Build prompt to extract structured facet data from a session transcript."""
    categories_str = ", ".join(_GOAL_CATEGORIES)
    return f"""\
You are analyzing an OpenCode session transcript. OpenCode is an AI-powered CLI \
tool where users interact with agents (build, explore, librarian, oracle) that use \
tools, skills, and project-specific AGENTS.md rules to complete tasks.

Given the transcript and session metadata below, extract structured information \
about this session.

## Session Metadata
{meta_summary}

## Session Transcript
{transcript}

## Instructions

Analyze the transcript and return a JSON object with these fields:

- "underlying_goal": string — what the user was trying to accomplish
- "goal_categories": object mapping each category to 0 or 1 indicating relevance. \
Categories: {categories_str}
- "outcome": one of "fully_achieved", "mostly_achieved", "partially_achieved", \
"not_achieved", "unclear"
- "satisfaction": object with keys "frustrated", "dissatisfied", "likely_satisfied", \
"satisfied", "happy" each mapped to 0 or 1 (exactly one should be 1)
- "helpfulness": one of "unhelpful", "slightly_helpful", "moderately_helpful", \
"very_helpful", "essential"
- "session_type": one of "single_task", "multi_task", "iterative_refinement", \
"exploration", "quick_question"
- "friction_counts": object with keys "tool_failed", "misunderstood_intent", \
"repeated_corrections", "context_lost", "wrong_approach" each mapped to a count (integer)
- "friction_detail": string — brief description of the main friction point, if any
- "primary_success": one of "none", "fast_accurate_search", "correct_code_edits", \
"good_explanations", "proactive_help", "multi_file_changes", "good_debugging"
- "brief_summary": string — 1-2 sentence summary of what happened in this session

{_JSON_SUFFIX}"""


def build_project_areas_prompt(data: dict[str, Any]) -> str:
    """Build prompt to identify project areas from session summaries."""
    data_str = json.dumps(data, indent=2, ensure_ascii=False)
    return f"""\
You are analyzing OpenCode session data to identify the main areas of a project \
that the user works on. Sessions involve interactions with agents (build, explore, \
librarian, oracle) using tools, skills, and AGENTS.md project rules.

## Session Data
{data_str}

## Instructions

Identify 4-5 distinct project areas based on the session summaries. For each area, \
provide a name, how many sessions relate to it, a description, and typical tasks \
performed in that area.

Return a JSON object:
{{
  "areas": [
    {{"name": "string", "session_count": 5, "description": "string", "typical_tasks": ["string"]}}
  ]
}}

{_JSON_SUFFIX}"""


def build_interaction_style_prompt(data: dict[str, Any]) -> str:
    """Build prompt to describe the user's interaction style."""
    data_str = json.dumps(data, indent=2, ensure_ascii=False)
    return f"""\
You are analyzing OpenCode usage patterns to describe how a user interacts with \
their AI-powered development environment. Consider how they use agents, tools, \
sessions, and skills.

## Usage Pattern Data
{data_str}

## Instructions

Describe the user's interaction style based on their usage patterns. Focus on \
observable behaviors: how they structure sessions, which agents they prefer, \
how they handle friction, and what kinds of tasks they delegate.

Return a JSON object:
{{
  "narrative": "string — 2-3 sentence description of your interaction style",
  "key_patterns": ["string — specific observable pattern"],
  "strengths": ["string"],
  "growth_areas": ["string"]
}}

{_JSON_SUFFIX}"""


def build_agent_performance_prompt(data: dict[str, Any]) -> str:
    """Build prompt to analyze agent usage, costs, and efficiency."""
    data_str = json.dumps(data, indent=2, ensure_ascii=False)
    return f"""\
You are analyzing OpenCode agent performance data. Agents include build (primary \
coder), explore (research/search), librarian (documentation), and oracle \
(architecture/planning). Each agent can use different models, tools, and skills.

## Agent Performance Data
{data_str}

## Instructions

Analyze the agent usage patterns, costs, and efficiency. Identify which agents \
perform best, where costs concentrate, which model pairings work well for which \
task types, and where there are opportunities to improve efficiency.

Return a JSON object:
{{
  "top_performers": [{{"agent": "string", "strength": "string", "usage_pattern": "string"}}],
  "cost_insights": ["string — specific cost observation"],
  "model_pairing_tips": ["string — which model works best for which task type"],
  "efficiency_opportunities": ["string"]
}}

{_JSON_SUFFIX}"""


def build_friction_prompt(data: dict[str, Any]) -> str:
    """Build prompt to analyze friction patterns across sessions."""
    data_str = json.dumps(data, indent=2, ensure_ascii=False)
    return f"""\
You are analyzing friction patterns from OpenCode sessions. Friction includes \
tool failures, misunderstood intent, repeated corrections, lost context, and \
wrong approaches taken by agents.

## Friction Data
{data_str}

## Instructions

Analyze the friction patterns across sessions. Identify the most common friction \
categories, their root causes, and quick actionable fixes the user can apply.

Return a JSON object:
{{
  "top_friction_categories": [
    {{"category": "string", "frequency": "high|medium|low", "description": "string", \
"examples": ["string"]}}
  ],
  "root_causes": ["string"],
  "quick_fixes": ["string — actionable fix"]
}}

{_JSON_SUFFIX}"""


def build_suggestions_prompt(data: dict[str, Any]) -> str:
    """Build prompt to generate actionable workflow improvement suggestions."""
    data_str = json.dumps(data, indent=2, ensure_ascii=False)
    return f"""\
You are generating actionable suggestions to improve an OpenCode user's workflow. \
OpenCode has powerful features that many users underutilize:

- **Skills**: Installable domain expertise that agents can load (e.g., playwright, \
git-master, frontend-ui-ux). Users can create custom skills.
- **AGENTS.md**: Project-specific rules and conventions that agents follow. Adding \
rules here shapes agent behavior for your codebase.
- **Hooks**: Automation triggers that run on events (e.g., pre-commit checks, \
auto-formatting). Configure in opencode.json.
- **Headless mode**: Run analysis via `opencode run` for scripted/automated workflows.

## User Data
{data_str}

## Instructions

Based on the user's patterns, suggest concrete improvements in three categories: \
AGENTS.md additions (specific rules to add), skill candidates (custom skills to create), \
and workflow patterns (better ways to use OpenCode).

Return a JSON object:
{{
  "agents_md_additions": [
    {{"rule": "string — specific rule to add to AGENTS.md", "rationale": "string"}}
  ],
  "skill_candidates": [
    {{"name": "string", "description": "string", "trigger_phrases": ["string"]}}
  ],
  "workflow_patterns": [
    {{"pattern": "string", "benefit": "string", "how_to": "string"}}
  ]
}}

{_JSON_SUFFIX}"""


def build_tool_health_prompt(data: dict[str, Any]) -> str:
    """Build prompt to analyze tool usage patterns and error rates."""
    data_str = json.dumps(data, indent=2, ensure_ascii=False)
    return f"""\
You are analyzing tool usage health across OpenCode sessions. Tools include file \
operations (read, write, edit, glob, grep), shell commands (bash), LSP operations \
(diagnostics, definitions, references), and specialized tools (ast_grep, web fetch).

## Tool Usage Data
{data_str}

## Instructions

Analyze tool usage patterns and error rates. Identify problematic tools with high \
error rates, provide efficiency tips for better tool usage, and suggest recovery \
patterns for common tool failures.

Return a JSON object:
{{
  "problematic_tools": [{{"tool": "string", "error_rate": "string", "likely_cause": \
"string", "fix": "string"}}],
  "efficiency_tips": ["string — how to use tools more effectively"],
  "recovery_patterns": ["string — what to do when tools fail"]
}}

{_JSON_SUFFIX}"""


def build_horizon_prompt(data: dict[str, Any]) -> str:
    """Build prompt to identify future workflow opportunities."""
    data_str = json.dumps(data, indent=2, ensure_ascii=False)
    return f"""\
You are identifying future opportunities for an OpenCode user's workflow. Consider \
automation via hooks and headless mode (`opencode run`), skill gaps that could be \
filled with custom skills, and how their workflow could evolve as they adopt more \
OpenCode features like AGENTS.md rules and session management.

## Current Workflow Data
{data_str}

## Instructions

Identify automation opportunities (with effort estimates), skill gaps that would \
help but aren't currently available, and ways the user's workflow could evolve.

Return a JSON object:
{{
  "automation_opportunities": [{{"opportunity": "string", "how": "string", \
"effort": "low|medium|high"}}],
  "skill_gaps": ["string — capability that would help but isn't available"],
  "workflow_evolutions": ["string — how your workflow could evolve"]
}}

{_JSON_SUFFIX}"""


def build_at_a_glance_prompt(all_insights: dict[str, Any], stats_summary: dict[str, Any]) -> str:
    """Build prompt to synthesize all insights into an executive summary."""
    insights_str = json.dumps(all_insights, indent=2, ensure_ascii=False)
    stats_str = json.dumps(stats_summary, indent=2, ensure_ascii=False)
    return f"""\
You are creating an executive summary of an OpenCode user's workflow analysis. \
You have access to all previously generated insights and overall usage statistics.

## All Insights
{insights_str}

## Usage Statistics
{stats_str}

## Instructions

Synthesize everything into a concise at-a-glance summary. Focus on the most \
impactful observations: what's working well (top 3), what's hindering productivity \
(top 3), quick wins with effort estimates, and ambitious workflow improvements \
to consider.

Return a JSON object:
{{
  "whats_working": ["string — top 3 things working well"],
  "whats_hindering": ["string — top 3 friction points"],
  "quick_wins": [{{"action": "string", "impact": "string", "effort": "low|medium|high"}}],
  "ambitious_workflows": ["string — bigger workflow improvements to consider"]
}}

{_JSON_SUFFIX}"""
