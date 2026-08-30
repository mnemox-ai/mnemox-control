"""Deterministic wire serialization and content hashing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


def _decimal_string(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format(normalized, "f")
    return format(normalized, "f").rstrip("0").rstrip(".")


def _datetime_string(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("canonical timestamps must be timezone-aware")
    utc_value = value.astimezone(UTC)
    timespec = "microseconds" if utc_value.microsecond else "seconds"
    rendered = utc_value.isoformat(timespec=timespec)
    if utc_value.microsecond:
        timestamp, offset = rendered.rsplit("+", maxsplit=1)
        rendered = f"{timestamp.rstrip('0').rstrip('.')}+{offset}"
    return rendered.replace("+00:00", "Z")


def _normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_string(value)
    if isinstance(value, datetime):
        return _datetime_string(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_normalize(item) for item in value]
    return value


def canonical_json_bytes(model: BaseModel, *, exclude: set[str] | None = None) -> bytes:
    """Serialize a model into stable UTF-8 JSON bytes."""
    data = model.model_dump(mode="python", exclude=exclude or set())
    normalized = _normalize(data)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def content_sha256(model: BaseModel, *, exclude: set[str] | None = None) -> str:
    """Return a lowercase SHA-256 digest of canonical model bytes."""
    return hashlib.sha256(canonical_json_bytes(model, exclude=exclude)).hexdigest()
