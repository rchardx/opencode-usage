"""OpenCode insights extraction, analysis, and reporting."""

from __future__ import annotations

# Legacy exports for backward compatibility (from old flat insights.py)
from opencode_usage._insights_legacy import (
    CachedFacet,
    Credentials,
    Facet,
    InsightsResult,
    QuantInsights,
    Suggestion,
    compute_quantitative,
    extract_facet,
    extract_facets_batch,
    generate_suggestions,
    get_cached_facet,
    insights_to_dict,
    load_cache,
    run_insights,
    save_facet,
)

# New subpackage exports
from .cache import FacetCache
from .types import AggregatedStats, InsightsConfig, SessionFacet, SessionMeta

__all__ = [
    "AggregatedStats",
    "CachedFacet",
    "Credentials",
    "Facet",
    "FacetCache",
    "InsightsConfig",
    "InsightsResult",
    "QuantInsights",
    "SessionFacet",
    "SessionMeta",
    "Suggestion",
    "compute_quantitative",
    "extract_facet",
    "extract_facets_batch",
    "generate_suggestions",
    "get_cached_facet",
    "insights_to_dict",
    "load_cache",
    "run_insights",
    "save_facet",
]
