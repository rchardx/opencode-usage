"""Data types for OpenCode insights extraction and analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionFacet:
    """Extracted facet information from a single session."""

    session_id: str
    underlying_goal: str
    goal_categories: dict[str, int] = field(default_factory=dict)
    outcome: str = ""
    satisfaction: dict[str, int] = field(default_factory=dict)
    helpfulness: str = ""
    session_type: str = ""
    friction_counts: dict[str, int] = field(default_factory=dict)
    friction_detail: str = ""
    primary_success: str = ""
    brief_summary: str = ""


@dataclass
class SessionMeta:
    """Metadata about a session for insights analysis."""

    id: str
    title: str
    project_path: str | None = None
    parent_id: str | None = None
    duration_minutes: float = 0.0
    user_msg_count: int = 0
    assistant_msg_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    tool_counts: dict[str, int] = field(default_factory=dict)
    languages: dict[str, int] = field(default_factory=dict)
    agent_counts: dict[str, int] = field(default_factory=dict)
    model_counts: dict[str, int] = field(default_factory=dict)
    start_time: int = 0
    end_time: int = 0


@dataclass
class AggregatedStats:
    """Aggregated statistics across multiple sessions."""

    total_sessions: int
    analyzed_sessions: int
    date_range: tuple[int, int]
    total_messages: int
    total_cost: float
    top_tools: list[tuple[str, int]] = field(default_factory=list)
    top_agents: list[tuple[str, int]] = field(default_factory=list)
    top_models: list[tuple[str, int]] = field(default_factory=list)
    outcome_dist: dict[str, int] = field(default_factory=dict)
    satisfaction_dist: dict[str, int] = field(default_factory=dict)
    friction_dist: dict[str, int] = field(default_factory=dict)


@dataclass
class InsightsConfig:
    """Configuration for the insights pipeline."""

    model: str = "opencode/minimax-m2.5-free"
    days: int | None = None
    since: datetime | None = None
    force: bool = False
    output_path: str = "./opencode-insights.html"
