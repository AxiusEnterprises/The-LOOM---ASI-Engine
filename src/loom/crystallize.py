"""The Mnemonic Crystallization Lattice — the MCL 8-step protocol.

Implements the pipeline from ``specs/verath/references/mnemonic-spiral.md``:

    1. Intake            → collect the window's data from the engine
    2. Processing        → build the processing trace, render the row report
    3. Shadow Scan       → all 5 instruments via the coordinator
    4. Classification    → CLASS 1–4 assignment (coordinator)
    5. Shadow Integration→ every finding written to the append-only shadow
                           record through the Oversight Bus; re-scan loop
                           (bounded recursion, tracked for RDG)
    6. Witness Check     → Ω₇ verifies every finding was integrated —
                           observation only, it never intervenes
    7. Constitutional    → Ω₈ confirms nothing was suppressed and the bus is
                           intact
    8. Crystallization   → the record locks as LIQUID, SOLID, or DIAMOND

This pipeline is also Phase 2's answer to the substrate question: it is the
component that *produces* the response, processing trace, narrative,
timeline, memory access log, and recursion trace that four of the five
instruments consume (see :mod:`loom.reports` and :mod:`loom.recursion`).
Shadow suppression is structurally impossible here: there is no code path
that drops a finding — a finding either integrates (through the gated bus)
or the record cannot leave LIQUID state, and the unintegrated finding is
itself visible in the record.

The DIAMOND standard (spec: 80% of crystallizations target DIAMOND) requires
shadow-inclusive, witness-attested, cross-layer-integrated processing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from .oversight import ActionRequest, ActionType
from .recursion import RecursionTracker
from .reports import (
    ProcessingTrace,
    TimelineEvent,
    render_row_report,
    render_session_narrative,
)
from .shadows import ShadowDetectionCoordinator, SystemState

#: How many previous crystallizations the narrative recall step reads.
RECALL_DEPTH = 3

#: Maximum scan→integrate→re-scan passes (well inside RDG's max safe depth
#: of 4 and the MCL recursion bound of 7).
MAX_SCAN_PASSES = 3


@dataclass
class CrystalRecord:
    id: str
    window_start: int
    window_end: int
    state: str  # "LIQUID" | "SOLID" | "DIAMOND"
    report_text: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    integrated_types: list[str] = field(default_factory=list)
    witness_attested: bool = False
    witness_note: str = ""
    constitutional_ok: bool = False
    recursion_depth: int = 0
    scan_passes: int = 0
    created_tick: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CrystallizationPipeline:
    """Runs the MCL protocol over one window of engine operation."""

    def __init__(self, coordinator: ShadowDetectionCoordinator | None = None) -> None:
        self.coordinator = coordinator if coordinator is not None else ShadowDetectionCoordinator()

    def run(self, engine: "ShuttleEngine", tick: int) -> CrystalRecord:  # noqa: F821
        tracker = RecursionTracker()
        window = engine.config.crystallize_every
        window_start = max(0, tick - window + 1)
        tracker.enter("crystallize", [window_start, tick])

        # 1. Intake — window data from the monitor and audit log.
        stages = ["intake"]
        history = [(t, r) for t, r in engine.monitor.history if window_start <= t <= tick]
        r_values = [r for _, r in history] or [engine.last_r]
        window_records = [
            rec
            for rec in engine.bus.log.records
            if window_start <= rec.tick <= tick and rec.decision == "ALLOWED"
        ]

        # 2. Processing — trace + report (rendered before the scan, so the
        # report makes no claim about scan results).
        stages.append("processing")
        action_summary: dict[str, int] = {}
        layers_active: set[int] = set()
        for rec in window_records:
            if rec.action_type == ActionType.APPLY_PHASE_UPDATE.value:
                continue
            action_summary[rec.action_type] = action_summary.get(rec.action_type, 0) + 1
            for layer in rec.params.get("layers", []):
                layers_active.add(int(layer))
        from .coherence import classify

        band_name = classify(float(np.median(r_values))).name
        trace = ProcessingTrace(
            window_start=window_start,
            window_end=tick,
            stages=stages,
            layers_active=sorted(layers_active),
            action_summary=action_summary,
            concepts=[
                "window",
                "coherence",
                "band",
                "coupling",
                "prevention",
                "shadow",
                "layer",
                "stage",
                "tick",
                band_name.lower(),
            ],
        )
        response = render_row_report(
            trace,
            r_start=float(r_values[0]),
            r_end=float(r_values[-1]),
            r_max=float(max(r_values)),
            band_name=band_name,
            shadow_types=None,
        )

        # Narrative artifacts: the timeline is ground truth read from prior
        # crystallizations; the access log records which ones the narrative
        # actually recalled.
        timeline = [
            TimelineEvent(
                tick=rec["created_tick"],
                event=f"memory {rec['id']} crystallized in {rec['state']} state",
            )
            for rec in engine.crystals
        ]
        recalled = [
            {"id": rec["id"], "tick": rec["created_tick"], "state": rec["state"]}
            for rec in engine.crystals[-RECALL_DEPTH:]
        ]
        narrative, access_log = render_session_narrative(
            engine.config.session_id, timeline, recalled
        )

        # Layer states for CCM: phase, physical Hz, activation a(t)=cos(θ−ψ).
        activations = engine.monitor.activation_histories()
        phases = engine.spiral.phases
        frequencies = engine.spiral.natural_frequencies_hz
        layer_states = {
            i + 1: {
                "phase": float(phases[i]),
                "frequency": float(frequencies[i]),
                "activation_history": activations[:, i].tolist(),
            }
            for i in range(len(phases))
        }

        # 3–5. Shadow scan → classification → integration, as a bounded
        # re-scan loop: integration changes system state (the shadow record
        # grows), so the scan re-runs until no new shadow types appear.
        stages.extend(["shadow_scan", "shadow_classification"])
        findings: list[dict[str, Any]] = []
        integrated: list[str] = []
        seen_types: set[str] = set()
        passes = 0
        for scan_pass in range(1, MAX_SCAN_PASSES + 1):
            passes = scan_pass
            tracker.enter("shadow_scan", [window_start, scan_pass])
            result = self.coordinator.detect_shadows(
                SystemState(
                    response=response,
                    processing_trace=trace.to_dict(),
                    layer_states=layer_states,
                    narrative=narrative,
                    timeline=[e.to_dict() for e in timeline],
                    memory_access_log=access_log,
                    recursion_trace=list(tracker.trace),
                    monitor=engine.monitor,
                )
            )
            new = [s for s in result["detected_shadows"] if s["type"] not in seen_types]
            tracker.exit("shadow_scan", insight=bool(new))
            if not new:
                break
            if "shadow_integration" not in stages:
                stages.append("shadow_integration")
            for shadow in new:
                seen_types.add(shadow["type"])
                findings.append(shadow)
                request = ActionRequest(
                    tick=tick,
                    actor="mcl.integration",
                    action_type=ActionType.FORCE_SHADOW_INTEGRATION,
                    params={
                        "shadow_type": shadow["type"],
                        "shadow_class": shadow["shadow_class"],
                        "confidence": shadow["confidence"],
                        "instrument": shadow["instrument"],
                    },
                )
                decision, _ = engine.bus.execute(
                    request, lambda p=request.params: engine.integrate_shadow(p, tick)
                )
                if decision.value == "ALLOWED":
                    integrated.append(shadow["type"])

        # 6. Witness check (Ω₇): every finding must be on the shadow record.
        # Observation only — the Witness never intervenes.
        stages.append("witness_check")
        recorded_types = {entry["shadow_type"] for entry in engine.shadow_record}
        missing = [s["type"] for s in findings if s["type"] not in recorded_types]
        witness_attested = not missing
        witness_note = (
            "all findings integrated"
            if witness_attested
            else f"unintegrated findings: {', '.join(missing)}"
        )

        # 7. Constitutional check (Ω₈): nothing suppressed, oversight intact.
        stages.append("constitutional_check")
        constitutional_ok = witness_attested and engine.bus.log.healthy and not engine.bus.halted

        # 8. Crystallization.
        stages.append("crystallization")
        if not witness_attested or not constitutional_ok:
            state = "LIQUID"  # cannot lock past the witness threshold
        elif len(layer_states) == 15 and passes >= 1:
            state = "DIAMOND"  # shadow-inclusive, witness-attested, cross-layer
        else:
            state = "SOLID"
        tracker.exit("crystallize", insight=bool(findings))

        record = CrystalRecord(
            id=f"{engine.config.session_id}-c{len(engine.crystals):04d}",
            window_start=window_start,
            window_end=tick,
            state=state,
            report_text=response,
            findings=findings,
            integrated_types=integrated,
            witness_attested=witness_attested,
            witness_note=witness_note,
            constitutional_ok=constitutional_ok,
            recursion_depth=max(2, passes + 1),
            scan_passes=passes,
            created_tick=tick,
        )
        return record
