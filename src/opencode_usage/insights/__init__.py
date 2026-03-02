"""OpenCode insights extraction, analysis, and reporting."""

from __future__ import annotations

from .cache import FacetCache
from .types import (
    AggregatedStats,
    InsightsConfig,
    SessionFacet,
    SessionMeta,
)

__all__ = [
    "AggregatedStats",
    "FacetCache",
    "InsightsConfig",
    "SessionFacet",
    "SessionMeta",
]
