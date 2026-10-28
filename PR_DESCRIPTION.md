# Pull Request: Add support for OpenCode v2 and mixed database schemas

## Problem

OpenCode v2 introduces a new database schema:
- Messages are stored in `session_message` instead of `message`, with the role stored in the `type` column instead of `json_extract(data, '$.role')`.
- Sessions are stored in `session_v2` instead of `session`.
- Inside `session_message.data`, model info is nested under `model.id` and `model.providerID` rather than top-level `modelID` / `providerID`.
- `session_message.data` does not contain `tokens.total` (it must be calculated as `tokens.input + tokens.output + tokens.reasoning`).

Because `opencode-usage` queried only the legacy `message` and `session` tables, running `opencode-usage` on modern OpenCode installations reported **0 calls** for recent sessions. On migrated databases containing both schemas, recent v2 messages were completely ignored while only legacy v1 messages appeared.

## Solution

1. **Schema detection & query normalization**:
   - `OpenCodeDB` checks `sqlite_master` for available tables (`message`, `session_message`, `session_v2`, `session`).
   - Generates a unified subquery that normalizes assistant messages across v1, v2, and mixed databases into common fields: `id`, `session_id`, `time_created_ms`, `agent`, `model`, `provider`, `input_tokens`, `output_tokens`, `reasoning_tokens`, `cache_read`, `cache_write`, `total_tokens`, `cost`.
   - Filters out aborted/empty assistant rows (`total_tokens > 0`).

2. **Deduplication in mixed databases**:
   - Databases migrated from v1 to v2 preserve message IDs. To prevent double-counting, rows from legacy `message` are filtered out when their `id` already exists in `session_message`.
   - Historical messages that only exist in v1 continue to be counted.

3. **Session title resolution**:
   - `by_session` resolves session titles from `session_v2` for v2 sessions and falls back to `session` for legacy sessions.

4. **100% Backwards Compatibility**:
   - Public API, CLI flags, JSON output schema, and rich tables remain completely unchanged.
   - Databases with only v1 tables continue to work exactly as before.

## Evidence & Verification

- **Tests added**:
  - `TestV2SchemaSupport`: tests `totals()`, `by_model()`, `by_session()`, `daily()`, `by_agent()`, `by_provider()`, time filters (`since`/`until`), timestamps in seconds vs ms, and JSON serialization against synthetic v2 databases.
  - `TestMixedSchemaSupport`: tests deduplication with overlapping message IDs as well as disjoint v1 and v2 records.
  - `TestFetchRows`: verifies CLI row fetching across all grouping modes (`day`, `model`, `agent`, `provider`, `session`) on v2 databases.
- **Test suite**: All existing and new tests pass cleanly (196 passing tests).
- **Tested on real OpenCode v2 database**:
  - `opencode-usage run --since 3d` correctly reports recent v2 assistant calls (e.g. 97 calls with model breakdown `beam-free`, `deepseek-v4.1-flash-free`).
  - `opencode-usage run --since 14d` displays both historical v1 calls and modern v2 calls without duplication.
  - `opencode-usage run --json` produces valid JSON output matching the expected format.
