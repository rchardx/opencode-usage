"""Data structures for the insights pipeline."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .db import OpenCodeDB

@dataclass
class Credentials:
    """API credentials for insights service."""

    api_key: str
    base_url: str
    model: str


@dataclass
class Facet:
    """Qualitative analysis of a session."""

    underlying_goal: str
    goal_categories: dict[str, int]
    outcome: str
    satisfaction_counts: dict[str, int]
    friction_counts: dict[str, int]
    friction_detail: str
    session_type: str
    primary_success: str
    brief_summary: str
    helpfulness: str


@dataclass
class SessionMeta:
    """Metadata about a user session."""

    session_id: str
    title: str
    parent_id: str | None
    start_time: datetime
    duration_minutes: float
    message_count: int
    user_message_count: int
    total_tokens: int
    total_cost: float
    agents: list[str]
    models: list[str]
    tool_counts: dict[str, int]
    tool_errors: int


@dataclass
class CachedFacet:
    """Cached facet analysis with session timestamp."""

    session_id: str
    session_updated: int
    facet: Facet


@dataclass
class QuantInsights:
    """Quantitative metrics and insights."""

    cache_efficiency: dict[str, float] = field(default_factory=dict)
    cost_per_1k: dict[str, float] = field(default_factory=dict)
    tool_error_rates: dict[str, float] = field(default_factory=dict)
    avg_tokens_per_session: float = 0.0
    agent_delegation: dict[str, list[str]] = field(default_factory=dict)
    top_sessions: list[SessionMeta] = field(default_factory=list)


@dataclass
class Suggestion:
    """Recommendation from insights analysis."""

    category: str
    finding: str
    recommendation: str


@dataclass
class InsightsResult:
    """Complete insights result for a time period."""

    period: str
    quantitative: QuantInsights
    facets: list[CachedFacet] | None = None
    suggestions: list[Suggestion] | None = None
    interaction_style: str | None = None
    what_works: list[dict[str, Any]] | None = None
    friction: list[dict[str, Any]] | None = None


_FACET_DEFAULTS: dict[str, object] = {
    "underlying_goal": "",
    "goal_categories": {},
    "outcome": "unclear_from_transcript",
    "satisfaction_counts": {},
    "friction_counts": {},
    "friction_detail": "",
    "session_type": "single_task",
    "primary_success": "none",
    "brief_summary": "",
    "helpfulness": "unsure",
}


def _cache_dir() -> Path:
    """Return the opencode-usage cache directory, creating it if needed."""
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    cache = base / "opencode-usage" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def load_cache() -> dict[str, CachedFacet]:
    """Load all cached facets from disk. Returns empty dict on missing or corrupt file."""
    path = _cache_dir() / "facets.json"
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            raw: dict[str, object] = json.load(f)
        result: dict[str, CachedFacet] = {}
        for session_id, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            facet_data = entry.get("facet", {})
            if not isinstance(facet_data, dict):
                continue
            facet = Facet(**{k: facet_data.get(k, _FACET_DEFAULTS[k]) for k in _FACET_DEFAULTS})
            result[session_id] = CachedFacet(
                session_id=session_id,
                session_updated=int(entry.get("session_updated", 0)),
                facet=facet,
            )
        return result
    except (json.JSONDecodeError, TypeError, KeyError):
        return {}


def save_facet(session_id: str, session_updated: int, facet: Facet) -> None:
    """Save a single facet to the cache file atomically."""
    cache_dir = _cache_dir()
    path = cache_dir / "facets.json"
    existing = load_cache()
    existing[session_id] = CachedFacet(
        session_id=session_id,
        session_updated=session_updated,
        facet=facet,
    )
    serialized: dict[str, object] = {
        sid: {
            "session_updated": cf.session_updated,
            "facet": {
                "underlying_goal": cf.facet.underlying_goal,
                "goal_categories": cf.facet.goal_categories,
                "outcome": cf.facet.outcome,
                "satisfaction_counts": cf.facet.satisfaction_counts,
                "friction_counts": cf.facet.friction_counts,
                "friction_detail": cf.facet.friction_detail,
                "session_type": cf.facet.session_type,
                "primary_success": cf.facet.primary_success,
                "brief_summary": cf.facet.brief_summary,
                "helpfulness": cf.facet.helpfulness,
            },
        }
        for sid, cf in existing.items()
    }
    tmp_path = cache_dir / "facets.json.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(serialized, f, ensure_ascii=False, indent=2)
    tmp_path.rename(path)


def get_cached_facet(session_id: str, session_updated: int) -> Facet | None:
    """Return cached facet if it exists and session_updated matches, else None."""
    cache = load_cache()
    cached = cache.get(session_id)
    if cached is None:
        return None
    if cached.session_updated != session_updated:
        return None
    return cached.facet


def compute_quantitative(
    db: OpenCodeDB,
    since: datetime | None,
    until: datetime | None,
) -> QuantInsights:
    """Compute derived quantitative metrics from usage data."""
    cache_efficiency = db.cache_efficiency(since, until)
    cost_per_1k = db.cost_per_1k_tokens(since, until)
    tool_error_rates = db.tool_error_rates(since, until)
    agent_delegation = db.agent_delegation(since, until)
    sessions = db.session_meta(since, until, limit=100)

    avg_tokens = 0.0
    if sessions:
        avg_tokens = sum(s.total_tokens for s in sessions) / len(sessions)

    # Top 5 sessions by tokens
    top_sessions = sorted(sessions, key=lambda s: s.total_tokens, reverse=True)[:5]

    return QuantInsights(
        cache_efficiency=cache_efficiency,
        cost_per_1k=cost_per_1k,
        tool_error_rates=tool_error_rates,
        avg_tokens_per_session=avg_tokens,
        agent_delegation=agent_delegation,
        top_sessions=top_sessions,
    )


_FACET_SYSTEM_PROMPT = (
    "You are a session analysis expert. Analyze the AI agent session transcript "
    "and return a JSON object with exactly these keys:\n"
    "- underlying_goal: str, brief summary of user's goal\n"
    "- goal_categories: dict of 0/1 for: debug_investigate, implement_feature, "
    "fix_bug, write_script_tool, refactor_code, configure_system, "
    "understand_codebase, write_tests, write_docs, warmup_minimal\n"
    "- outcome: one of: fully_achieved, mostly_achieved, partially_achieved, "
    "not_achieved, unclear_from_transcript\n"
    "- satisfaction_counts: dict of counts for: frustrated, dissatisfied, "
    "likely_satisfied, satisfied, happy, unsure\n"
    "- friction_counts: dict of occurrence counts for: misunderstood_request, "
    "wrong_approach, buggy_code, excessive_changes, tool_failed, slow_or_verbose\n"
    "- friction_detail: str, main friction point or empty string\n"
    "- session_type: one of: single_task, multi_task, exploration, debugging, iteration\n"
    "- primary_success: str, what worked well or 'none'\n"
    "- brief_summary: str, 1-2 sentence summary\n"
    "- helpfulness: one of: very_helpful, helpful, somewhat_helpful, not_helpful, unsure\n"
    "Return ONLY valid JSON, no markdown fences, matching exactly this schema."
)


def extract_facet(credentials: Credentials, transcript: str) -> Facet:
    """Analyze a session transcript and extract structured facets via LLM."""
    from .llm import chat_complete_json

    messages = [
        {"role": "system", "content": _FACET_SYSTEM_PROMPT},
        {"role": "user", "content": transcript},
    ]
    try:
        data = chat_complete_json(credentials, messages, temperature=0.3, max_tokens=1024)
        return Facet(
            underlying_goal=str(data.get("underlying_goal", "")),
            goal_categories={k: int(v) for k, v in data.get("goal_categories", {}).items()},
            outcome=str(data.get("outcome", "unclear_from_transcript")),
            satisfaction_counts={
                k: int(v) for k, v in data.get("satisfaction_counts", {}).items()
            },
            friction_counts={k: int(v) for k, v in data.get("friction_counts", {}).items()},
            friction_detail=str(data.get("friction_detail", "")),
            session_type=str(data.get("session_type", "single_task")),
            primary_success=str(data.get("primary_success", "none")),
            brief_summary=str(data.get("brief_summary", "")),
            helpfulness=str(data.get("helpfulness", "unsure")),
        )
    except (RuntimeError, KeyError, TypeError, ValueError):
        return Facet(
            underlying_goal="",
            goal_categories={},
            outcome="unclear_from_transcript",
            satisfaction_counts={},
            friction_counts={},
            friction_detail="",
            session_type="single_task",
            primary_success="none",
            brief_summary="",
            helpfulness="unsure",
        )


def extract_facets_batch(
    credentials: Credentials,
    db: OpenCodeDB,
    sessions: list[SessionMeta],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[CachedFacet]:
    """Extract facets for multiple sessions, using cache when available."""
    sessions = sessions[:50]
    total = len(sessions)
    results: list[CachedFacet] = []

    for i, session in enumerate(sessions):
        session_updated = int(session.start_time.timestamp() * 1000)

        # Check cache first
        cached_facet = get_cached_facet(session.session_id, session_updated)
        if cached_facet is not None:
            results.append(
                CachedFacet(
                    session_id=session.session_id,
                    session_updated=session_updated,
                    facet=cached_facet,
                )
            )
        else:
            # Build transcript and extract facet via LLM
            transcript = db.build_transcript(session.session_id, max_chars=30000)
            if transcript:
                facet = extract_facet(credentials, transcript)
            else:
                facet = Facet(
                    underlying_goal="",
                    goal_categories={},
                    outcome="unclear_from_transcript",
                    satisfaction_counts={},
                    friction_counts={},
                    friction_detail="",
                    session_type="single_task",
                    primary_success="none",
                    brief_summary="",
                    helpfulness="unsure",
                )
            # Save to cache immediately (interrupt-safe)
            save_facet(session.session_id, session_updated, facet)
            results.append(
                CachedFacet(
                    session_id=session.session_id,
                    session_updated=session_updated,
                    facet=facet,
                )
            )

        if on_progress is not None:
            on_progress(i + 1, total)

    return results


_SUGGESTIONS_SYSTEM_PROMPT = (
    "You are an expert at analyzing AI agent usage patterns to improve productivity. "
    "Given aggregated statistics from multiple sessions, identify patterns and suggest "
    "specific improvements.\n"
    "Return a JSON object with these keys:\n"
    "- suggestions: list of {category, finding, recommendation} where category is one of: "
    "agents_md (rules/instructions for AGENTS.md), skill (new automatable skills), "
    "command (new shortcut commands), agent_config (model/prompt improvements).\n"
    "- interaction_style: str describing user's work style (e.g. 'systematic builder')\n"
    "- what_works: list of {title, description} for things going well\n"
    "- friction: list of {category, description, examples} for pain points\n"
    "Example suggestion: {\"category\": \"agents_md\", \"finding\": \"User repeatedly asks "
    "for compact output\", \"recommendation\": \"Add rule: prefer concise responses\"}\n"
    "Return ONLY valid JSON, no markdown fences."
)


def generate_suggestions(
    credentials: Credentials,
    quant: QuantInsights,
    facets: list[CachedFacet],
    session_summaries: list[str],
) -> tuple[list[Suggestion], str, list[dict[str, object]], list[dict[str, object]]]:
    """Generate aggregated AGENTS.md/skills/commands suggestions via LLM."""
    from .llm import chat_complete_json

    # Build aggregated stats from quant + facets
    outcome_dist: dict[str, int] = {}
    satisfaction_dist: dict[str, int] = {}
    friction_dist: dict[str, int] = {}
    friction_details: list[str] = []

    for cf in facets:
        f = cf.facet
        outcome_dist[f.outcome] = outcome_dist.get(f.outcome, 0) + 1
        for level, count in f.satisfaction_counts.items():
            satisfaction_dist[level] = satisfaction_dist.get(level, 0) + count
        for ftype, count in f.friction_counts.items():
            friction_dist[ftype] = friction_dist.get(ftype, 0) + count
        if f.friction_detail:
            friction_details.append(f.friction_detail)

    # Aggregate data for the prompt (limit to avoid token overflow)
    agg_data = {
        "total_sessions": len(facets),
        "outcome_distribution": outcome_dist,
        "satisfaction_distribution": satisfaction_dist,
        "top_friction": friction_dist,
        "friction_details": friction_details[:20],
        "session_summaries": session_summaries[:30],
        "cache_efficiency_by_model": {k: round(v, 3) for k, v in quant.cache_efficiency.items()},
        "tool_error_rates": {k: round(v, 4) for k, v in quant.tool_error_rates.items()},
        "avg_tokens_per_session": round(quant.avg_tokens_per_session),
    }

    messages = [
        {"role": "system", "content": _SUGGESTIONS_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(agg_data, ensure_ascii=False, indent=2)},
    ]

    data = chat_complete_json(credentials, messages, temperature=0.5, max_tokens=8192)

    suggestions = [
        Suggestion(
            category=str(s.get("category", "agents_md")),
            finding=str(s.get("finding", "")),
            recommendation=str(s.get("recommendation", "")),
        )
        for s in data.get("suggestions", [])
        if isinstance(s, dict)
    ]
    interaction_style = str(data.get("interaction_style", ""))
    what_works = [d for d in data.get("what_works", []) if isinstance(d, dict)]
    friction = [d for d in data.get("friction", []) if isinstance(d, dict)]

    return suggestions, interaction_style, what_works, friction


def run_insights(
    db: OpenCodeDB,
    since: datetime | None,
    until: datetime | None,
    *,
    credentials: Credentials | None = None,
    no_llm: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
) -> InsightsResult:
    """Run the complete insights pipeline."""
    sessions = db.session_meta(since, until)
    quant = compute_quantitative(db, since, until)
    period = "custom"

    if no_llm or credentials is None:
        return InsightsResult(period=period, quantitative=quant)

    # LLM mode: extract facets for all sessions
    facets = extract_facets_batch(credentials, db, sessions, on_progress=on_progress)

    # Generate aggregated suggestions
    session_summaries = [cf.facet.brief_summary for cf in facets if cf.facet.brief_summary]
    suggestions, interaction_style, what_works, friction = generate_suggestions(
        credentials, quant, facets, session_summaries
    )

    return InsightsResult(
        period=period,
        quantitative=quant,
        facets=facets,
        suggestions=suggestions,
        interaction_style=interaction_style,
        what_works=what_works,
        friction=friction,
    )
