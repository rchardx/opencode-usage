from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

from .insights import Credentials

"""Thin OpenAI-compatible HTTP client using stdlib urllib."""


def chat_complete(
    credentials: Credentials,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: int = 60,
) -> str:
    """Call OpenAI-compatible API and return response text."""
    url = credentials.base_url.rstrip("/") + "/chat/completions"

    body = {
        "model": credentials.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(body).encode()

    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {credentials.api_key}",
            "Content-Type": "application/json",
        },
    )

    ctx = ssl.create_default_context()
    try:
        response = urllib.request.urlopen(req, context=ctx, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise RuntimeError("Authentication failed: check your API key") from e
        elif e.code == 429:
            raise RuntimeError("Rate limit exceeded") from e
        else:
            raise RuntimeError(f"HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e
    except TimeoutError as e:
        raise RuntimeError(f"Request timed out after {timeout}s") from e

    try:
        result = json.loads(response.read().decode())
        return result["choices"][0]["message"]["content"]
    finally:
        response.close()


def chat_complete_json(
    credentials: Credentials,
    messages: list[dict[str, str]],
    **kwargs: object,
) -> dict[str, object]:
    """Call OpenAI-compatible API and return parsed JSON response."""
    raw = chat_complete(credentials, messages, **kwargs)

    # Strip markdown code fences if present
    stripped = raw
    if stripped.startswith("```json\n"):
        stripped = stripped[8:]
    if stripped.startswith("```\n"):
        stripped = stripped[4:]
    if stripped.endswith("\n```"):
        stripped = stripped[:-4]
    elif stripped.endswith("```"):
        stripped = stripped[:-3]

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM returned non-JSON: {raw[:200]}") from e
