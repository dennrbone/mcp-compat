"""Deterministic UTF-8 JSON serialization."""

import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Serialize a JSON-compatible value deterministically without ASCII escaping."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def canonical_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value to deterministic UTF-8 bytes."""
    return canonical_json(value).encode("utf-8")
