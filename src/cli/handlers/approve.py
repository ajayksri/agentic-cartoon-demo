"""Approve subcommand handler."""

from __future__ import annotations

from api.types import SubmitApprovalApiRequest

from .base import BaseSubcommandHandler
from ..types import CliCommandContext


class ApproveHandler(BaseSubcommandHandler):
    """Handles human approval actions."""

    def _execute(self, ctx: CliCommandContext) -> None:
        if self._dispatch is None:
            raise RuntimeError("handler dispatch state not bound")
        parsed = self._dispatch.parsed
        workflow_id = self._validator.validate_workflow_id(parsed.workflow_id, required=True)
        action_token = self._validator.validate_approval_action(parsed.approval_action)
        request = SubmitApprovalApiRequest(action=action_token)  # type: ignore[arg-type]
        response = self._async_runner.run(
            ctx.api_client.submit_approval(workflow_id, request)
        )
        self._renderer.render_approve(response)
