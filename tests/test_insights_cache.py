"""Tests for FacetCache — per-session facet caching with atomic writes."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencode_usage.insights.cache import FacetCache
from opencode_usage.insights.types import SessionFacet


@pytest.fixture()
def sample_facet() -> SessionFacet:
    """Sample SessionFacet for testing."""
    return SessionFacet(
        session_id="ses_abc123",
        underlying_goal="Implement dark mode toggle",
        goal_categories={"feature": 1},
        outcome="Successfully added dark mode with CSS-in-JS",
        satisfaction={"completeness": 9, "clarity": 8},
        helpfulness="Very helpful for setup",
        session_type="engineering",
        friction_counts={"naming": 1},
        friction_detail="Struggled with CSS variable naming",
        primary_success="Clean toggle implementation",
        brief_summary="Added dark mode to settings",
    )


# ── __init__ ─────────────────────────────────────────────────────────
class TestFacetCacheInit:
    """Test FacetCache.__init__()."""

    def test_init_creates_cache_dir_if_missing(self, tmp_path: Path) -> None:
        """Creates cache_dir if it doesn't exist."""
        cache_dir = tmp_path / "facets"
        assert not cache_dir.exists()
        FacetCache(cache_dir)
        assert cache_dir.exists()

    def test_init_with_none_uses_default_path(self) -> None:
        """Uses ~/.local/share/opencode-usage/facets/ when cache_dir=None."""
        cache = FacetCache(None)
        # Default path should contain "opencode-usage" and "facets"
        assert "opencode-usage" in str(cache.cache_dir)
        assert "facets" in str(cache.cache_dir)

    def test_init_with_explicit_path(self, tmp_path: Path) -> None:
        """Uses provided cache_dir."""
        cache_dir = tmp_path / "my_cache"
        cache = FacetCache(cache_dir)
        assert cache.cache_dir == cache_dir


# ── has() ────────────────────────────────────────────────────────────
class TestFacetCacheHas:
    """Test FacetCache.has()."""

    def test_has_returns_false_for_missing(self, tmp_path: Path) -> None:
        """Returns False when session JSON doesn't exist."""
        cache = FacetCache(tmp_path)
        assert not cache.has("ses_missing")

    def test_has_returns_true_after_put(self, tmp_path: Path, sample_facet: SessionFacet) -> None:
        """Returns True after put() is called."""
        cache = FacetCache(tmp_path)
        cache.put(sample_facet.session_id, sample_facet)
        assert cache.has(sample_facet.session_id)

    def test_has_returns_false_after_clear(
        self, tmp_path: Path, sample_facet: SessionFacet
    ) -> None:
        """Returns False after clear() removes all files."""
        cache = FacetCache(tmp_path)
        cache.put(sample_facet.session_id, sample_facet)
        assert cache.has(sample_facet.session_id)
        cache.clear()
        assert not cache.has(sample_facet.session_id)


# ── get() ────────────────────────────────────────────────────────────
class TestFacetCacheGet:
    """Test FacetCache.get()."""

    def test_get_returns_none_for_missing(self, tmp_path: Path) -> None:
        """Returns None when session JSON doesn't exist."""
        cache = FacetCache(tmp_path)
        assert cache.get("ses_missing") is None

    def test_get_returns_facet_after_put(self, tmp_path: Path, sample_facet: SessionFacet) -> None:
        """Returns correct SessionFacet after put()."""
        cache = FacetCache(tmp_path)
        cache.put(sample_facet.session_id, sample_facet)
        retrieved = cache.get(sample_facet.session_id)
        assert retrieved is not None
        assert retrieved.session_id == sample_facet.session_id
        assert retrieved.underlying_goal == sample_facet.underlying_goal

    def test_get_returns_none_for_corrupt_json(self, tmp_path: Path) -> None:
        """Returns None gracefully when JSON is corrupt."""
        cache = FacetCache(tmp_path)
        # Write corrupt JSON directly
        json_file = tmp_path / "ses_corrupt.json"
        json_file.write_text("{ invalid json }", encoding="utf-8")
        assert cache.get("ses_corrupt") is None

    def test_get_returns_none_for_empty_file(self, tmp_path: Path) -> None:
        """Returns None gracefully for empty JSON file."""
        cache = FacetCache(tmp_path)
        json_file = tmp_path / "ses_empty.json"
        json_file.write_text("", encoding="utf-8")
        assert cache.get("ses_empty") is None


# ── put() ────────────────────────────────────────────────────────────
class TestFacetCachePut:
    """Test FacetCache.put()."""

    def test_put_creates_json_file(self, tmp_path: Path, sample_facet: SessionFacet) -> None:
        """Creates {session_id}.json file."""
        cache = FacetCache(tmp_path)
        cache.put(sample_facet.session_id, sample_facet)
        json_file = tmp_path / f"{sample_facet.session_id}.json"
        assert json_file.exists()

    def test_put_round_trip(self, tmp_path: Path, sample_facet: SessionFacet) -> None:
        """Put then get returns identical data."""
        cache = FacetCache(tmp_path)
        cache.put(sample_facet.session_id, sample_facet)
        retrieved = cache.get(sample_facet.session_id)
        assert retrieved == sample_facet

    def test_put_overwrites_existing(self, tmp_path: Path, sample_facet: SessionFacet) -> None:
        """Overwrites existing file without error."""
        cache = FacetCache(tmp_path)
        cache.put(sample_facet.session_id, sample_facet)
        # Modify and re-put
        sample_facet.outcome = "Modified outcome"
        cache.put(sample_facet.session_id, sample_facet)
        retrieved = cache.get(sample_facet.session_id)
        assert retrieved.outcome == "Modified outcome"

    def test_put_uses_atomic_write(self, tmp_path: Path) -> None:
        """Uses atomic write pattern: .tmp then os.rename()."""
        cache = FacetCache(tmp_path)
        facet = SessionFacet(
            session_id="ses_atomic",
            underlying_goal="Test atomic write",
        )
        cache.put(facet.session_id, facet)
        # Verify no .tmp file remains
        tmp_file = tmp_path / f"{facet.session_id}.json.tmp"
        assert not tmp_file.exists()
        # Verify final file exists
        json_file = tmp_path / f"{facet.session_id}.json"
        assert json_file.exists()

    def test_put_formats_json_with_indent(self, tmp_path: Path, sample_facet: SessionFacet) -> None:
        """Writes JSON with indent=2 for readability."""
        cache = FacetCache(tmp_path)
        cache.put(sample_facet.session_id, sample_facet)
        json_file = tmp_path / f"{sample_facet.session_id}.json"
        content = json_file.read_text(encoding="utf-8")
        # Check that JSON is formatted (has newlines and indentation)
        assert "\n" in content
        assert "  " in content


# ── clear() ──────────────────────────────────────────────────────────
class TestFacetCacheClear:
    """Test FacetCache.clear()."""

    def test_clear_removes_all_json_files(self, tmp_path: Path) -> None:
        """Removes all *.json files from cache_dir."""
        cache = FacetCache(tmp_path)
        facet1 = SessionFacet(session_id="ses_001", underlying_goal="Goal 1")
        facet2 = SessionFacet(session_id="ses_002", underlying_goal="Goal 2")
        cache.put(facet1.session_id, facet1)
        cache.put(facet2.session_id, facet2)
        assert (tmp_path / "ses_001.json").exists()
        assert (tmp_path / "ses_002.json").exists()
        cache.clear()
        assert not (tmp_path / "ses_001.json").exists()
        assert not (tmp_path / "ses_002.json").exists()

    def test_clear_ignores_non_json_files(self, tmp_path: Path) -> None:
        """Does not remove non-.json files."""
        cache = FacetCache(tmp_path)
        facet = SessionFacet(session_id="ses_001", underlying_goal="Goal")
        cache.put(facet.session_id, facet)
        # Create a non-JSON file
        other_file = tmp_path / "other.txt"
        other_file.write_text("important data", encoding="utf-8")
        cache.clear()
        assert not (tmp_path / "ses_001.json").exists()
        assert other_file.exists()

    def test_clear_on_empty_cache_succeeds(self, tmp_path: Path) -> None:
        """Calling clear() on empty cache doesn't raise."""
        cache = FacetCache(tmp_path)
        cache.clear()  # Should not raise
        assert tmp_path.exists()


# ── Integration ──────────────────────────────────────────────────────
class TestFacetCacheIntegration:
    """Integration tests for FacetCache workflow."""

    def test_multiple_sessions_isolated(self, tmp_path: Path) -> None:
        """Multiple sessions cached independently."""
        cache = FacetCache(tmp_path)
        facet1 = SessionFacet(session_id="ses_001", underlying_goal="Goal 1", outcome="Outcome 1")
        facet2 = SessionFacet(session_id="ses_002", underlying_goal="Goal 2", outcome="Outcome 2")
        cache.put(facet1.session_id, facet1)
        cache.put(facet2.session_id, facet2)
        assert cache.get("ses_001").outcome == "Outcome 1"
        assert cache.get("ses_002").outcome == "Outcome 2"

    def test_default_field_values_preserved(self, tmp_path: Path) -> None:
        """Dataclass default values preserved through round-trip."""
        cache = FacetCache(tmp_path)
        facet = SessionFacet(session_id="ses_test", underlying_goal="Test")
        cache.put(facet.session_id, facet)
        retrieved = cache.get(facet.session_id)
        assert retrieved.goal_categories == {}
        assert retrieved.satisfaction == {}
        assert retrieved.friction_counts == {}
        assert retrieved.outcome == ""
        assert retrieved.helpfulness == ""

    def test_complex_dict_fields_preserved(self, tmp_path: Path) -> None:
        """Complex nested dict fields survive serialization."""
        cache = FacetCache(tmp_path)
        facet = SessionFacet(
            session_id="ses_complex",
            underlying_goal="Complex test",
            goal_categories={"feature": 2, "bug_fix": 1},
            satisfaction={"completeness": 9, "clarity": 7, "speed": 8},
        )
        cache.put(facet.session_id, facet)
        retrieved = cache.get(facet.session_id)
        assert retrieved.goal_categories == {"feature": 2, "bug_fix": 1}
        assert retrieved.satisfaction == {"completeness": 9, "clarity": 7, "speed": 8}
