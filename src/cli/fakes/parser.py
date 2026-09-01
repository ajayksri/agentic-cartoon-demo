"""Fake argument parser for handler tests."""

from __future__ import annotations

from collections.abc import Sequence

from cli.parser import ParsedCliInvocation


class FakeArgumentParser:
    """Returns a predetermined parse result without argv parsing."""

    def __init__(self, parsed: ParsedCliInvocation) -> None:
        self._parsed = parsed

    def parse(self, argv: Sequence[str]) -> ParsedCliInvocation:
        _ = argv
        return self._parsed
