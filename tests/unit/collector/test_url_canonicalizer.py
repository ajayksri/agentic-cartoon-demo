"""Pre-code test mold for COL-005 — UrlCanonicalizer (HLD §10.3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "collector"
_VECTORS = json.loads((_FIXTURES / "url_vectors.json").read_text(encoding="utf-8"))["pairs"]


@pytest.mark.parametrize("vector", _VECTORS, ids=[f"pair-{v['id']}" for v in _VECTORS])
def test_url_canonicalizer_vectors(vector: dict[str, object]) -> None:
    """All eight HLD §10.3 URL equivalence pairs canonicalize deterministically."""
    from collector.normalizer import UrlCanonicalizationError, UrlCanonicalizer

    canonicalizer = UrlCanonicalizer()
    raw_input = str(vector["input"])

    if vector.get("reject"):
        with pytest.raises(UrlCanonicalizationError):
            canonicalizer.canonicalize(raw_input)
        return

    assert canonicalizer.canonicalize(raw_input) == str(vector["expected"])


def test_canonicalize_optional_none_passthrough() -> None:
    """None input to canonicalize_optional returns None."""
    from collector.normalizer import UrlCanonicalizer

    canonicalizer = UrlCanonicalizer()

    assert canonicalizer.canonicalize_optional(None) is None


def test_canonicalize_optional_empty_after_trim_returns_none() -> None:
    """Whitespace-only URL becomes None via canonicalize_optional."""
    from collector.normalizer import UrlCanonicalizer

    canonicalizer = UrlCanonicalizer()

    assert canonicalizer.canonicalize_optional("   ") is None
