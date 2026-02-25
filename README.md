# opencode-usage

CLI tool to track and display [OpenCode](https://github.com/opencodeco/opencode) token usage statistics. Reads directly from OpenCode's local SQLite database — no API keys or external services needed.

## Features

- **Daily breakdown** — token usage and cost per day
- **Group by dimension** — model, agent, provider, or session
- **Agent × Model view** — see which model each agent uses
- **Time filtering** — last N days, relative durations (`7d`, `2w`), or ISO dates
- **JSON output** — pipe to `jq` or other tools
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

```bash
# Default: last 7 days, daily breakdown
opencode-usage

# Quick shortcuts
opencode-usage today
opencode-usage yesterday

# Time filtering
opencode-usage --days 30
opencode-usage --since 7d
opencode-usage --since 2025-01-01

# Group by dimension
opencode-usage --by model
opencode-usage --by agent          # shows model per agent
opencode-usage --by provider
opencode-usage --by session --limit 10

# JSON output
opencode-usage --json
opencode-usage --by model --json | jq '.rows[].label'
```

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
