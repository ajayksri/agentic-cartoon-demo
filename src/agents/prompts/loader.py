"""Prompt file loading with version hashing and optional cache."""

# GUARDRAIL: Input — prompts loaded from approved files with size limits and version tracking.

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from config.types import AgentId

from agents.constants import PROMPT_FILE_MAX_BYTES, PROMPT_VERSION_HEX_LENGTH
from agents.errors import AgentPromptLoadError
from agents.messages import prompt_load_message


@dataclass(frozen=True, slots=True)
class PromptLoadResult:
    """Successful prompt load before template substitution."""

    text: str
    version: str
    path: str


@dataclass(frozen=True, slots=True)
class PromptCacheKey:
    path: str
    mtime_ns: int


@dataclass
class PromptCacheEntry:
    result: PromptLoadResult


class PromptLoader:
    """Loads prompt files with CRLF normalization and SHA-256 version hash."""

    def __init__(
        self,
        *,
        enable_cache: bool = True,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._enable_cache = enable_cache
        self._clock = clock
        self._cache: dict[PromptCacheKey, PromptCacheEntry] = {}
        self._lock = threading.Lock()

    def load(self, prompt_file: str, *, agent_id: AgentId) -> PromptLoadResult:
        path = Path(prompt_file)
        if not path.is_file():
            raise AgentPromptLoadError(
                prompt_load_message(agent_id=agent_id, reason="file not found"),
                agent_id=agent_id,
            )

        try:
            stat = path.stat()
        except OSError as exc:
            raise AgentPromptLoadError(
                prompt_load_message(agent_id=agent_id, reason=str(exc)),
                agent_id=agent_id,
            ) from exc

        if stat.st_size > PROMPT_FILE_MAX_BYTES:
            raise AgentPromptLoadError(
                prompt_load_message(agent_id=agent_id, reason="file too large"),
                agent_id=agent_id,
            )

        cache_key = PromptCacheKey(path=str(path), mtime_ns=stat.st_mtime_ns)
        if self._enable_cache:
            with self._lock:
                cached = self._cache.get(cache_key)
            if cached is not None:
                return cached.result

        try:
            raw_bytes = path.read_bytes()
        except OSError as exc:
            raise AgentPromptLoadError(
                prompt_load_message(agent_id=agent_id, reason=str(exc)),
                agent_id=agent_id,
            ) from exc

        normalized_bytes = raw_bytes.replace(b"\r\n", b"\n")
        normalized_text = normalized_bytes.decode("utf-8")
        version = hashlib.sha256(normalized_bytes).hexdigest()[:PROMPT_VERSION_HEX_LENGTH]
        result = PromptLoadResult(text=normalized_text, version=version, path=str(path))

        if self._enable_cache:
            with self._lock:
                self._cache[cache_key] = PromptCacheEntry(result=result)

        return result
