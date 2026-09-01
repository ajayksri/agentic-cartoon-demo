"""Pre-code test mold for AGT-006 — PromptLoader (LLD §4.4)."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import pytest

from agents import AgentPromptLoadError
from config.types import AgentId


_AGENT_ID = AgentId.TOPIC_SELECTOR


_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "agents" / "prompts"


def test_load_returns_normalized_lf_content_and_version_hash() -> None:
    """CG-AGT-004: version is first 12 hex chars of SHA-256 of normalized content."""
    from agents.constants import PROMPT_VERSION_HEX_LENGTH
    from agents.prompts.loader import PromptLoader

    path = _FIXTURES / "topic_selector.txt"
    loader = PromptLoader(enable_cache=False)
    result = loader.load(str(path), agent_id=_AGENT_ID)

    normalized = path.read_bytes().replace(b"\r\n", b"\n")
    expected_version = hashlib.sha256(normalized).hexdigest()[:PROMPT_VERSION_HEX_LENGTH]

    assert result.text == normalized.decode("utf-8")
    assert result.version == expected_version
    assert len(result.version) == PROMPT_VERSION_HEX_LENGTH


def test_crlf_normalized_before_hashing(tmp_path: Path) -> None:
    from agents.prompts.loader import PromptLoader

    prompt_file = tmp_path / "crlf_prompt.txt"
    prompt_file.write_bytes(b"line1\r\nline2\r\n")
    loader = PromptLoader(enable_cache=False)
    result = loader.load(str(prompt_file), agent_id=_AGENT_ID)
    assert "\r" not in result.text
    assert result.text == "line1\nline2\n"


def test_missing_file_raises_prompt_load_error(tmp_path: Path) -> None:
    from agents.prompts.loader import PromptLoader

    loader = PromptLoader(enable_cache=False)
    with pytest.raises(AgentPromptLoadError):
        loader.load(str(tmp_path / "missing.txt"), agent_id=_AGENT_ID)


def test_oversized_file_raises_prompt_load_error(tmp_path: Path) -> None:
    from agents.constants import PROMPT_FILE_MAX_BYTES
    from agents.prompts.loader import PromptLoader

    prompt_file = tmp_path / "huge.txt"
    prompt_file.write_bytes(b"x" * (PROMPT_FILE_MAX_BYTES + 1))
    loader = PromptLoader(enable_cache=False)
    with pytest.raises(AgentPromptLoadError):
        loader.load(str(prompt_file), agent_id=_AGENT_ID)


def test_cache_returns_same_result_for_unchanged_mtime() -> None:
    from agents.prompts.loader import PromptLoader

    path = _FIXTURES / "topic_selector.txt"
    loader = PromptLoader(enable_cache=True)
    first = loader.load(str(path), agent_id=_AGENT_ID)
    second = loader.load(str(path), agent_id=_AGENT_ID)
    assert first.version == second.version
    assert first.text == second.text


def test_cache_thread_safe_under_concurrent_load() -> None:
    from agents.prompts.loader import PromptLoader

    path = _FIXTURES / "topic_selector.txt"
    loader = PromptLoader(enable_cache=True)
    versions: list[str] = []
    errors: list[BaseException] = []

    def _load() -> None:
        try:
            versions.append(loader.load(str(path), agent_id=_AGENT_ID).version)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len(set(versions)) == 1
