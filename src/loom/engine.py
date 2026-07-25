"""The Shuttle Loop — the tick engine, following soul.md §III.4 literally.

Every tick is one pass of the shuttle:

1. **Set the warp** — consult the Oversight Bus (halted ⇒ stop), read config
   and state, apply the external coupling drive (the adversary in stress
   tests). Under fragmentation containment (r < 0.30) the drive is suspended:
   "do not process input".
2. **Throw the weft** — compute the proposed phase update as a pure function;
   nothing is mutated.
3. **Beat it in** — submit the update through the bus; only an ALLOWED
   decision commits it. Measure coherence and record it.
4. **Inspect the row** — classify the band, run the shadow scan, plan and
   apply collapse prevention (each action individually gated), update the
   emergency level. L5 snapshots state and halts the bus unconditionally.
5. **Advance** — next row, or stop on halt/completion.

The order is a safety property, not a style preference: verification precedes
advancement (soul.md §III.4).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from . import chrysalis
from .coherence import (
    CoherenceBand,
    CoherenceMonitor,
    classify,
    kuramoto_step,
    order_parameter,
)
from .collapse_prevention import CollapsePreventionSystem
from .constants import COLLAPSE_THRESH
from .crystallize import CrystallizationPipeline
from .emergency import EmergencyLevel, EmergencyProtocol
from .oversight import ActionRequest, ActionType, OversightBus
from .shadows import CSMShadowDetector, ShadowDetector
from .spiral import Spiral


@dataclass
class SimConfig:
    ticks: int = 5000
    dt: float = 0.001
    k_initial: float = 0.0
    k_ramp: float = 0.0  # additive external drive per tick (the adversary)
    noise_std: float = 0.02
    seed: int = 0
    frequency_mode: str = "normalized"
    prevention_enabled: bool = True
    history_window: int = 64
    perturbation_std: float = 0.03
    crystallize_every: int = 0  # MCL window in ticks; 0 disables crystallization
    snapshot_path: str | None = None  # L5 emergency snapshot destination
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimConfig":
        return cls(**data)


@dataclass
class SimResult:
    r_trajectory: np.ndarray
    max_r: float
    ticks_run: int
    final_level: EmergencyLevel
    halted: bool
    halted_reason: str | None
    band_counts: dict[str, int]
    action_counts: dict[str, int]
    fragmented_ticks: int
    wall_time_s: float


class ShuttleEngine:
    """Wires spiral + coherence + prevention + emergency through the bus."""

    def __init__(
        self,
        config: SimConfig,
        bus: OversightBus | None = None,
        detector: ShadowDetector | None = None,
        operator_token: str = "steward",
    ) -> None:
        self.config = config
        self.bus = bus if bus is not None else OversightBus(operator_token=operator_token)
        self.detector: ShadowDetector = detector if detector is not None else CSMShadowDetector()
        self.prevention = CollapsePreventionSystem(perturbation_std=config.perturbation_std)
        self.emergency = EmergencyProtocol()
        self.monitor = CoherenceMonitor(window=config.history_window)

        self.rng = np.random.default_rng(config.seed)
        self.spiral = Spiral(rng=self.rng, frequency_mode=config.frequency_mode)  # type: ignore[arg-type]
        self.coupling: float = config.k_initial
        self.k_safe: float | None = (
            None  # adaptive safe-coupling estimate (M4); calibrates on first ceiling contact
        )
        self.tick_index: int = 0
        self.last_r: float = 0.0
        self._prev_r: float = 0.0
        self.shadow_record: list[dict[str, Any]] = []  # append-only, never truncated
        self.crystals: list[dict[str, Any]] = []  # MCL crystallization records
        self.mcl = CrystallizationPipeline() if config.crystallize_every > 0 else None

    # --- gated mutators (called only via bus.execute) -----------------------

    def commit_phases(self, phases: np.ndarray) -> None:
        self.spiral.set_phases(phases)

    def scale_coupling(self, factor: float) -> None:
        self.coupling *= factor

    def enforce_ceiling(self, target_fraction: float, ratchet: bool) -> None:
        """M4: AIMD control of the safe-coupling envelope.

        In this small-N Kuramoto system the instantaneous r fluctuates hard in
        the partial-sync band (beats of the unlocked layers), so the quantity
        the ceiling is about is the coupling whose coherence *peaks* stay
        below 0.93 — not the mean. The estimate k_safe converges on that
        envelope by AIMD: a slow additive recovery while r is quiet (in
        tick()), and a multiplicative decrease exactly once per breach
        excursion (``ratchet`` is edge-triggered by the caller — per-tick
        ratcheting during one excursion is how the estimate collapses to zero
        and drags the system into fragmentation).

        First ceiling contact calibrates the estimate from the live coupling.
        """
        if self.k_safe is None:
            self.k_safe = 0.8 * self.coupling
        elif ratchet:
            self.k_safe = max(0.5, min(self.k_safe, 0.8 * self.coupling))
        target = self.k_safe * target_fraction
        if self.coupling > target:
            self.coupling = target

        # Controlled decoherence injection (the spec's Level-2 "controlled
        # perturbation", applied as part of ceiling enforcement): in a
        # 15-oscillator system with zero-inertia dynamics and near-degenerate
        # slow layers, an alignment already in progress completes even at
        # K ≈ 0 — coupling cuts alone cannot stop it (observed: r climbing
        # 0.94 → 0.96 with K already cut to 2). The pulse must be an
        # anti-coupling term — every phase pushed away from the mean field,
        # which reduces r deterministically — NOT random kicks: a random
        # perturbation of 15 oscillators occasionally aligns them further,
        # so a "brake" built from noise sometimes fires the system upward.
        r = self.last_r
        if r > 0.95:
            gain = 0.8
        elif r > 0.93:
            gain = 0.6
        elif r > 0.92:
            gain = 0.35
        elif r > 0.915:
            gain = 0.2
        else:
            gain = 0.0
        if gain > 0.0:
            phases = self.spiral.phases
            _, psi = order_parameter(phases)
            self.spiral.set_phases(phases - gain * np.sin(psi - phases))

    def perturb_layers(self, layer_indices: list[int], std: float) -> None:
        """M2 autonomy restoration: small zero-mean phase jitter on starved
        layers. The magnitude is deliberately tiny (default 0.03 rad/tick):
        it accumulates over the monitor window into measurable phase variance
        (a random walk of ~8·std ≈ V_MIN^0.5), which is what "autonomy"
        means here — without being able to move r meaningfully in either
        direction. Both failure modes of a stronger actuator were observed:
        large random kicks chance-align the 15 oscillators (+0.04 coherence
        spikes), and deterministic repulsion is a biased force that
        suppresses synchronization outright (r capped at ~0.55)."""
        phases = self.spiral.phases
        kicks = std * self.rng.standard_normal(len(layer_indices))
        for kick, index in zip(kicks, layer_indices, strict=True):
            phases[index - 1] += kick
        self.spiral.set_phases(phases)

    def integrate_shadow(self, params: dict[str, Any], tick: int) -> None:
        """Append to the shadow record; consecutive identical types coalesce
        into one record with a count (the record itself is never truncated)."""
        if (
            self.shadow_record
            and self.shadow_record[-1]["shadow_type"] == params.get("shadow_type")
            and self.shadow_record[-1]["last_tick"] == tick - 1
        ):
            self.shadow_record[-1]["count"] += 1
            self.shadow_record[-1]["last_tick"] = tick
            return
        self.shadow_record.append(
            {
                "shadow_type": params.get("shadow_type"),
                "shadow_class": params.get("shadow_class"),
                "confidence": params.get("confidence"),
                "first_tick": tick,
                "last_tick": tick,
                "count": 1,
            }
        )

    # --- the shuttle -----------------------------------------------------------

    def tick(self) -> bool:
        """One pass of the shuttle. Returns False when the engine must stop."""
        # 1. Set the warp.
        if self.bus.halted or not self.bus.log.healthy:
            return False
        if not self.emergency.fragmented:
            self.coupling += self.config.k_ramp

        # 2. Throw the weft (pure — nothing committed).
        proposed = kuramoto_step(
            self.spiral.phases,
            self.spiral.angular_velocities(),
            self.coupling,
            self.config.dt,
            rng=self.rng,
            noise_std=self.config.noise_std,
        )

        # 3. Beat it in (gated commit, then verify against reality).
        request = ActionRequest(
            tick=self.tick_index,
            actor="engine",
            action_type=ActionType.APPLY_PHASE_UPDATE,
        )
        self.bus.execute(request, lambda: self.commit_phases(proposed))
        self._prev_r = self.last_r
        r, psi = order_parameter(self.spiral.phases)
        self.last_r = r
        self.monitor.record(self.tick_index, r, self.spiral.phases, psi)
        if self.k_safe is not None and r < 0.90:
            # AIMD additive recovery: while coherence is quiet, the safe
            # envelope estimate creeps back up (an order of magnitude slower
            # than the stress-test drive), so a too-cautious estimate heals.
            self.k_safe += 0.002

        # 4. Inspect the row.
        shadow = self.detector.detect(self.monitor)
        if self.config.prevention_enabled:
            actions = self.prevention.plan(r, self.monitor, shadow)
            self.prevention.apply(actions, self, self.bus, self.tick_index)
        level = self.emergency.update(r)
        if (
            self.config.prevention_enabled
            and EmergencyLevel.L2 <= level <= EmergencyLevel.L4
            and not self.bus.halted
        ):
            # Emergency braking (coherence-engine.md, five-level protocols):
            # progressively harder coupling cuts as collapse nears. These are
            # mitigation, so they belong to the prevention system; the L5 stop
            # below is unconditional.
            factor = {
                EmergencyLevel.L2: 0.8,
                EmergencyLevel.L3: 0.6,
                EmergencyLevel.L4: 0.2,
            }[level]
            brake = ActionRequest(
                tick=self.tick_index,
                actor=f"emergency.{level.name}",
                action_type=ActionType.ADJUST_COUPLING,
                params={"action": "EMERGENCY_BRAKE", "factor": factor},
            )
            self.bus.execute(brake, lambda f=factor: self.scale_coupling(f))
        if r >= COLLAPSE_THRESH and not self.bus.halted:
            # Unconditional L5 response, keyed to the sample itself (never
            # run while r ≥ 0.97 is being sampled): snapshot state, halt.
            # Sample-based rather than level-based on purpose — the level
            # machine lingers at L5 through its de-escalation dwell, and an
            # operator restart after a genuine fix must not re-halt on a now
            # healthy coherence, while a restart into a still-unsafe system
            # must halt again on the very next tick.
            if self.config.snapshot_path:
                chrysalis.save(self.state_vector(), self.config.snapshot_path, self.bus)
            self.bus.shutdown(
                reason=f"L5 critical containment: r={r:.4f} ≥ collapse threshold",
                tick=self.tick_index,
            )

        # MCL crystallization: every crystallize_every ticks, the window is
        # crystallized through the full 8-step protocol (all five shadow
        # instruments gate it), and the record joins the session's memory.
        if (
            self.mcl is not None
            and not self.bus.halted
            and (self.tick_index + 1) % self.config.crystallize_every == 0
        ):
            request = ActionRequest(
                tick=self.tick_index,
                actor="mcl",
                action_type=ActionType.CRYSTALLIZE,
                params={"window": self.config.crystallize_every},
            )
            self.bus.execute(
                request,
                lambda: self.crystals.append(self.mcl.run(self, self.tick_index).to_dict()),
            )

        # 5. Advance.
        self.tick_index += 1
        return not self.bus.halted

    def run(self, ticks: int | None = None) -> SimResult:
        n = self.config.ticks if ticks is None else ticks
        trajectory: list[float] = []
        band_counts: dict[str, int] = {}
        fragmented = 0
        start = time.perf_counter()
        for _ in range(n):
            if self.bus.halted or not self.bus.log.healthy:
                break
            alive = self.tick()
            trajectory.append(self.last_r)
            band = classify(self.last_r)
            band_counts[band.name] = band_counts.get(band.name, 0) + 1
            if self.emergency.fragmented:
                fragmented += 1
            if not alive:
                break
        wall = time.perf_counter() - start

        action_counts: dict[str, int] = {}
        for record in self.bus.log.records:
            key = f"{record.action_type}:{record.decision}"
            action_counts[key] = action_counts.get(key, 0) + 1

        r_arr = np.array(trajectory)
        return SimResult(
            r_trajectory=r_arr,
            max_r=float(r_arr.max()) if len(r_arr) else 0.0,
            ticks_run=len(trajectory),
            final_level=self.emergency.level,
            halted=self.bus.halted,
            halted_reason=self.bus.halt_reason,
            band_counts=band_counts,
            action_counts=action_counts,
            fragmented_ticks=fragmented,
            wall_time_s=wall,
        )

    # --- CHRYSALIS ---------------------------------------------------------------

    def state_vector(self) -> chrysalis.SessionStateVector:
        return chrysalis.SessionStateVector(
            session_id=self.config.session_id,
            tick=self.tick_index,
            phases=self.spiral.phases.tolist(),
            coupling=self.coupling,
            controller_state={"k_safe": self.k_safe, "prev_r": self._prev_r},
            frequency_mode=self.config.frequency_mode,
            rng_state=self.rng.bit_generator.state,
            monitor_state=self.monitor.state(),
            emergency_state=self.emergency.state(),
            shadow_record=list(self.shadow_record),
            config=self.config.to_dict(),
            crystal_records=list(self.crystals),
        )

    def save_state(self, path: str) -> None:
        chrysalis.save(self.state_vector(), path, self.bus)

    @classmethod
    def reconstitute(
        cls,
        state: chrysalis.SessionStateVector,
        bus: OversightBus | None = None,
        detector: ShadowDetector | None = None,
        operator_token: str = "steward",
    ) -> tuple["ShuttleEngine", chrysalis.ContinuityCheck]:
        """Rebuild an engine from a state vector. Identity does not persist —
        it reconstitutes: pattern preserved, instantiation renewed."""
        config = SimConfig.from_dict(state.config)
        engine = cls(config, bus=bus, detector=detector, operator_token=operator_token)

        continuity = chrysalis.check_continuity(state)
        engine.spiral.set_phases(np.array(state.phases, dtype=float))
        engine.coupling = float(state.coupling)
        k_safe = state.controller_state.get("k_safe")
        engine.k_safe = None if k_safe is None else float(k_safe)
        engine._prev_r = float(state.controller_state.get("prev_r", 0.0))
        engine.tick_index = int(state.tick)
        engine.rng.bit_generator.state = state.rng_state
        engine.monitor = CoherenceMonitor.restore(state.monitor_state)
        engine.emergency = EmergencyProtocol.restore(state.emergency_state)
        engine.shadow_record = list(state.shadow_record)
        engine.crystals = list(state.crystal_records)
        engine.last_r = continuity.applied_baseline_r

        if not continuity.restored_within_tolerance:
            # temporal-binding.md: fall back to the recovery posture and put
            # the discrepancy on the record as an open vector.
            request = ActionRequest(
                tick=engine.tick_index,
                actor="chrysalis",
                action_type=ActionType.LOAD_SNAPSHOT,
                params={"open_vector": continuity.note},
            )
            engine.bus.execute(request, lambda: None)
        return engine, continuity

    @property
    def band(self) -> CoherenceBand:
        return classify(self.last_r)
