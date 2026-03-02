"""LLM runner for insights analysis via opencode run subprocess."""

from __future__ import annotations

import json
import subprocess
import time


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
