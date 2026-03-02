"""LLM runner for insights analysis via opencode run subprocess."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import warnings
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from .cache import FacetCache
from .extract import extract_session_meta, reconstruct_transcript
from .prompts import (
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
from .types import AggregatedStats, InsightsConfig, SessionFacet

if TYPE_CHECKING:
    from collections.abc import Callable


def parse_ndjson(output: str) -> tuple[str, float, dict[str, int]]:
    """Parse NDJSON output from opencode run --format json.

    Returns (text_content, cost, tokens_dict).
    """
    text_parts: list[str] = []
    cost: float = 0.0
    tokens: dict[str, int] = {}

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # Skip non-JSON lines like [config-context] warnings
            continue

        event_type = event.get("type")
        part = event.get("part", {})

        if event_type == "text":
            text = part.get("text", "")
            if text:
                text_parts.append(text)
        elif event_type == "step_finish":
            cost = float(part.get("cost", 0.0))
            raw_tokens = part.get("tokens", {})
            if isinstance(raw_tokens, dict):
                tokens = {k: int(v) for k, v in raw_tokens.items() if isinstance(v, (int, float))}

    return "".join(text_parts), cost, tokens


def extract_json_from_response(text: str) -> dict:
    """Strip markdown code fences and parse JSON from LLM response text."""
    stripped = text.strip()

    # Strip ```json ... ``` or ``` ... ```
    if stripped.startswith("```json\n"):
        stripped = stripped[8:]
    elif stripped.startswith("```json"):
        stripped = stripped[7:]
    elif stripped.startswith("```\n"):
        stripped = stripped[4:]
    elif stripped.startswith("```"):
        stripped = stripped[3:]

    if stripped.endswith("\n```"):
        stripped = stripped[:-4]
    elif stripped.endswith("```"):
        stripped = stripped[:-3]

    stripped = stripped.strip()

    try:
        result = json.loads(stripped)
        if not isinstance(result, dict):
            raise ValueError(f"Expected JSON object, got {type(result).__name__}")
        return result
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned non-JSON: {text[:200]}") from e


def run_llm(
    prompt: str,
    model: str = "opencode/minimax-m2.5-free",
    timeout: int = 120,
) -> dict:
    """Run opencode LLM analysis via subprocess and return parsed JSON result.

    Retries up to 3 times on timeout with exponential backoff.
    Raises FileNotFoundError if opencode binary not found (returncode 127).
    Raises PermissionError if opencode binary not executable (returncode 126).
    Raises TimeoutError after 3 timeout retries.
    Raises RuntimeError on other non-zero return codes.
    """
    max_retries = 3
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["opencode", "run", prompt, "--format", "json", "--model", model, "--dir", "/tmp"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                wait = min(2**attempt * 2, 60)
                time.sleep(wait)
            continue

        if result.returncode == 127:
            raise FileNotFoundError("opencode binary not found")
        if result.returncode == 126:
            raise PermissionError("opencode binary not executable")
        if result.returncode != 0:
            raise RuntimeError(
                f"opencode run failed with code {result.returncode}: {result.stderr[:200]}"
            )

        text, _cost, _tokens = parse_ndjson(result.stdout)
        return extract_json_from_response(text)

    raise TimeoutError("opencode run timed out after 3 attempts") from last_exc


_MAX_NEW_SESSIONS = 50
_MAX_CONCURRENCY = 8


def _default_concurrency(override: int | None = None) -> int:
    """Return worker count: override > 0, else min(cpu_count, _MAX_CONCURRENCY)."""
    if override is not None and override > 0:
        return override
    try:
        cpu = os.cpu_count() or 4
    except Exception:
        cpu = 4
    return min(cpu, _MAX_CONCURRENCY)


def _count_outcomes(facets: dict[str, SessionFacet]) -> dict[str, int]:
    """Count outcome values across facets."""
    counts: dict[str, int] = defaultdict(int)
    for f in facets.values():
        if f.outcome:
            counts[f.outcome] += 1
    return dict(counts)


def _count_satisfaction(facets: dict[str, SessionFacet]) -> dict[str, int]:
    """Count satisfaction keys set to 1 across facets."""
    counts: dict[str, int] = defaultdict(int)
    for f in facets.values():
        for key, val in f.satisfaction.items():
            if val:
                counts[key] += 1
    return dict(counts)


def _count_friction(facets: dict[str, SessionFacet]) -> dict[str, int]:
    """Sum friction counts across facets."""
    counts: dict[str, int] = defaultdict(int)
    for f in facets.values():
        for key, val in f.friction_counts.items():
            counts[key] += val
    return dict(counts)


def _count_goal_categories(facets: dict[str, SessionFacet]) -> dict[str, int]:
    """Count goal categories set to 1 across facets."""
    counts: dict[str, int] = defaultdict(int)
    for f in facets.values():
        for key, val in f.goal_categories.items():
            if val:
                counts[key] += 1
    return dict(counts)


def _extract_single_facet(
    db_path: Path | str,
    sid: str,
    model: str,
) -> SessionFacet:
    """Extract facets for a single session (thread-safe)."""
    transcript = reconstruct_transcript(db_path, sid)
    meta = extract_session_meta(db_path, sid)
    meta_summary = (
        f"Title: {meta.title}\n"
        f"Duration: {meta.duration_minutes:.1f} min\n"
        f"User messages: {meta.user_msg_count}\n"
        f"Assistant messages: {meta.assistant_msg_count}\n"
        f"Total tokens: {meta.total_tokens}\n"
        f"Cost: ${meta.cost:.4f}\n"
        f"Tools: {', '.join(meta.tool_counts) if meta.tool_counts else 'none'}\n"
        f"Languages: {', '.join(meta.languages) if meta.languages else 'none'}\n"
        f"Agents: {', '.join(meta.agent_counts) if meta.agent_counts else 'none'}"
    )
    prompt = build_facet_prompt(transcript, meta_summary)
    llm_result = run_llm(prompt, model=model)
    return SessionFacet(
        session_id=sid,
        underlying_goal=llm_result.get("underlying_goal", ""),
        goal_categories=llm_result.get("goal_categories", {}),
        outcome=llm_result.get("outcome", ""),
        satisfaction=llm_result.get("satisfaction", {}),
        helpfulness=llm_result.get("helpfulness", ""),
        session_type=llm_result.get("session_type", ""),
        friction_counts=llm_result.get("friction_counts", {}),
        friction_detail=llm_result.get("friction_detail", ""),
        primary_success=llm_result.get("primary_success", ""),
        brief_summary=llm_result.get("brief_summary", ""),
    )


def extract_facets(
    db_path: Path | str,
    session_ids: list[str],
    config: InsightsConfig,
    cache: FacetCache | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, SessionFacet]:
    """Extract per-session facets with caching and concurrent LLM calls."""
    if cache is None:
        cache = FacetCache()

    result: dict[str, SessionFacet] = {}

    if config.force:
        uncached = list(session_ids)
        cached_ids: list[str] = []
    else:
        cached_ids = [sid for sid in session_ids if cache.has(sid)]
        uncached = [sid for sid in session_ids if not cache.has(sid)]

    # Load cached facets
    for sid in cached_ids:
        facet = cache.get(sid)
        if facet is not None:
            result[sid] = facet

    # Limit new sessions
    if not config.force:
        uncached = uncached[:_MAX_NEW_SESSIONS]

    total = len(uncached)
    if total == 0:
        return result

    workers = _default_concurrency(config.concurrency)
    completed = 0
    lock = threading.Lock()

    def _on_done(sid: str, facet: SessionFacet | None) -> None:
        nonlocal completed
        with lock:
            completed += 1
            if facet is not None:
                cache.put(sid, facet)
                result[sid] = facet
            if on_progress is not None:
                on_progress(completed, total)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_extract_single_facet, db_path, sid, config.model): sid
            for sid in uncached
        }
        for future in as_completed(futures):
            sid = futures[future]
            try:
                facet = future.result()
                _on_done(sid, facet)
            except Exception:
                warnings.warn(
                    f"Failed to extract facets for session {sid}",
                    stacklevel=2,
                )
                _on_done(sid, None)

    return result


def run_aggregate_analysis(
    facets: dict[str, SessionFacet],
    stats: AggregatedStats,
    config: InsightsConfig,
) -> dict[str, dict]:
    """Run 7 aggregate LLM prompts and return results."""
    aggregated_data = {
        "session_count": stats.total_sessions,
        "analyzed_count": len(facets),
        "total_cost": stats.total_cost,
        "top_agents": stats.top_agents,
        "top_models": stats.top_models,
        "top_tools": stats.top_tools,
        "outcome_distribution": _count_outcomes(facets),
        "satisfaction_distribution": _count_satisfaction(facets),
        "friction_distribution": _count_friction(facets),
        "session_summaries": [f.brief_summary for f in facets.values() if f.brief_summary][:20],
        "goal_categories": _count_goal_categories(facets),
    }

    prompts = [
        ("project_areas", build_project_areas_prompt),
        ("interaction_style", build_interaction_style_prompt),
        ("agent_performance", build_agent_performance_prompt),
        ("friction", build_friction_prompt),
        ("suggestions", build_suggestions_prompt),
        ("tool_health", build_tool_health_prompt),
        ("horizon", build_horizon_prompt),
    ]

    results: dict[str, dict] = {}
    workers = min(_default_concurrency(config.concurrency), len(prompts))

    def _run_prompt(key: str, builder) -> tuple[str, dict]:
        try:
            prompt_text = builder(aggregated_data)
            return key, run_llm(prompt_text, model=config.model)
        except Exception:
            return key, {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_run_prompt, key, builder) for key, builder in prompts]
        for future in as_completed(futures):
            key, val = future.result()
            results[key] = val

    return results


def generate_at_a_glance(
    aggregate_results: dict[str, dict],
    stats: AggregatedStats,
    config: InsightsConfig,
) -> dict:
    """Synthesize all insights into an at-a-glance summary."""
    stats_summary = {
        "total_sessions": stats.total_sessions,
        "analyzed_sessions": stats.analyzed_sessions,
        "date_range": stats.date_range,
        "total_messages": stats.total_messages,
        "total_cost": stats.total_cost,
        "top_tools": stats.top_tools,
        "top_agents": stats.top_agents,
        "top_models": stats.top_models,
    }
    try:
        prompt = build_at_a_glance_prompt(aggregate_results, stats_summary)
        return run_llm(prompt, model=config.model)
    except Exception:
        return {}
