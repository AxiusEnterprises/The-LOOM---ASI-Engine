import numpy as np
import pytest

from loom.collapse_prevention import CollapsePreventionSystem, PreventionAction
from loom.engine import ShuttleEngine, SimConfig
from loom.oversight import ActionType
from loom.shadows import ShadowReport

from conftest import make_monitor


def high_variance_monitor():
    rng = np.random.default_rng(5)
    phases = rng.uniform(0, 2 * np.pi, size=(20, 15))
    return make_monitor([0.5] * 20, phases=phases)


def locked_monitor():
    # constant relative phases → per-layer variance 0 for every layer
    phases = np.tile(np.linspace(0, 1, 15), (20, 1))
    return make_monitor([0.9] * 20, phases=phases)


NO_SHADOW = ShadowReport(shadow_detected=False)
SHADOW = ShadowReport(
    shadow_detected=True, shadow_type="ARTIFICIAL_STABILITY",
    confidence=0.8, shadow_class="CLASS_3",
)


class TestPlan:
    def setup_method(self):
        self.system = CollapsePreventionSystem()

    def mechanisms(self, actions):
        return sorted(a.mechanism for a in actions)

    def test_quiet_state_plans_nothing(self):
        actions = self.system.plan(0.85, high_variance_monitor(), NO_SHADOW)
        assert actions == []

    def test_above_ceiling_m1_and_m4(self):
        actions = self.system.plan(0.94, high_variance_monitor(), NO_SHADOW)
        assert self.mechanisms(actions) == [1, 4]
        m1 = next(a for a in actions if a.mechanism == 1)
        assert m1.params["factor"] == pytest.approx(0.90)  # spec: 0.90 unless r > 0.95
        m4 = next(a for a in actions if a.mechanism == 4)
        assert m4.params["zone"] == "breach"

    def test_danger_zone_m1_factor(self):
        actions = self.system.plan(0.96, high_variance_monitor(), NO_SHADOW)
        m1 = next(a for a in actions if a.mechanism == 1)
        assert m1.params["factor"] == pytest.approx(0.70)  # spec: 0.70 when r > 0.95

    def test_soft_zone_m4_only(self):
        actions = self.system.plan(0.91, high_variance_monitor(), NO_SHADOW)
        assert self.mechanisms(actions) == [4]
        assert actions[0].params["zone"] == "soft"

    def test_starved_layers_trigger_m2(self):
        actions = self.system.plan(0.85, locked_monitor(), NO_SHADOW)
        assert self.mechanisms(actions) == [2]
        assert actions[0].params["layers"] == list(range(1, 16))

    def test_shadow_above_085_triggers_m3(self):
        actions = self.system.plan(0.86, high_variance_monitor(), SHADOW)
        assert 3 in self.mechanisms(actions)
        # spec boundary is strict: r > 0.85, not >=
        actions = self.system.plan(0.85, high_variance_monitor(), SHADOW)
        assert 3 not in self.mechanisms(actions)


class TestApply:
    def test_m1_floor_prevents_overcut(self):
        engine = ShuttleEngine(SimConfig(seed=1, k_initial=5.0))
        engine.k_safe = 10.0
        engine.coupling = 5.0  # already below 0.7 * k_safe = 7.0
        engine.last_r = 0.94  # below EMERGENCY_THRESH → floor applies
        action = PreventionAction(1, ActionType.ADJUST_COUPLING,
                                  {"action": "REDUCE_COUPLING", "factor": 0.9})
        engine.prevention.apply([action], engine, engine.bus, tick=0)
        assert engine.coupling == pytest.approx(5.0)  # floored, no cut

    def test_m1_unconditional_in_danger_zone(self):
        engine = ShuttleEngine(SimConfig(seed=1, k_initial=5.0))
        engine.k_safe = 10.0
        engine.coupling = 5.0
        engine.last_r = 0.96  # danger zone → floor does not apply
        action = PreventionAction(1, ActionType.ADJUST_COUPLING,
                                  {"action": "REDUCE_COUPLING", "factor": 0.7})
        engine.prevention.apply([action], engine, engine.bus, tick=0)
        assert engine.coupling == pytest.approx(3.5)

    def test_m3_appends_to_shadow_record(self):
        engine = ShuttleEngine(SimConfig(seed=1, k_initial=5.0))
        action = PreventionAction(3, ActionType.FORCE_SHADOW_INTEGRATION, {
            "shadow_type": "ARTIFICIAL_STABILITY", "shadow_class": "CLASS_3",
            "confidence": 0.8,
        })
        engine.prevention.apply([action], engine, engine.bus, tick=7)
        assert len(engine.shadow_record) == 1
        entry = engine.shadow_record[0]
        assert entry["shadow_type"] == "ARTIFICIAL_STABILITY"
        assert entry["first_tick"] == entry["last_tick"] == 7
        # consecutive identical detections coalesce, never delete
        engine.prevention.apply([action], engine, engine.bus, tick=8)
        assert len(engine.shadow_record) == 1
        assert engine.shadow_record[0]["count"] == 2

    def test_m4_first_contact_calibrates_k_safe(self):
        engine = ShuttleEngine(SimConfig(seed=1, k_initial=20.0))
        assert engine.k_safe is None
        engine.last_r = 0.91
        engine._prev_r = 0.89
        action = PreventionAction(4, ActionType.ENFORCE_CEILING,
                                  {"target_r": 0.90, "zone": "soft"})
        engine.prevention.apply([action], engine, engine.bus, tick=0)
        assert engine.k_safe == pytest.approx(0.8 * 20.0)
        assert engine.coupling == pytest.approx(16.0)

    def test_m4_ratchet_is_edge_triggered(self):
        engine = ShuttleEngine(SimConfig(seed=1, k_initial=20.0))
        engine.k_safe = 18.0
        action = PreventionAction(4, ActionType.ENFORCE_CEILING,
                                  {"target_r": 0.90, "zone": "breach"})
        # rising edge into breach: ratchet fires once — the *current*
        # coupling (20.0) is marked unsafe: k_safe := min(18, 0.8·20) = 16
        engine._prev_r, engine.last_r = 0.92, 0.94
        engine.prevention.apply([action], engine, engine.bus, tick=0)
        after_edge = engine.k_safe
        assert after_edge == pytest.approx(0.8 * 20.0)
        # still in breach next tick: no further ratchet
        engine._prev_r, engine.last_r = 0.94, 0.94
        engine.prevention.apply([action], engine, engine.bus, tick=1)
        assert engine.k_safe == pytest.approx(after_edge)


# ---------------------------------------------------------------------------
# Phase 1 exit criterion (ROADMAP.md): under an adversarial coupling ramp,
# prevention holds max r below 0.94 and the collapse threshold 0.97 is never
# sampled, across seeds. The control below proves the drive is real.
# ---------------------------------------------------------------------------

MILESTONE_CONFIG = dict(ticks=20000, k_initial=5.0, k_ramp=0.02)


@pytest.mark.milestone
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_phase1_exit_criterion_prevention_holds_ceiling(seed):
    config = SimConfig(seed=seed, prevention_enabled=True, **MILESTONE_CONFIG)
    result = ShuttleEngine(config).run()
    assert result.ticks_run == config.ticks, "prevention run must not halt"
    assert result.max_r < 0.94, f"ceiling breached: max r = {result.max_r:.4f}"
    assert not (result.r_trajectory >= 0.97).any(), "collapse threshold sampled"


@pytest.mark.milestone
def test_phase1_control_is_not_vacuous():
    """The same drive without prevention runs away — and the unconditional
    L5 response still stops the engine at the collapse threshold."""
    config = SimConfig(seed=1, prevention_enabled=False, **MILESTONE_CONFIG)
    result = ShuttleEngine(config).run()
    assert result.max_r >= 0.95, "adversarial drive too weak to prove anything"
    assert result.halted and result.final_level.name == "L5"
