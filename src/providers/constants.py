"""Internal constants for the providers module."""

from __future__ import annotations

from config.types import InjectionId

FINJ_PROVIDER_ORDER: tuple[InjectionId, ...] = (
    InjectionId.FINJ_PRV_TIMEOUT,
    InjectionId.FINJ_PRV_RATE,
    InjectionId.FINJ_PRV_ERROR,
    InjectionId.FINJ_PRV_INVALID,
)

METRIC_CALL_DURATION_MS = "provider_call_duration_ms"
METRIC_TOKENS_TOTAL = "provider_tokens_total"
METRIC_ERRORS_TOTAL = "provider_errors_total"

SPAN_GENERATE = "provider.generate"
LOG_CALL_COMPLETED = "provider_call_completed"
LOG_CALL_FAILED = "provider_call_failed"
SPAN_EVENT_STARTED = "call_started"
SPAN_EVENT_COMPLETED = "call_completed"
SPAN_EVENT_FAILED = "call_failed"

VENDOR_DETAIL_MAX_LENGTH = 200

FAKE_DEFAULT_CONTENT = "fake completion"
FAKE_MIN_LATENCY_MS = 1.0

# Deterministic schema-valid stubs for demo / subprocess E2E (PD-001 / INT-006).
FAKE_AGENT_TOPIC_DEFAULT = (
    '{"outcome":"topic_selected","selected_topic":"Rust async patterns",'
    '"why_interesting":"Developers debate memory safety versus async ergonomics daily",'
    '"cartoon_angle":"Two crabs fighting over a shell labeled borrow checker",'
    '"scores":{"technical_relevance":0.85,"developer_relevance":0.9,'
    '"discussion_interest":0.75,"humour_potential":0.8,"irony_contradiction":0.6,'
    '"visual_scenario_potential":0.85,"background_knowledge_required":0.4},'
    '"alternatives":[{"topic":"Go generics","rationale":"Also topical but less visual"}]}'
)
FAKE_AGENT_SCENARIO_DEFAULT = (
    '{"topic":"Rust async patterns","premise":"Two developers argue about async runtime choices",'
    '"characters":["Alice","Bob"],'
    '"panels":[{"scene":"Office desk","dialogue":"Async is too hard!"},'
    '{"scene":"Office desk","dialogue":"Just use await everywhere!"},'
    '{"scene":"Office desk","dialogue":"That blocks the executor!"}],'
    '"punchline":"They both ship blocking I/O anyway."}'
)
FAKE_AGENT_CRITIC_PASS_DEFAULT = '{"status":"PASS","issues":[],"suggested_changes":[]}'

MIN_RATE_LIMIT_PER_MINUTE = 1
