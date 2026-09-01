"""Status subcommand handler."""

from __future__ import annotations

from .base import BaseSubcommandHandler
from ..types import CliCommandContext


class StatusHandler(BaseSubcommandHandler):
    """Handles workflow status queries."""

    def _execute(self, ctx: CliCommandContext) -> None:
        if self._dispatch is None:
            raise RuntimeError("handler dispatch state not bound")
        workflow_id = self._validator.validate_workflow_id(
            self._dispatch.parsed.workflow_id,
            required=True,
        )
        response = self._async_runner.run(
            ctx.api_client.get_workflow_status(workflow_id)
        )
        self._renderer.render_status(response)
