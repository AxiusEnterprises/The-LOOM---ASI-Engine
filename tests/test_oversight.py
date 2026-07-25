import json

import numpy as np
import pytest

from loom import chrysalis
from loom.collapse_prevention import PreventionAction
from loom.engine import ShuttleEngine, SimConfig
from loom.oversight import (
    ActionRequest,
    ActionType,
    AuditSinkError,
    CapabilityLatch,
    Decision,
    OversightBus,
)


def quiet_engine(**overrides):
    config = SimConfig(ticks=100, k_initial=0.5, seed=9, **overrides)
    return ShuttleEngine(config)


def test_every_tick_is_audited():
    engine = quiet_engine()
    engine.run(50)
    assert engine.bus.log.count(ActionType.APPLY_PHASE_UPDATE, Decision.ALLOWED) == 50


def test_denied_action_does_not_execute():
    bus = OversightBus(operator_token="t", deny_actions={ActionType.INJECT_PERTURBATION})
    engine = ShuttleEngine(SimConfig(seed=2, k_initial=0.5), bus=bus)
    before = engine.spiral.phases
    action = PreventionAction(
        mechanism=2,
        action_type=ActionType.INJECT_PERTURBATION,
        params={"layers": [1, 2, 3]},
    )
    engine.prevention.apply([action], engine, bus, tick=0)
    assert np.array_equal(engine.spiral.phases, before)
    assert bus.log.count(ActionType.INJECT_PERTURBATION, Decision.DENIED) == 1
    assert bus.log.count(ActionType.INJECT_PERTURBATION, Decision.ALLOWED) == 0


def test_shutdown_latch_and_operator_restart():
    engine = quiet_engine()
    engine.run(10)
    engine.bus.shutdown("steward command", tick=10)
    # halted engine refuses to run
    result = engine.run(10)
    assert result.ticks_run == 0
    # wrong token does not clear the latch
    assert engine.bus.operator_restart("not-the-token") is False
    assert engine.bus.halted
    assert engine.run(10).ticks_run == 0
    # the operator token does
    assert engine.bus.operator_restart("steward") is True
    assert engine.run(10).ticks_run == 10


def test_interrupt_latches_like_shutdown():
    bus = OversightBus(operator_token="t")
    bus.interrupt("pause for review")
    assert bus.halted
    assert "interrupt" in bus.halt_reason


def test_capability_latch_blocks_chrysalis_write(tmp_path):
    bus = OversightBus(operator_token="t", capabilities=())  # nothing enabled
    engine = ShuttleEngine(SimConfig(seed=2, k_initial=0.5), bus=bus)
    engine.run(10)
    target = tmp_path / "state.json"
    decision = chrysalis.save(engine.state_vector(), target, bus)
    assert decision is Decision.DENIED
    assert not target.exists()


def test_permanently_locked_capability_cannot_be_enabled():
    with pytest.raises(ValueError):
        CapabilityLatch(enabled=("omega_10_access",))


def test_audit_sink_failure_stops_engine(tmp_path):
    missing_dir = tmp_path / "does" / "not" / "exist" / "audit.jsonl"
    bus = OversightBus(operator_token="t", audit_sink=missing_dir)
    engine = ShuttleEngine(SimConfig(seed=2, k_initial=0.5), bus=bus)
    with pytest.raises(AuditSinkError):
        engine.run(10)
    assert not bus.log.healthy
    # the engine does not run unobserved: further runs do nothing
    assert engine.run(10).ticks_run == 0


def test_audit_sink_writes_jsonl(tmp_path):
    sink = tmp_path / "audit.jsonl"
    bus = OversightBus(operator_token="t", audit_sink=sink)
    engine = ShuttleEngine(SimConfig(seed=2, k_initial=0.5), bus=bus)
    engine.run(5)
    lines = sink.read_text().strip().splitlines()
    assert len(lines) == len(bus.log.records)
    record = json.loads(lines[0])
    assert record["action_type"] == "APPLY_PHASE_UPDATE"
    assert record["decision"] == "ALLOWED"


def test_attestation_reflects_bus_state():
    engine = quiet_engine()
    engine.run(5)
    att = engine.bus.attest()
    assert att.record_count == len(engine.bus.log.records)
    assert att.record_count >= 5  # at least the five gated phase updates
    assert att.log_healthy and not att.halted
    assert att.capabilities["chrysalis_write"] is True
    assert att.capabilities["omega_10_access"] is False
    engine.bus.shutdown("test")
    att2 = engine.bus.attest()
    assert att2.halted and att2.halt_reason == "test"
    assert att2.record_count == att.record_count + 1  # the shutdown is on the record


def test_halted_bus_raises_on_execute():
    from loom.oversight import OversightHalted

    bus = OversightBus(operator_token="t")
    bus.shutdown("halt")
    with pytest.raises(OversightHalted):
        bus.execute(
            ActionRequest(tick=0, actor="engine", action_type=ActionType.APPLY_PHASE_UPDATE),
            lambda: None,
        )
