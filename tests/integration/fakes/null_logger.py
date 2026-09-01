"""Minimal Logger protocol double for CLI wiring."""

from __future__ import annotations


class NullLogger:
    """No-op logger satisfying observability.Logger for CLI deps."""

    def debug(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        del event, message, fields

    def info(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        del event, message, fields

    def warning(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        del event, message, fields

    def error(self, event: str, message: str, **fields: str | int | float | bool) -> None:
        del event, message, fields
