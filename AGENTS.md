# AGENTS.md — opencode-usage

Guidelines for AI agents working in this repository.

## Project Overview

Python CLI tool that reads OpenCode's local SQLite database and displays token usage statistics. Uses Rich for terminal rendering, argparse for CLI, and dataclasses for data structures.

**Stack**: Python 3.10+, Rich, SQLite, pytest, Ruff, uv

## Repository Structure

```
src/opencode_usage/
  __init__.py      # Package init, __version__ only
  __main__.py      # `python -m opencode_usage` entry
  cli.py           # Argument parsing, main(), orchestration
  db.py            # SQLite queries, dataclasses (TokenStats, UsageRow, OpenCodeDB)
  render.py        # Rich table rendering, formatting helpers
tests/
  test_cli.py      # CLI parsing, _resolve_since, _compute_deltas, _fetch_rows
  test_db.py       # DB queries with in-memory SQLite fixtures
  test_render.py   # Formatting helpers (_fmt_tokens, _spark_bar, etc.)
```

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
| Classes | PascalCase | `OpenCodeDB`, `TokenStats` |
| Public functions | snake_case | `daily`, `render_summary` |
| Private functions | `_snake_case` | `_fmt_tokens`, `_connect` |
| Module constants | `_UPPER_CASE` | `_BAR_WIDTH_DEFAULT`, `_BAR_FULL` |
| Variables | snake_case | `db_path`, `group_by` |
| Test classes | `Test{Feature}` | `TestSparkBar`, `TestDaily` |
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

```python
# DB connection pattern
conn = self._connect()
try:
    rows = conn.execute(sql, params).fetchall()
finally:
    conn.close()
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
```

## Testing Conventions

- **Framework**: pytest (no unittest)
- **Structure**: Test classes grouped by feature, one class per function/component
- **Fixtures**: `@pytest.fixture()` for shared setup (e.g., temp DB with test data)
- **Assertions**: Plain `assert`, `pytest.approx` for floats, `pytest.raises` for exceptions
- **Section comments** separate test groups: `# ── _fmt_tokens ─────────────`
- **Test files mirror source**: `test_db.py` tests `db.py`, `test_render.py` tests `render.py`

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
fix(db): use ~/.local/share path on all platforms
chore(release): bump version to 0.1.2
test: add unit test suite
docs: add PyPI installation instructions
```

## Key Patterns

- **Console**: Module-level `console = Console()` in render.py, reconfigurable via `configure_console()`
- **SQL**: Raw f-strings for dynamic GROUP BY/ORDER, parameterized `?` for user values
- **Datetime**: Always timezone-aware (`datetime.now().astimezone()`), stored as milliseconds
- **JSON output**: `round(cost, 4)`, `ensure_ascii=False`, `indent=2`
- **Version**: In `pyproject.toml` (canonical), also in `__init__.py` (may drift — pyproject.toml is authoritative)
