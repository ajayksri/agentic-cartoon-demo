"""Dataclass JSON serialization helpers (internal)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum

from .types import ApiErrorEnvelope


def dataclass_to_json_dict(obj: object) -> dict[str, object]:
    """Recursively convert dataclasses and related types to JSON-serializable dict."""
    return _to_json_value(obj)  # type: ignore[return-value]


def envelope_json(envelope: ApiErrorEnvelope) -> dict[str, object]:
    """Stable error body shape for all 4xx/5xx."""
    return dataclass_to_json_dict(envelope)


def _to_json_value(obj: object) -> object:
    if obj is None:
        return None
    if is_dataclass(obj) and not isinstance(obj, type):
        result: dict[str, object] = {}
        for field in fields(obj):
            result[field.name] = _to_json_value(getattr(obj, field.name))
        return result
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, tuple):
        return [_to_json_value(item) for item in obj]
    if isinstance(obj, list):
        return [_to_json_value(item) for item in obj]
    if isinstance(obj, Mapping):
        return {str(key): _to_json_value(value) for key, value in obj.items()}
    return obj
