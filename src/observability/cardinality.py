"""Metric label cardinality guard pipeline (LLD §6.4)."""

from __future__ import annotations

import re
from collections.abc import Mapping

from observability.errors import HighCardinalityLabelError
from observability.redaction import matches_secret_pattern
from observability.types import FORBIDDEN_METRIC_LABEL_KEYS, MetricDescriptor

_PROMPT_LIKE_MAX_LENGTH = 256

_UUID_LIKE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_RAW_URL = re.compile(r"^https?://", re.IGNORECASE)


class CardinalityGuard:
    """Validates metric label keys and values before OTel instrument updates."""

    def validate_labels(
        self,
        descriptor: MetricDescriptor,
        labels: Mapping[str, str],
    ) -> Mapping[str, str]:
        """
        Pipeline (raises HighCardinalityLabelError):
          1. keys ⊆ descriptor.allowed_label_keys
          2. keys ∩ FORBIDDEN_METRIC_LABEL_KEYS == ∅
          3. value heuristics (UUID-like, raw URL, prompt-like > 256 chars)
          4. secret-pattern rejection via redaction.matches_secret_pattern(value)

        Returns sanitized label mapping (unchanged when valid).
        """
        sanitized = dict(labels)

        disallowed_keys = set(sanitized.keys()) - descriptor.allowed_label_keys
        if disallowed_keys:
            key = sorted(disallowed_keys)[0]
            raise HighCardinalityLabelError(
                f"Metric label key {key!r} is not in descriptor allowed_label_keys"
            )

        forbidden_keys = set(sanitized.keys()) & FORBIDDEN_METRIC_LABEL_KEYS
        if forbidden_keys:
            key = sorted(forbidden_keys)[0]
            raise HighCardinalityLabelError(
                f"Metric label key {key!r} is forbidden"
            )

        for key, value in sanitized.items():
            if _UUID_LIKE.search(value) is not None:
                raise HighCardinalityLabelError(
                    f"Metric label {key!r} has UUID-like value"
                )
            if _RAW_URL.match(value) is not None:
                raise HighCardinalityLabelError(
                    f"Metric label {key!r} has raw URL value"
                )
            if len(value) > _PROMPT_LIKE_MAX_LENGTH:
                raise HighCardinalityLabelError(
                    f"Metric label {key!r} exceeds maximum length {_PROMPT_LIKE_MAX_LENGTH}"
                )
            if matches_secret_pattern(value):
                raise HighCardinalityLabelError(
                    f"Metric label {key!r} contains a secret-like value"
                )

        return sanitized
