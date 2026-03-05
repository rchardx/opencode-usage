# opencode-usage

CLI tool to track and display [OpenCode](https://github.com/opencodeco/opencode) token usage statistics. Reads directly from OpenCode's local SQLite database — no API keys or external services needed for basic usage.

## Features

- **Daily breakdown** — token usage and cost per day
- **Group by dimension** — model, agent, provider, or session
- **Agent × Model view** — see which model each agent uses
- **Time filtering** — last N days, relative durations (`7d`, `2w`), or ISO dates
- **Period comparison** — compare current vs previous period with `--compare`
- **JSON output** — pipe to `jq` or other tools
- **LLM-powered insights** — analyze session transcripts and generate a self-contained HTML report
- **Cross-platform** — macOS, Linux, Windows

## Installation

```bash
# From PyPI
pip install opencode-usage

# Or with uv
uv tool install opencode-usage
```

### From source

```bash
git clone https://github.com/rchardx/opencode-usage.git
cd opencode-usage
uv sync
uv tool install -e .
```

After installation, `opencode-usage` is available globally.

## Usage

The CLI has two subcommands: `run` (default) and `insights`.

### `run` — Token usage statistics

```bash
# Default: last 7 days, daily breakdown
opencode-usage

# Time filtering
opencode-usage run --days 30
opencode-usage run --since 7d
opencode-usage run --since 2025-01-01

# Group by dimension
opencode-usage run --by model
opencode-usage run --by agent          # shows model per agent
opencode-usage run --by provider
opencode-usage run --by session --limit 10

# JSON output
opencode-usage run --json
opencode-usage run --by model --json | jq '.rows[].label'

# Compare with previous period
opencode-usage run --since 7d --compare
```

### `insights` — LLM-powered analysis

Analyze your OpenCode sessions and generate an HTML report with workflow insights, friction patterns, agent performance, and actionable suggestions.

```bash
# Interactive model picker
opencode-usage insights

# Specific model
opencode-usage insights --model gpt-4o-mini

# Customize analysis
opencode-usage insights --days 30 --concurrency 4 --output report.html

# Force re-analysis (ignore cache)
opencode-usage insights --force
```

Requires an API key for the LLM provider — set via environment variable (e.g. `OPENAI_API_KEY`) or OpenCode's `auth.json`.

### Example output

```
╭──────────────── OpenCode Usage — Last 7 days ────────────────╮
│   Calls: 1,280  │  Tokens: 52.3M  │  Cost: $0.00             │
╰──────────────────────────────────────────────────────────────╯

               Usage by Agent (Last 7 days)
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┓
┃ Agent                  ┃ Model        ┃ Calls ┃   Total ┃    Cost ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━╇━━━━━━━━━┩
│ build                  │ deepseek-r1  │   420 │   18.2M │       - │
│                        │ qwen-3-coder │   105 │    4.7M │       - │
├────────────────────────┼──────────────┼───────┼─────────┼─────────┤
│ explore                │ gemma-3      │   310 │   12.5M │       - │
│                        │ minimax-m2.5 │   198 │    8.1M │       - │
├────────────────────────┼──────────────┼───────┼─────────┼─────────┤
│ librarian              │ llama-4      │   156 │    5.8M │       - │
├────────────────────────┼──────────────┼───────┼─────────┼─────────┤
│ oracle                 │ qwen-3-coder │    91 │    3.0M │       - │
└────────────────────────┴──────────────┴───────┴─────────┴─────────┘
```

## Configuration

| Environment Variable | Description |
|---|---|
| `OPENCODE_DB` | Override database path (default: auto-detected per platform) |
| `NO_COLOR` | Disable colored output when set (see [no-color.org](https://no-color.org)) |
| `{PROVIDER}_API_KEY` | API key for insights LLM provider (e.g. `OPENAI_API_KEY`) |
| `{PROVIDER}_BASE_URL` | Base URL override for insights LLM provider |

Default database locations:

- **All platforms** (macOS, Linux, Windows): `~/.local/share/opencode/opencode.db`

## Development

```bash
git clone https://github.com/rchardx/opencode-usage.git
cd opencode-usage
uv sync

# Lint & format
uvx ruff check .
uvx ruff format .

# Install pre-commit hooks
uvx pre-commit install
```

## License

[MIT](LICENSE)
