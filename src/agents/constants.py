"""Internal resource limits, template variables, and telemetry logical names."""

from __future__ import annotations

# Resource limits (HLD §7)
PROMPT_FILE_MAX_BYTES = 262_144
RESPONSE_CONTENT_MAX_BYTES = 1_048_576
MAX_TOPIC_CANDIDATES = 100
MAX_JSON_DEPTH = 32
CRITIC_ISSUE_DESCRIPTION_MAX = 2000

# Prompt version (CG-AGT-004)
PROMPT_VERSION_HEX_LENGTH = 12

# Mustache template variable names (CG-AGT-009)
TOPIC_TEMPLATE_VARS: frozenset[str] = frozenset({"candidates_json"})
SCENARIO_TEMPLATE_VARS: frozenset[str] = frozenset(
    {"selected_topic", "why_interesting", "cartoon_angle"},
)
CRITIC_TEMPLATE_VARS: frozenset[str] = frozenset({"scenario_json", "revision_number"})

# Panel bounds (CG-AGT-006)
SCENARIO_PANEL_MIN = 3
SCENARIO_PANEL_MAX = 4

# Score bounds (CG-AGT-001)
SCORE_MIN = 0.0
SCORE_MAX = 1.0

# Telemetry logical metric names (HLD §11.2)
METRIC_VALIDATION_TOTAL = "agent_validation_total"
METRIC_CRITIC_VERDICT_TOTAL = "critic_verdict_total"
METRIC_TOPIC_OUTCOME_TOTAL = "topic_selection_outcome_total"

# Span / log event names (HLD §11)
SPAN_AGENT_RUN = "agent.run"
LOG_RUN_COMPLETED = "agent_run_completed"
LOG_CRITIC_VERDICT = "critic_verdict"
LOG_VALIDATION_FAILED = "agent_validation_failed"

# GenerateRequest V1 defaults (CG-AGT-HLD-002)
DEFAULT_TEMPERATURE: float | None = None
DEFAULT_MAX_OUTPUT_TOKENS: int | None = None
