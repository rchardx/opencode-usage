# AGENTS.md — opencode-usage

Guidelines for AI agents working in this repository.

## Project Overview

Python CLI tool that reads OpenCode's local SQLite database and displays token usage statistics, with an optional LLM-powered insights analysis that produces an HTML report. Uses Rich for terminal rendering, argparse for CLI with subcommands, and dataclasses for data structures.

**Two modes of operation:**

1. **`run`** (default) — Token usage tables: daily breakdown, group-by model/agent/provider/session, period comparison, JSON export.
2. **`insights`** — LLM-powered analysis pipeline: extract session transcripts → concurrent LLM facet extraction → aggregate analysis → generate a self-contained HTML report.

**Stack**: Python 3.10+, Rich, SQLite, pytest, Ruff, uv

## Repository Structure

```
src/opencode_usage/
  __init__.py        # Package init, __version__ via importlib.metadata
  __main__.py        # `python -m opencode_usage` entry
  _opencode_cli.py   # Wrapper around `opencode` binary (db path, config paths, models)
  auth.py            # Credential resolution (env → auth.json → opencode.json)
  cli.py             # Subcommand parser (run/insights), main() dispatcher
  db.py              # SQLite queries, dataclasses (TokenStats, UsageRow, OpenCodeDB)
  llm.py             # Thin OpenAI-compatible HTTP client (stdlib urllib)
  models.py          # Model discovery, tier-based ranking, interactive picker
  render.py          # Rich table rendering, formatting helpers

  insights/          # LLM-powered analysis subpackage
    __init__.py      # Re-exports: AggregatedStats, FacetCache, InsightsConfig, SessionFacet, SessionMeta
    types.py         # Dataclasses: SessionFacet, SessionMeta, AggregatedStats, InsightsConfig
    extract.py       # Session filtering, metadata extraction, transcript reconstruction, stats
    analyze.py       # Concurrent LLM facet extraction, aggregate analysis, NDJSON parsing
    cache.py         # Per-session facet cache with atomic writes (.tmp → os.rename)
    prompts.py       # Prompt builders for 8 analysis dimensions
    report.py        # HTML report generation (9-section terminal-hacker aesthetic)
    orchestrator.py  # Pipeline: extract → analyze → report, Rich progress display

tests/
  conftest.py                   # autouse fixture: clears lru_cache between tests
  test_auth.py                  # Credential resolution, list_providers
  test_cli.py                   # CLI parsing, _resolve_since, _compute_deltas, _fetch_rows
  test_db.py                    # DB queries with in-memory SQLite fixtures
  test_insights_analyze.py      # Facet extraction, aggregate analysis, NDJSON/JSON parsing
  test_insights_cache.py        # FacetCache has/get/put/clear, corruption handling
  test_insights_extract.py      # Session filtering, metadata, transcript, stats extraction
  test_insights_orchestrator.py # Pipeline orchestration, graceful degradation
  test_insights_prompts.py      # Prompt builder output validation
  test_insights_report.py       # HTML report sections, CSS, rendering helpers
  test_insights_types.py        # Dataclass defaults, field types
  test_llm.py                   # HTTP client, error handling, JSON parsing
  test_models.py                # Model listing, ranking, search, tier sorting
  test_opencode_cli.py          # CLI wrapper, path resolution, XDG fallbacks
  test_render.py                # Formatting helpers (_fmt_tokens, _spark_bar, etc.)
```

## CLI Subcommands

The CLI uses argparse subcommands. When invoked without a subcommand (or with flags only), it auto-defaults to `run`.

### `run` (default)

Token usage statistics with tabular output.

```bash
opencode-usage                         # default: last 7 days, daily breakdown
opencode-usage run --days 30
opencode-usage run --since 7d          # relative: 7d, 2w, 30d, 3h
opencode-usage run --since 2025-01-01  # ISO date
opencode-usage run --by model          # group by: model, agent, provider, session, day
opencode-usage run --by agent --limit 10
opencode-usage run --json
opencode-usage run --compare           # compare with previous period of same length
```

| Flag | Type | Default | Description |
|---|---|---|---|
| `--days N` | int | 7 | Show last N days |
| `--since SPEC` | str | — | `'7d'`, `'2w'`, `'3h'`, or ISO date |
| `--by DIM` | choice | `day` | `model`, `agent`, `provider`, `session`, `day` |
| `--limit N` | int | — | Max rows to display |
| `--json` | flag | — | Output as JSON |
| `--compare` | flag | — | Compare with previous period |

### `insights`

LLM-powered usage analysis → HTML report.

```bash
opencode-usage insights                          # interactive model picker
opencode-usage insights --model gpt-4o-mini      # specific model
opencode-usage insights --force                   # ignore cache, re-analyze
opencode-usage insights --concurrency 4           # limit parallel LLM workers
opencode-usage insights --output report.html      # custom output path
opencode-usage insights --days 30                 # last 30 days (default: 30)
```

| Flag | Type | Default | Description |
|---|---|---|---|
| `--days N` | int | 30 | Show last N days |
| `--since SPEC` | str | — | `'7d'`, `'2w'`, `'3h'`, or ISO date |
| `--model ID` | str | — | Model for analysis (interactive picker if omitted) |
| `--force` | flag | — | Re-analyze, ignore cache |
| `--concurrency N` | int | `min(cpu_count, 8)` | Max parallel LLM workers |
| `--output PATH` | str | `./opencode-insights.html` | Output path for HTML report |

### Global flags

| Flag | Description |
|---|---|
| `-V`, `--version` | Print version and exit |

## Build / Lint / Test Commands

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest tests/

# Run a single test file
uv run pytest tests/test_render.py

# Run a single test class
uv run pytest tests/test_render.py::TestSparkBar

# Run a single test method
uv run pytest tests/test_render.py::TestSparkBar::test_mid_value

# Verbose output
uv run pytest tests/ -v

# Lint (check only, matches CI)
uvx ruff check .
uvx ruff format --check .

# Lint (auto-fix, matches pre-commit)
uvx ruff check --fix .
uvx ruff format .
```

**Important**: CI runs `ruff check` and `ruff format --check` (no auto-fix). Always run both checks before committing to avoid CI failures. Pre-commit hooks auto-fix but CI does not.

## CI Pipelines

- **CI** (`.github/workflows/ci.yml`): Runs on push/PR to main. Lint with ruff, test on Python 3.10/3.12/3.13.
- **Release** (`.github/workflows/release.yml`): Triggered by `v*` tags. Builds, publishes to PyPI, creates GitHub Release.

## Code Style

### Ruff Configuration

Defined in `pyproject.toml`:
- Line length: **100**
- Target: **py310**
- Rules: E, W, F, I (isort), UP (pyupgrade), B (bugbear), SIM (simplify), RUF

### Imports

Every module starts with `from __future__ import annotations`. Group order:

```python
from __future__ import annotations          # 1. Always first

import os                                    # 2. Standard library (alphabetized)
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console             # 3. Third-party

from .db import OpenCodeDB, UsageRow         # 4. Local (relative imports)
```

Use `TYPE_CHECKING` for imports only needed by type checkers:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .db import UsageRow
```

### Naming

| Element | Convention | Example |
|---------|-----------|---------|
| Classes | PascalCase | `OpenCodeDB`, `TokenStats`, `SessionFacet` |
| Public functions | snake_case | `daily`, `render_summary`, `filter_sessions` |
| Private functions | `_snake_case` | `_fmt_tokens`, `_connect`, `_tier` |
| Private modules | `_snake_case.py` | `_opencode_cli.py` |
| Module constants | `_UPPER_CASE` | `_BAR_WIDTH_DEFAULT`, `_PREFERRED`, `_MAX_CONCURRENCY` |
| Variables | snake_case | `db_path`, `group_by` |
| Test classes | `Test{Feature}` | `TestSparkBar`, `TestDaily`, `TestFacetCache` |
| Test methods | `test_{behavior}` | `test_zero_returns_dash` |

### Type Annotations

Annotate all function signatures and non-obvious variables. Use `|` union syntax (not `Union`/`Optional`):

```python
def __init__(self, db_path: Path | str | None = None) -> None:
def _time_filter(self, since: datetime | None, until: datetime | None = None) -> tuple[str, list[Any]]:
d: dict[str, Any] = { ... }
```

### Docstrings

One-line triple-quoted summaries. No parameter/return docs:

```python
"""SQLite query layer for OpenCode's database."""       # module
"""Read-only access to the OpenCode SQLite database."""  # class
"""Human-readable token count."""                        # function
```

### Error Handling

- Use built-in exceptions with descriptive messages — no custom exception classes
- `try/finally` for resource cleanup (DB connections)
- `argparse.ArgumentTypeError` for CLI input validation
- Catch `FileNotFoundError` in `main()`, print with Rich markup, `sys.exit(1)`
- `RuntimeError` for auth failures, HTTP errors, LLM parse errors
- `warnings.warn` for non-critical LLM failures (individual session extraction)
- Graceful degradation: when `opencode` binary is unavailable, generate data-only report

```python
# DB connection pattern
conn = self._connect()
try:
    rows = conn.execute(sql, params).fetchall()
finally:
    conn.close()

# LLM error pattern — retry with exponential backoff
for attempt in range(max_retries):
    try:
        result = subprocess.run([...], timeout=timeout)
    except subprocess.TimeoutExpired:
        if attempt < max_retries - 1:
            time.sleep(min(2**attempt * 2, 60))
        continue
```

### Data Structures

Use `@dataclass` for data containers. Default values via `field(default_factory=...)`:

```python
@dataclass
class UsageRow:
    label: str
    calls: int = 0
    tokens: TokenStats = field(default_factory=TokenStats)
    cost: float = 0.0
    detail: str | None = None

@dataclass
class SessionFacet:
    session_id: str
    underlying_goal: str
    goal_categories: dict[str, int] = field(default_factory=dict)
    outcome: str = ""
    # ... (structured LLM extraction result per session)

@dataclass
class InsightsConfig:
    model: str
    days: int | None = None
    since: datetime | None = None
    force: bool = False
    output_path: str = "./opencode-insights.html"
    concurrency: int | None = None
```

## Testing Conventions

- **Framework**: pytest (no unittest)
- **Structure**: Test classes grouped by feature, one class per function/component
- **Fixtures**: `@pytest.fixture()` for shared setup (e.g., temp DB with test data)
- **Shared fixtures**: `conftest.py` provides `autouse` fixture that clears `lru_cache` on `_opencode_cli` helpers between every test
- **Assertions**: Plain `assert`, `pytest.approx` for floats, `pytest.raises` for exceptions
- **Mocking**: `unittest.mock.patch` for subprocess calls, file I/O, and LLM responses
- **Section comments** separate test groups: `# ── _fmt_tokens ─────────────`
- **Test files mirror source**: `test_db.py` tests `db.py`, `test_render.py` tests `render.py`, insights tests use `test_insights_{module}.py` pattern

```python
class TestFmtCost:
    def test_zero_returns_dash(self):
        assert _fmt_cost(0) == "-"

    def test_small_value_four_decimals(self):
        assert _fmt_cost(0.001) == "$0.0010"
```

DB tests create in-memory SQLite with realistic JSON message data:

```python
@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    db_file = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE message (...)")
    # Insert test rows with JSON data
    conn.close()
    return db_file
```

## Commit Style

Semantic commits in English. No co-author trailers, no footers:

```
feat: add horizontal trend bar to daily view
feat(cli): add --version / -V flag
feat(insights): add concurrent LLM analysis with ThreadPoolExecutor
fix(db): use ~/.local/share path on all platforms
refactor(cli): restructure argument parsing with run/insights subcommands
chore(release): bump version to 0.2.3
test: add unit test suite
docs: add PyPI installation instructions
```

## Key Patterns

- **Console**: Module-level `console = Console()` in render.py and orchestrator.py; honors `NO_COLOR` env var automatically via Rich
- **SQL**: Raw f-strings for dynamic GROUP BY/ORDER/WHERE, parameterized `?` for user values
- **Datetime**: Always timezone-aware (`datetime.now().astimezone()`), stored as milliseconds in SQLite
- **JSON output**: `round(cost, 4)`, `ensure_ascii=False`, `indent=2`
- **Version**: `importlib.metadata.version("opencode-usage")` in `__init__.py`, canonical source is `pyproject.toml`
- **CLI wrapper** (`_opencode_cli.py`): `subprocess.run` to invoke `opencode` binary, results cached with `@lru_cache`, XDG-based fallback paths when binary unavailable
- **Credential chain** (`auth.py`): Environment variable → `auth.json` → `opencode.json` for API key and base URL
- **Concurrent LLM** (`analyze.py`): `ThreadPoolExecutor` with configurable worker count, `warnings.warn` on per-session failures, NDJSON stream parsing
- **Atomic cache** (`cache.py`): Write to `.tmp` file then `os.rename()` for crash safety, one JSON file per session ID
- **Insights pipeline** (`orchestrator.py`): Phase 1 (extract from DB) → Phase 2 (concurrent LLM analysis) → Phase 3 (HTML report), with graceful degradation to data-only mode
- **Model ranking** (`models.py`): Tier-based sorting (preferred → opencode/* → github-copilot/* → others), interactive picker with search

## Configuration

| Environment Variable | Description |
|---|---|
| `OPENCODE_DB` | Override database path (default: auto-detected via `opencode db path` or `~/.local/share/opencode/opencode.db`) |
| `NO_COLOR` | Disable colored output when set (via Rich) |
| `{PROVIDER}_API_KEY` | API key for insights LLM provider (e.g. `OPENAI_API_KEY`) |
| `{PROVIDER}_BASE_URL` | Base URL override for insights LLM provider |
