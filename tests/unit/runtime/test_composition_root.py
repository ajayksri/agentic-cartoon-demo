"""Unit tests for RT-015 — DefaultCompositionRoot (LLD §8)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from runtime import API_ENTRY, COORDINATOR_ENTRY, WORKER_ENTRY, UnsupportedProcessKindError

from tests.unit.runtime.helpers import minimal_runtime_config


def test_create_composition_root_loads_config_once() -> None:
    """RT-TC-006: load_config invoked exactly once at root creation."""
    from runtime.composition import create_composition_root

    with patch(
        "runtime.composition.load_config",
        return_value=minimal_runtime_config(),
    ) as load_config:
        root = create_composition_root()
        with patch("runtime.composition.SharedBootstrap") as shared:
            shared.return_value.wire_common.return_value = MagicMock()
            with patch("runtime.composition.ApiProcessWiring") as api:
                api.return_value.wire.side_effect = lambda ctx: ctx
                root.bootstrap(API_ENTRY)

    assert load_config.call_count == 1


def test_bootstrap_for_tests_injects_fakes() -> None:
    """LLD §21.3: _bootstrap_for_tests returns wired dependencies with injectable fakes."""
    from runtime.composition import _bootstrap_for_tests

    fake_queue = MagicMock()
    wired = _bootstrap_for_tests(
        entry=API_ENTRY,
        config=minimal_runtime_config(),
        task_queue=fake_queue,
    )

    assert wired.task_queue is fake_queue
    assert wired.entry.kind == API_ENTRY.kind


def test_unsupported_process_kind_raises() -> None:
    """RT-TC-013: invalid ProcessKind raises UnsupportedProcessKindError."""
    from types import SimpleNamespace

    from runtime.composition import DefaultCompositionRoot

    root = DefaultCompositionRoot(minimal_runtime_config())
    invalid = SimpleNamespace(kind="invalid-kind", service_name="bad")

    with patch("runtime.composition.SharedBootstrap") as shared:
        shared.return_value.wire_common.return_value = MagicMock()
        with pytest.raises(UnsupportedProcessKindError):
            root.bootstrap(invalid)  # type: ignore[arg-type]


def test_rebootstrap_tears_down_prior_context() -> None:
    """MOD-RT-INV-010: second bootstrap closes prior redis/persistence handles."""
    from runtime.composition import DefaultCompositionRoot

    root = DefaultCompositionRoot(minimal_runtime_config())
    teardown = MagicMock()
    root._teardown_partial = teardown  # type: ignore[method-assign]

    with patch("runtime.composition.SharedBootstrap") as shared:
        ctx = MagicMock()
        shared.return_value.wire_common.return_value = ctx
        with patch("runtime.composition.ApiProcessWiring") as api:
            api.return_value.wire.side_effect = lambda current: current
            with patch("runtime.composition.CoordinatorProcessWiring") as coord:
                coord.return_value.wire.side_effect = lambda current, **_kw: current
                root.bootstrap(API_ENTRY)
                root.bootstrap(COORDINATOR_ENTRY)

    teardown.assert_called_once()


def test_three_entry_kinds_bootstrap_independently() -> None:
    """RT-TC-004 unit seam: api/coordinator/worker bootstrap without cross-kind dependency."""
    from runtime.composition import DefaultCompositionRoot

    for entry in (API_ENTRY, COORDINATOR_ENTRY, WORKER_ENTRY):
        fresh = DefaultCompositionRoot(minimal_runtime_config())
        with patch("runtime.composition.SharedBootstrap") as shared:
            ctx = MagicMock()
            shared.return_value.wire_common.return_value = ctx
            with patch("runtime.composition.ApiProcessWiring") as api:
                api.return_value.wire.side_effect = lambda current: current
                with patch("runtime.composition.CoordinatorProcessWiring") as coord:
                    coord.return_value.wire.side_effect = lambda current, **_kw: current
                    with patch("runtime.composition.WorkerProcessWiring") as worker:
                        worker.return_value.wire.side_effect = lambda current, **_kw: current
                        result = fresh.bootstrap(entry)
        assert result.entry.kind == entry.kind
