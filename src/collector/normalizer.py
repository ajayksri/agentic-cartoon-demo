"""Story normalization pipeline: URL canonicalization, content guard, and normalizer."""

# GUARDRAIL: Input — sanitize untrusted HN content before it reaches any agent.

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from collector.hn_parser import RawObservation
from collector.messages import rejection_detail
from collector.service import StoryDraft
from collector.types import RejectedStoryRecord, RejectionReason, StorySource

TRACKING_PARAM_PATTERN = re.compile(r"(?i)^(utm_.*|fbclid|gclid)$")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class UrlCanonicalizationError(Exception):
    """Internal URL canonicalization failure."""


class UrlCanonicalizer:
    def canonicalize(self, url: str) -> str:
        trimmed = url.strip()
        if not trimmed:
            raise UrlCanonicalizationError("empty URL")

        original = trimmed
        explicit_port: int | None = None

        if "://" not in trimmed:
            trimmed = f"https://{trimmed}"
        else:
            scheme_sep = trimmed.find("://")
            port_sep = trimmed.find(":", scheme_sep + 3)
            slash_sep = trimmed.find("/", scheme_sep + 3)
            if port_sep != -1 and (slash_sep == -1 or port_sep < slash_sep):
                port_value = trimmed[port_sep + 1 : slash_sep if slash_sep != -1 else None]
                if port_value.isdigit():
                    explicit_port = int(port_value)

        parsed = urlparse(trimmed)

        scheme = parsed.scheme.lower() if parsed.scheme else ""
        host = parsed.hostname

        if not host:
            raise UrlCanonicalizationError(f"unparseable URL: {original}")

        if "." not in host and not host.replace(".", "").isdigit():
            raise UrlCanonicalizationError(f"invalid host: {host}")

        if scheme not in {"http", "https"}:
            raise UrlCanonicalizationError(f"unsupported scheme: {scheme}")

        if scheme == "http" and explicit_port is None:
            scheme = "https"

        host = host.lower()
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise UrlCanonicalizationError(f"invalid host encoding: {host}") from exc

        port = parsed.port
        if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
            port = None

        path = parsed.path or ""
        while "//" in path:
            path = path.replace("//", "/")
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        filtered_params: list[tuple[str, str]] = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if TRACKING_PARAM_PATTERN.match(key):
                continue
            filtered_params.append((key, value))
        filtered_params.sort(key=lambda item: item[0])
        query = urlencode(filtered_params, quote_via=quote)

        netloc = host if port is None else f"{host}:{port}"
        return urlunparse((scheme, netloc, path, "", query, ""))

    def canonicalize_optional(self, url: str | None) -> str | None:
        if url is None:
            return None
        trimmed = url.strip()
        if not trimmed:
            return None
        return self.canonicalize(trimmed)


class UntrustedContentGuard:
    def check(self, *values: str | None) -> bool:
        for value in values:
            if value is None:
                continue
            if CONTROL_CHAR_PATTERN.search(value) is not None:
                return False
        return True


class StoryNormalizer:
    def __init__(
        self,
        *,
        url_canonicalizer: UrlCanonicalizer | None = None,
        content_guard: UntrustedContentGuard | None = None,
        collected_at_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._url_canonicalizer = url_canonicalizer or UrlCanonicalizer()
        self._content_guard = content_guard or UntrustedContentGuard()
        self._collected_at_fn = collected_at_fn

    def normalize(
        self,
        observation: RawObservation,
        *,
        collected_at: datetime,
    ) -> StoryDraft | RejectedStoryRecord:
        source_id = str(observation.get("id", ""))
        raw_observation = dict(observation)

        if observation.get("type") != "story":
            return self._rejection(
                source_id=source_id or "unknown",
                collected_at=collected_at,
                raw_observation=raw_observation,
                reason_code=RejectionReason.VALIDATION_FAILED,
                stage="type_gate",
            )

        if not source_id or source_id == "None":
            return self._rejection(
                source_id="unknown",
                collected_at=collected_at,
                raw_observation=raw_observation,
                reason_code=RejectionReason.VALIDATION_FAILED,
                stage="required_fields",
                field="source_id",
            )

        title_raw = observation.get("title")
        if title_raw is None or (isinstance(title_raw, str) and not title_raw.strip()):
            return self._rejection(
                source_id=source_id,
                collected_at=collected_at,
                raw_observation=raw_observation,
                reason_code=RejectionReason.VALIDATION_FAILED,
                stage="required_fields",
                field="title",
            )

        title = self._collapse_title_whitespace(str(title_raw).strip())
        author_value = observation.get("by")
        author = str(author_value).strip() if author_value is not None else None
        if author == "":
            author = None
        url_value = observation.get("url")
        url = str(url_value).strip() if url_value is not None else None
        if url == "":
            url = None

        if not title:
            return self._rejection(
                source_id=source_id,
                collected_at=collected_at,
                raw_observation=raw_observation,
                reason_code=RejectionReason.NORMALIZATION_FAILED,
                stage="whitespace",
            )

        canonical_url: str | None
        if url is None:
            canonical_url = None
        else:
            try:
                canonical_url = self._url_canonicalizer.canonicalize(url)
            except UrlCanonicalizationError:
                parsed = urlparse(url.strip())
                if parsed.scheme and parsed.scheme not in {"http", "https"}:
                    canonical_url = url.strip()
                else:
                    return self._rejection(
                        source_id=source_id,
                        collected_at=collected_at,
                        raw_observation=raw_observation,
                        reason_code=RejectionReason.NORMALIZATION_FAILED,
                        stage="url",
                    )

        published_at, timestamp_failed = self._stage_published_at(observation.get("time"))
        if timestamp_failed:
            return self._rejection(
                source_id=source_id,
                collected_at=collected_at,
                raw_observation=raw_observation,
                reason_code=RejectionReason.VALIDATION_FAILED,
                stage="timestamp",
            )

        score_value = observation.get("score")
        score = (
            int(score_value)
            if isinstance(score_value, (int, float)) and not isinstance(score_value, bool)
            else None
        )

        descendants = observation.get("descendants")
        comment_count = (
            int(descendants)
            if isinstance(descendants, (int, float)) and not isinstance(descendants, bool)
            else None
        )

        if not self._content_guard.check(title, canonical_url, author):
            return self._rejection(
                source_id=source_id,
                collected_at=collected_at,
                raw_observation=raw_observation,
                reason_code=RejectionReason.UNTRUSTED_CONTENT,
            )

        return StoryDraft(
            source=StorySource.HACKERNEWS,
            source_id=source_id,
            collected_at=collected_at,
            raw_observation=raw_observation,
            title=title,
            url=canonical_url,
            author=author,
            score=score,
            comment_count=comment_count,
            published_at=published_at,
        )

    def _stage_published_at(
        self, unix_time: object | None
    ) -> tuple[datetime | None, bool]:
        if unix_time is None:
            return None, False
        if isinstance(unix_time, bool) or not isinstance(unix_time, (int, float)):
            return None, True
        return datetime.fromtimestamp(float(unix_time), tz=UTC), False

    def _collapse_title_whitespace(self, title: str) -> str:
        return re.sub(r"\s+", " ", title)

    def _rejection(
        self,
        *,
        source_id: str,
        collected_at: datetime,
        raw_observation: RawObservation,
        reason_code: RejectionReason,
        stage: str | None = None,
        field: str | None = None,
    ) -> RejectedStoryRecord:
        return RejectedStoryRecord(
            source=StorySource.HACKERNEWS,
            source_id=source_id,
            collected_at=collected_at,
            raw_observation=raw_observation,
            reason_code=reason_code,
            reason_detail=rejection_detail(
                reason_code=reason_code,
                stage=stage,
                field=field,
            ),
        )
