"""YAML configuration file parser (S1a)."""

from __future__ import annotations

from pathlib import Path

import yaml

from config.draft import RawConfigTree
from config.errors import ConfigLoadError


class ConfigParser:
    """Reads UTF-8 YAML configuration files into a raw tree."""

    def parse_file(self, path: Path) -> RawConfigTree:
        """Read UTF-8 file; yaml.safe_load into dict.

        Raises ConfigLoadError on OSError, UnicodeDecodeError, yaml.YAMLError,
        or when root is not a mapping.
        """
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ConfigLoadError(str(exc)) from exc

        try:
            root = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigLoadError(str(exc)) from exc

        if not isinstance(root, dict):
            type_name = type(root).__name__
            raise ConfigLoadError(
                f"Configuration root must be a mapping, got {type_name}"
            )

        return root
