"""Strip optional markdown code fences before JSON parsing (CG-AGT-HLD-004)."""

# GUARDRAIL: Output — normalize provider text to parseable JSON; reject prose-only responses.

from __future__ import annotations


def extract_json_payload(content: str) -> str:
    """Return JSON text with optional markdown fences removed."""
    text = content.strip()
    if not text.startswith("```"):
        return text

    remainder = text[3:]
    newline_idx = remainder.find("\n")
    if newline_idx == -1:
        return remainder.strip()

    inner = remainder[newline_idx + 1 :]
    close_idx = inner.find("```")
    if close_idx != -1:
        inner = inner[:close_idx]
    return inner.strip()
