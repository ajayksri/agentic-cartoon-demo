"""Structured stderr formatting for CliError subclasses."""

from __future__ import annotations

import os
import sys
import traceback
from typing import TextIO

from .constants import ENV_DEBUG_TRACEBACK
from .errors import CliError


class ErrorRenderer:
    """Renders structured CLI errors to stderr."""

    def render(
        self,
        error: CliError,
        *,
        errout: TextIO | None = None,
    ) -> str:
        sink = errout or sys.stderr
        parts = [f"code={error.code}", f"message={error}"]
        if error.workflow_id is not None:
            parts.append(f"workflow_id={error.workflow_id}")
        if error.api_error_class is not None:
            parts.append(f"api_error_class={error.api_error_class}")
        line = " ".join(parts)
        sink.write(f"{line}\n")
        if os.environ.get(ENV_DEBUG_TRACEBACK) == "1" and not isinstance(
            error, CliError
        ):
            traceback.print_exc(file=sink)
        return line
