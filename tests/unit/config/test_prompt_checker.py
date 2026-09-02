"""Pre-code T0 molds for PromptChecker S5 filesystem checks (CFG-008)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from config.errors import ConfigPromptNotFoundError


def _agent_draft_map(*, prompt_file: str) -> dict[Any, Any]:
    from config.draft import AgentDraft
    from config.types import AgentId, ProviderId

    return {
        AgentId.TOPIC_SELECTOR: AgentDraft(
            provider=ProviderId.GEMINI,
            model="gemini-pro",
            prompt_file=prompt_file,
        ),
    }


def test_s5_missing_prompt_file_raises_config_prompt_not_found_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CFG-TC-017 trace: missing prompt file at S5."""
    monkeypatch.chdir(tmp_path)
    missing = "prompts/missing.txt"
    agents = _agent_draft_map(prompt_file=missing)

    from config.validator import PromptChecker

    checker = PromptChecker()

    with pytest.raises(ConfigPromptNotFoundError) as exc_info:
        checker.check_all(agents)

    assert exc_info.value.prompt_file == missing
    assert "agents.topic_selector.prompt_file" in str(exc_info.value)


def test_s5_existing_prompt_file_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CFG-TC-016 trace: existing prompt file accepted at S5."""
    monkeypatch.chdir(tmp_path)
    prompt_path = Path("prompts/topic_selector/v1.txt")
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("prompt body", encoding="utf-8")
    agents = _agent_draft_map(prompt_file=str(prompt_path))

    from config.validator import PromptChecker

    checker = PromptChecker()
    checker.check_all(agents)


def test_s5_prompt_file_resolved_relative_to_process_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLD-CFG-003: prompt_file paths resolve relative to process CWD."""
    monkeypatch.chdir(tmp_path)
    relative = "prompts/cwd_relative.txt"
    absolute_outside = tmp_path.parent / "outside_prompt.txt"
    absolute_outside.write_text("outside", encoding="utf-8")

    from config.validator import PromptChecker

    checker = PromptChecker()
    agents = _agent_draft_map(prompt_file=str(absolute_outside))

    with pytest.raises(ConfigPromptNotFoundError):
        checker.check_all(agents)

    cwd_prompt = Path(relative)
    cwd_prompt.parent.mkdir(parents=True)
    cwd_prompt.write_text("inside cwd", encoding="utf-8")
    checker.check_all(_agent_draft_map(prompt_file=relative))
