"""History subcommand handler."""

from __future__ import annotations

from .base import BaseSubcommandHandler
from ..types import CliCommandContext


class HistoryHandler(BaseSubcommandHandler):
    """Handles workflow history queries."""

    def _execute(self, ctx: CliCommandContext) -> None:
        if self._dispatch is None:
            raise RuntimeError("handler dispatch state not bound")
        workflow_id = self._validator.validate_workflow_id(
            self._dispatch.parsed.workflow_id,
            required=True,
        )
        response = self._async_runner.run(
            ctx.api_client.get_workflow_history(workflow_id)
        )
        self._renderer.render_history(response)
