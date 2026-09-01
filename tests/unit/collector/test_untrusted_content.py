"""Pre-code test mold for COL-005 — UntrustedContentGuard (LLD §4.8)."""

from __future__ import annotations

import pytest



def test_nul_byte_in_title_is_unsafe() -> None:
    """NUL byte in title triggers UNTRUSTED_CONTENT rejection path."""
    from collector.normalizer import UntrustedContentGuard

    guard = UntrustedContentGuard()

    assert guard.check("safe\x00title") is False


def test_c0_control_char_in_author_is_unsafe() -> None:
    """Disallowed C0 control characters (except tab/lf/cr) are unsafe."""
    from collector.normalizer import UntrustedContentGuard

    guard = UntrustedContentGuard()

    assert guard.check("author\x0bname") is False


def test_allowed_whitespace_controls_are_safe() -> None:
    """TAB, LF, CR are permitted in string fields."""
    from collector.normalizer import UntrustedContentGuard

    guard = UntrustedContentGuard()

    assert guard.check("line\tone\nline\rtwo") is True


def test_script_like_strings_are_safe_as_plain_text() -> None:
    """Script-like content without control chars passes guard (COL-TC-014)."""
    from collector.normalizer import UntrustedContentGuard

    guard = UntrustedContentGuard()

    assert guard.check("<script>alert(1)</script>", "javascript:alert(1)") is True
