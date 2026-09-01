"""Public collector error types."""

from __future__ import annotations


class CollectorError(Exception):
    """Base class for all collector module errors."""

    code: str = "COL_ERROR"
    retryable: bool = False


class CollectorFetchError(CollectorError):
    """Hacker News fetch failed with a retryable condition."""

    code = "COL_FETCH"
    retryable = True


class CollectorResponseError(CollectorError):
    """Hacker News returned an unrecoverable malformed payload."""

    code = "COL_RESPONSE"
    retryable = False


class CollectorTimeoutError(CollectorError):
    """Hacker News fetch exceeded the configured deadline."""

    code = "COL_TIMEOUT"
    retryable = True
