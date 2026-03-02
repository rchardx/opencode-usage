"""Tests for the insights cache pipeline."""

from __future__ import annotations

from opencode_usage.insights import (
    Facet,
    get_cached_facet,
    load_cache,
    save_facet,
)


def _make_facet() -> Facet:
    return Facet(
        underlying_goal="test goal",
        goal_categories={"implement_feature": 1},
        outcome="fully_achieved",
        satisfaction_counts={"satisfied": 1},
        friction_counts={},
        friction_detail="",
        session_type="single_task",
        primary_success="completed task",
        brief_summary="Test session",
        helpfulness="very_helpful",
    )


# ── TestFacetCache ────────────────────────────────────────────────────────────


class TestFacetCache:
    def test_save_and_load(self, tmp_path, monkeypatch):
        """save_facet then load_cache returns the saved facet."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        facet = _make_facet()
        save_facet("sess-1", 12345, facet)
        cache = load_cache()
        assert "sess-1" in cache
        assert cache["sess-1"].facet.underlying_goal == "test goal"

    def test_cache_invalidation(self, tmp_path, monkeypatch):
        """get_cached_facet returns None when session_updated mismatches."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        facet = _make_facet()
        save_facet("sess-2", 100, facet)
        assert get_cached_facet("sess-2", 100) is not None
        assert get_cached_facet("sess-2", 200) is None

    def test_corrupt_cache(self, tmp_path, monkeypatch):
        """Corrupt cache file returns empty dict gracefully."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        cache_dir = tmp_path / "opencode-usage" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "facets.json").write_text("not valid json {{{")
        result = load_cache()
        assert result == {}

    def test_atomic_write(self, tmp_path, monkeypatch):
        """save_facet leaves no .tmp files behind."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        facet = _make_facet()
        save_facet("sess-3", 999, facet)
        cache_dir = tmp_path / "opencode-usage" / "cache"
        tmp_files = list(cache_dir.glob("*.tmp"))
        assert len(tmp_files) == 0
