"""Data structures for the insights pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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
