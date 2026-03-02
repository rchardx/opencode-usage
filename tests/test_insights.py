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


# ── TestQuantInsightsEngine ───────────────────────────────────────────────────


class TestQuantInsightsEngine:
    def test_build_quantitative(self, tmp_path, monkeypatch):
        """compute_quantitative returns populated QuantInsights from real DB."""
        import sqlite3
        from datetime import timezone

        from opencode_usage.db import OpenCodeDB
        from opencode_usage.insights import compute_quantitative

        db_file = tmp_path / "opencode.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT)")
        conn.execute(
            "CREATE TABLE session "
            "(id TEXT PRIMARY KEY, parent_id TEXT, title TEXT, "
            "time_created INTEGER, time_updated INTEGER)"
        )
        conn.execute(
            "CREATE TABLE part "
            "(id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, "
            "time_created INTEGER, data TEXT)"
        )
        import json

        now_ms = int(__import__("datetime").datetime.now(tz=timezone.utc).timestamp() * 1000)
        conn.execute(
            "INSERT INTO session VALUES (?,?,?,?,?)",
            ("s1", None, "Test Session", now_ms, now_ms),
        )
        conn.execute(
            "INSERT INTO message VALUES (?,?,?)",
            (
                "m1",
                "s1",
                json.dumps(
                    {
                        "role": "assistant",
                        "modelID": "test-model",
                        "agent": "build",
                        "providerID": "openrouter",
                        "tokens": {
                            "input": 100,
                            "output": 50,
                            "reasoning": 0,
                            "cache": {"read": 20, "write": 5},
                            "total": 175,
                        },
                        "cost": 0.01,
                        "time": {"created": now_ms},
                    }
                ),
            ),
        )
        conn.commit()
        conn.close()

        db = OpenCodeDB(db_path=db_file)
        quant = compute_quantitative(db, None, None)
        assert quant.avg_tokens_per_session > 0
        assert isinstance(quant.cache_efficiency, dict)
        assert isinstance(quant.cost_per_1k, dict)

    def test_handles_empty_data(self, tmp_path):
        """compute_quantitative handles empty DB gracefully."""
        import sqlite3

        from opencode_usage.db import OpenCodeDB
        from opencode_usage.insights import compute_quantitative

        db_file = tmp_path / "opencode.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT)")
        conn.execute(
            "CREATE TABLE session "
            "(id TEXT PRIMARY KEY, parent_id TEXT, title TEXT, "
            "time_created INTEGER, time_updated INTEGER)"
        )
        conn.execute(
            "CREATE TABLE part "
            "(id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, "
            "time_created INTEGER, data TEXT)"
        )
        conn.commit()
        conn.close()

        db = OpenCodeDB(db_path=db_file)
        quant = compute_quantitative(db, None, None)
        assert quant.avg_tokens_per_session == 0.0
        assert quant.cache_efficiency == {}
        assert quant.top_sessions == []


# ── TestInsightsPipeline ──────────────────────────────────────────────────────


class TestInsightsPipeline:
    def _make_db(self, tmp_path):
        """Create a minimal test DB for pipeline tests."""
        import json
        import sqlite3
        from datetime import timezone

        from opencode_usage.db import OpenCodeDB

        db_file = tmp_path / "opencode.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT)")
        conn.execute(
            "CREATE TABLE session "
            "(id TEXT PRIMARY KEY, parent_id TEXT, title TEXT, "
            "time_created INTEGER, time_updated INTEGER)"
        )
        conn.execute(
            "CREATE TABLE part "
            "(id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, "
            "time_created INTEGER, data TEXT)"
        )
        now_ms = int(__import__("datetime").datetime.now(tz=timezone.utc).timestamp() * 1000)
        conn.execute(
            "INSERT INTO session VALUES (?,?,?,?,?)",
            ("s1", None, "Test", now_ms, now_ms),
        )
        conn.execute(
            "INSERT INTO message VALUES (?,?,?)",
            (
                "m1",
                "s1",
                json.dumps(
                    {
                        "role": "assistant",
                        "modelID": "test-model",
                        "agent": "build",
                        "providerID": "openrouter",
                        "tokens": {
                            "input": 100,
                            "output": 50,
                            "reasoning": 0,
                            "cache": {"read": 10, "write": 5},
                            "total": 165,
                        },
                        "cost": 0.01,
                        "time": {"created": now_ms},
                    }
                ),
            ),
        )
        conn.commit()
        conn.close()
        return OpenCodeDB(db_path=db_file)

    def test_run_no_llm(self, tmp_path, monkeypatch):
        """run_insights with no_llm=True returns quantitative only."""
        from opencode_usage.insights import run_insights

        db = self._make_db(tmp_path)
        result = run_insights(db, None, None, no_llm=True)
        assert result.quantitative is not None
        assert result.facets is None
        assert result.suggestions is None

    def test_run_no_llm_json_serializable(self, tmp_path, monkeypatch):
        """run_insights result can be serialized to JSON."""
        import json

        from opencode_usage.insights import insights_to_dict, run_insights

        db = self._make_db(tmp_path)
        result = run_insights(db, None, None, no_llm=True)
        d = insights_to_dict(result)
        serialized = json.dumps(d)
        assert "quantitative" in serialized
