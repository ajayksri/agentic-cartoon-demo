"""Unit tests for CFG-004 — ConfigParser (S1a)."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.errors import ConfigLoadError
from config.parser import ConfigParser


def test_valid_yaml_mapping_parses_to_raw_tree(tmp_path: Path) -> None:
    """Valid YAML mapping file parses to RawConfigTree (dict[str, object])."""
    config_file = tmp_path / "valid.yaml"
    config_file.write_text(
        "infrastructure:\n  postgres:\n    host: localhost\n",
        encoding="utf-8",
    )

    parser = ConfigParser()
    tree = parser.parse_file(config_file)

    assert isinstance(tree, dict)
    assert "infrastructure" in tree
    assert isinstance(tree["infrastructure"], dict)


def test_corrupt_yaml_raises_config_load_error(tmp_path: Path) -> None:
    """CFG-TC-021: corrupt YAML syntax raises ConfigLoadError with code CFG_LOAD."""
    config_file = tmp_path / "corrupt.yaml"
    config_file.write_text("infrastructure:\n  - [unclosed\n", encoding="utf-8")

    parser = ConfigParser()

    with pytest.raises(ConfigLoadError) as exc_info:
        parser.parse_file(config_file)

    assert exc_info.value.code == "CFG_LOAD"


def test_list_root_raises_config_load_error(tmp_path: Path) -> None:
    """Non-dict YAML root (list) raises ConfigLoadError with code CFG_LOAD."""
    config_file = tmp_path / "list_root.yaml"
    config_file.write_text("- item\n- item2\n", encoding="utf-8")

    parser = ConfigParser()

    with pytest.raises(ConfigLoadError) as exc_info:
        parser.parse_file(config_file)

    assert exc_info.value.code == "CFG_LOAD"


def test_empty_file_raises_config_load_error(tmp_path: Path) -> None:
    """Empty YAML file (null root) raises ConfigLoadError — root must be a mapping."""
    config_file = tmp_path / "empty.yaml"
    config_file.write_text("", encoding="utf-8")

    parser = ConfigParser()

    with pytest.raises(ConfigLoadError) as exc_info:
        parser.parse_file(config_file)

    assert exc_info.value.code == "CFG_LOAD"


def test_invalid_utf8_raises_config_load_error(tmp_path: Path) -> None:
    """Invalid UTF-8 byte sequence raises ConfigLoadError with code CFG_LOAD."""
    config_file = tmp_path / "invalid_utf8.yaml"
    config_file.write_bytes(b"infrastructure:\n  host: \xff\xfe\n")

    parser = ConfigParser()

    with pytest.raises(ConfigLoadError) as exc_info:
        parser.parse_file(config_file)

    assert exc_info.value.code == "CFG_LOAD"


def test_unreadable_path_raises_config_load_error(tmp_path: Path) -> None:
    """OSError on read (e.g. directory passed as file) raises ConfigLoadError."""
    parser = ConfigParser()

    with pytest.raises(ConfigLoadError) as exc_info:
        parser.parse_file(tmp_path)

    assert exc_info.value.code == "CFG_LOAD"


def test_parser_performs_no_semantic_validation(tmp_path: Path) -> None:
    """Parser returns raw tree without rejecting semantically invalid placeholder values."""
    config_file = tmp_path / "semantic.yaml"
    config_file.write_text(
        "collection:\n  candidate_count: not-a-number\n",
        encoding="utf-8",
    )

    parser = ConfigParser()
    tree = parser.parse_file(config_file)

    assert tree["collection"] == {"candidate_count": "not-a-number"}
