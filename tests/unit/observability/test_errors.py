"""Unit tests for observability public error types (OBS-001)."""

from __future__ import annotations

import observability
from observability import (
    DuplicateMetricError,
    HighCardinalityLabelError,
    InvalidLogEnvelopeError,
    InvalidTraceContextError,
    RedactionRequiredError,
    TelemetryNotInitializedError,
)
from observability.errors import (
    DuplicateMetricError as ErrorsDuplicateMetricError,
    HighCardinalityLabelError as ErrorsHighCardinalityLabelError,
    InvalidLogEnvelopeError as ErrorsInvalidLogEnvelopeError,
    InvalidTraceContextError as ErrorsInvalidTraceContextError,
    RedactionRequiredError as ErrorsRedactionRequiredError,
    TelemetryNotInitializedError as ErrorsTelemetryNotInitializedError,
)

ERROR_CASES = [
    (TelemetryNotInitializedError, RuntimeError, ErrorsTelemetryNotInitializedError),
    (InvalidLogEnvelopeError, ValueError, ErrorsInvalidLogEnvelopeError),
    (HighCardinalityLabelError, ValueError, ErrorsHighCardinalityLabelError),
    (RedactionRequiredError, ValueError, ErrorsRedactionRequiredError),
    (InvalidTraceContextError, ValueError, ErrorsInvalidTraceContextError),
    (DuplicateMetricError, ValueError, ErrorsDuplicateMetricError),
]

ERROR_NAMES = frozenset(
    {
        "TelemetryNotInitializedError",
        "InvalidLogEnvelopeError",
        "HighCardinalityLabelError",
        "RedactionRequiredError",
        "InvalidTraceContextError",
        "DuplicateMetricError",
    }
)


def test_all_includes_all_error_names() -> None:
    assert ERROR_NAMES <= set(observability.__all__)


def test_public_import_path_resolves() -> None:
    for public_cls, _, errors_cls in ERROR_CASES:
        assert public_cls is errors_cls


def test_error_subclass_of_documented_base() -> None:
    for public_cls, base_cls, _ in ERROR_CASES:
        assert issubclass(public_cls, base_cls)
