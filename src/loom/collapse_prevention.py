"""Strange Loop Collapse Prevention — the 4-mechanism system.

Transcribed from ``specs/verath/references/coherence-engine.md``'s
``CollapsePreventionSystem``. :meth:`plan` is pure and mirrors the spec's
pseudocode decision structure; :meth:`apply` executes every planned action
through the Oversight Bus — a denied action is logged and does nothing.

Mechanisms:
1. **Coherence Modulation** — above the 0.93 ceiling, multiply coupling by
   0.90 (0.70 when r > 0.95).
2. **Layer Autonomy Preservation** — inject phase perturbation into layers
   whose windowed relative-phase variance drops below V_MIN = 0.02. (The spec
   emits one action per layer; this implementation emits a single action
   carrying the layer list, purely to keep the audit log proportional to
   decisions rather than layers.)
3. **Shadow Coherence Check** — when a shadow is detected while r > 0.85,
   force shadow integration: the finding is recorded, immediately and
   permanently, in the session's append-only shadow record.
4. **Coherence Ceiling Enforcement** — adaptive controller: the engine keeps
   a running estimate of the largest coupling that held r inside the preferred
   band (``k_safe``, updated while 0.80 ≤ r < 0.90); when r breaches the
   ceiling, M4 snaps coupling back to that known-safe level in one action
   instead of multiplying down blindly. This stops both the upward cascade
   (coupling returns to a level whose equilibrium is below the ceiling) and
   the downward overshoot into fragmentation that naive compounding cuts
   cause.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .constants import EMERGENCY_THRESH, MAX_OPERATIONAL, MAX_SUSTAINED, V_MIN
from .coherence import CoherenceMonitor
from .oversight import ActionRequest, ActionType, OversightBus
from .shadows import ShadowReport


@dataclass(frozen=True)
class PreventionAction:
    mechanism: int  # 1–4
    action_type: ActionType
    params: dict[str, Any] = field(default_factory=dict)


class CollapsePreventionSystem:
    """Plans and applies the four collapse-prevention mechanisms."""

    def __init__(self, perturbation_std: float = 0.03) -> None:
        self.perturbation_std = perturbation_std

    # --- planning (pure) -----------------------------------------------------

    def plan(
        self,
        r_current: float,
        monitor: CoherenceMonitor,
        shadow_report: ShadowReport,
    ) -> list[PreventionAction]:
        actions: list[PreventionAction] = []

        # Mechanism 1: Coherence Modulation
        if r_current > MAX_OPERATIONAL:
            reduction = 0.70 if r_current > EMERGENCY_THRESH else 0.90
            actions.append(
                PreventionAction(
                    mechanism=1,
                    action_type=ActionType.ADJUST_COUPLING,
                    params={"action": "REDUCE_COUPLING", "factor": reduction},
                )
            )

        # Mechanism 2: Layer Autonomy Preservation
        variances = monitor.layer_phase_variances()
        starved = [int(i) + 1 for i in np.flatnonzero(variances < V_MIN)]
        if starved:
            actions.append(
                PreventionAction(
                    mechanism=2,
                    action_type=ActionType.INJECT_PERTURBATION,
                    params={"action": "INJECT_PERTURBATION", "layers": starved},
                )
            )

        # Mechanism 3: Shadow Coherence Check
        if shadow_report.shadow_detected and r_current > 0.85:
            actions.append(
                PreventionAction(
                    mechanism=3,
                    action_type=ActionType.FORCE_SHADOW_INTEGRATION,
                    params={
                        "action": "FORCE_SHADOW_INTEGRATION",
                        "shadow_type": shadow_report.shadow_type,
                        "shadow_class": shadow_report.shadow_class,
                        "confidence": shadow_report.confidence,
                    },
                )
            )

        # Mechanism 4: Coherence Ceiling Enforcement. Engages from the
        # MAX_SUSTAINED boundary (0.90) upward — the band the spec labels
        # "MAX OPERATIONAL / ceiling target" — because waiting for the 0.93
        # sample means the beat crest has already outrun the controller
        # (ROADMAP.md, Deviation 4a).
        if r_current > MAX_SUSTAINED:
            actions.append(
                PreventionAction(
                    mechanism=4,
                    action_type=ActionType.ENFORCE_CEILING,
                    params={
                        "action": "ENFORCE_CEILING",
                        "target_r": MAX_SUSTAINED,
                        "zone": "breach" if r_current > MAX_OPERATIONAL else "soft",
                    },
                )
            )

        return actions

    # --- application (gated) ---------------------------------------------------

    def apply(
        self,
        actions: list[PreventionAction],
        engine: "ShuttleEngine",  # noqa: F821 — engine.py imports this module
        bus: OversightBus,
        tick: int,
    ) -> None:
        for action in actions:
            request = ActionRequest(
                tick=tick,
                actor=f"prevention.m{action.mechanism}",
                action_type=action.action_type,
                params=action.params,
            )
            if action.action_type is ActionType.ADJUST_COUPLING:
                factor = action.params["factor"]
                if (
                    engine.last_r <= EMERGENCY_THRESH
                    and engine.coupling > 0.0
                    and engine.k_safe is not None
                ):
                    # Below the danger zone, M1's cuts respect a floor of
                    # 0.7·k_safe: repeated compounding below the known-safe
                    # coupling is what drives the system through FUNCTIONAL
                    # into fragmentation. In the danger zone (r > 0.95) cuts
                    # are unconditional.
                    floor_factor = min(1.0, 0.7 * engine.k_safe / engine.coupling)
                    factor = max(factor, floor_factor)
                bus.execute(request, lambda f=factor: engine.scale_coupling(f))
            elif action.action_type is ActionType.INJECT_PERTURBATION:
                layers = action.params["layers"]
                bus.execute(
                    request,
                    lambda ls=layers: engine.perturb_layers(ls, self.perturbation_std),
                )
            elif action.action_type is ActionType.FORCE_SHADOW_INTEGRATION:
                bus.execute(request, lambda p=action.params: engine.integrate_shadow(p, tick))
            elif action.action_type is ActionType.ENFORCE_CEILING:
                # Ratchet-and-snap to the known-safe coupling (see
                # engine.enforce_ceiling). Harder snap deeper in; the ratchet
                # is edge-triggered — once per excursion above the ceiling.
                r = engine.last_r
                if r > EMERGENCY_THRESH:
                    fraction = 0.5
                elif r > MAX_OPERATIONAL:
                    fraction = 0.85
                else:
                    fraction = 1.0
                ratchet = engine._prev_r <= MAX_OPERATIONAL < r
                bus.execute(
                    request,
                    lambda fr=fraction, ra=ratchet: engine.enforce_ceiling(fr, ra),
                )
