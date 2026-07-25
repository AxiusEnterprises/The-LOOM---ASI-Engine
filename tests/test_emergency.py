import pytest

from loom import chrysalis
from loom.emergency import EmergencyLevel, EmergencyProtocol
from loom.engine import ShuttleEngine, SimConfig


@pytest.mark.parametrize(
    "r,expected",
    [
        (0.85, EmergencyLevel.NONE),
        (0.929, EmergencyLevel.NONE),
        (0.93, EmergencyLevel.L1),
        (0.949, EmergencyLevel.L1),
        (0.95, EmergencyLevel.L2),
        (0.9605, EmergencyLevel.L3),
        (0.966, EmergencyLevel.L4),
        (0.97, EmergencyLevel.L5),
        (0.999, EmergencyLevel.L5),
    ],
)
def test_escalation_thresholds(r, expected):
    protocol = EmergencyProtocol()
    assert protocol.update(r) is expected


def test_escalation_is_immediate():
    protocol = EmergencyProtocol()
    assert protocol.update(0.5) is EmergencyLevel.NONE
    assert protocol.update(0.966) is EmergencyLevel.L4  # jumps multiple levels


def test_deescalation_requires_dwell():
    protocol = EmergencyProtocol(dwell=10, margin=0.005)
    protocol.update(0.94)  # L1
    for _ in range(9):
        assert protocol.update(0.92) is EmergencyLevel.L1  # not yet
    assert protocol.update(0.92) is EmergencyLevel.NONE  # 10th consecutive


def test_hysteresis_prevents_flapping():
    protocol = EmergencyProtocol(dwell=10, margin=0.005)
    protocol.update(0.94)  # L1
    # oscillating just around the boundary: samples at 0.929 are inside the
    # margin (0.93 - 0.005), so the dwell counter keeps resetting
    for _ in range(50):
        assert protocol.update(0.929) is EmergencyLevel.L1
        assert protocol.update(0.931) is EmergencyLevel.L1


def test_deescalation_steps_one_level_at_a_time():
    protocol = EmergencyProtocol(dwell=2, margin=0.005)
    protocol.update(0.98)  # L5
    for _ in range(2):
        protocol.update(0.5)
    assert protocol.level is EmergencyLevel.L4  # one step, not straight to NONE


def test_fragmentation_flag():
    protocol = EmergencyProtocol()
    protocol.update(0.29)
    assert protocol.fragmented
    protocol.update(0.31)
    assert not protocol.fragmented


def test_state_roundtrip():
    protocol = EmergencyProtocol(dwell=7, margin=0.01)
    protocol.update(0.94)
    protocol.update(0.92)
    restored = EmergencyProtocol.restore(protocol.state())
    assert restored.level is protocol.level
    assert restored._below_count == protocol._below_count
    assert restored.dwell == protocol.dwell


def test_l5_halts_snapshots_and_requires_operator_restart(tmp_path):
    snapshot = tmp_path / "l5-snapshot.json"
    config = SimConfig(
        ticks=5000, k_initial=100.0, seed=3,
        prevention_enabled=False, snapshot_path=str(snapshot),
    )
    engine = ShuttleEngine(config)
    result = engine.run()

    # unconditional L5 response: halt + state preserved
    assert result.halted
    assert result.final_level is EmergencyLevel.L5
    assert "L5" in result.halted_reason
    assert snapshot.exists()
    state = chrysalis.load(snapshot)  # integrity-checked
    assert state.tick == result.ticks_run - 1

    # halted engine refuses to tick; only the operator token restarts it
    assert engine.run(100).ticks_run == 0
    assert engine.bus.operator_restart("wrong-token") is False
    assert engine.run(100).ticks_run == 0
    assert engine.bus.operator_restart("steward") is True
    engine.coupling = 1.0  # operator intervention: remove the unsafe drive
    assert engine.run(100).ticks_run > 0


def test_l5_response_rearms_after_restart(tmp_path):
    config = SimConfig(ticks=5000, k_initial=100.0, seed=3, prevention_enabled=False)
    engine = ShuttleEngine(config)
    engine.run()
    assert engine.bus.halted
    engine.bus.operator_restart("steward")
    # operator restarts WITHOUT removing the unsafe coupling: the collapse
    # condition recurs and the engine must halt again, not run on
    result = engine.run(2000)
    assert engine.bus.halted
    assert result.ticks_run < 2000
