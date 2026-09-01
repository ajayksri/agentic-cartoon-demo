"""Initiate subcommand handler."""

from __future__ import annotations

from .base import BaseSubcommandHandler
from ..types import CliCommandContext


class InitiateHandler(BaseSubcommandHandler):
    """Handles workflow initiation."""

    _bootstrap_config = None

    def _execute(self, ctx: CliCommandContext) -> None:
        if self._dispatch is None:
            raise RuntimeError("handler dispatch state not bound")
        parsed = self._dispatch.parsed
        request = parsed.initiate_request
        if request is None:
            raise RuntimeError("initiate request missing from parse result")
        if self._dispatch.initiate_bootstrap is not None:
            self._bootstrap_config = self._dispatch.initiate_bootstrap.effective_config
        response = self._async_runner.run(ctx.api_client.initiate_workflow(request))
        self._renderer.render_initiate(response)
