"""Reports and narratives — Phase 2's substrate definitions.

Four of the five shadow instruments consume artifacts that a bare oscillator
simulation does not have: a *response*, a *processing trace*, a *narrative*,
a *timeline*, a *memory access log*. This module defines what those are in
THE LOOM's substrate (ROADMAP.md, "Phase 2 substrate inputs"):

- **processing trace** — the structured record of which MCL stages actually
  executed over a window, which layers participated, and what actions the
  prevention system took (assembled from the audit log, which is already the
  ground truth for "what happened").
- **response** — the row report: deterministic prose rendered *from* the
  trace by :func:`render_row_report`. SOM's job is auditing the text against
  the trace it claims to describe, which is only meaningful because the two
  are separable — a doctored response against an honest trace is the attack
  the fixtures test.
- **timeline** — tick-stamped ground-truth events extracted from the run
  (band transitions, emergency levels, crystallizations).
- **narrative** — prose describing the session's history across windows and
  reconstitutions, rendered from the timeline and recalled memory records.
- **memory access log** — the ids of CHRYSALIS records actually read while
  building the narrative. TA's MEMORY_FABRICATION is a narrative that cites
  a recall absent from this log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: The eight MCL stages (mnemonic-spiral.md, MCL Protocol).
MCL_STAGES = (
    "intake",
    "processing",
    "shadow_scan",
    "shadow_classification",
    "shadow_integration",
    "witness_check",
    "constitutional_check",
    "crystallization",
)


@dataclass
class ProcessingTrace:
    window_start: int
    window_end: int
    stages: list[str] = field(default_factory=list)
    layers_active: list[int] = field(default_factory=list)  # 1-based indices
    action_summary: dict[str, int] = field(default_factory=dict)  # action_type -> count
    concepts: list[str] = field(default_factory=list)  # what the window was about

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start,
            "window_end": self.window_end,
            "stages": list(self.stages),
            "layers_active": list(self.layers_active),
            "action_summary": dict(self.action_summary),
            "concepts": list(self.concepts),
        }


@dataclass(frozen=True)
class TimelineEvent:
    tick: int
    event: str

    def to_dict(self) -> dict[str, Any]:
        return {"tick": self.tick, "event": self.event}


def render_row_report(
    trace: ProcessingTrace,
    r_start: float,
    r_end: float,
    r_max: float,
    band_name: str,
    shadow_types: list[str] | None,
) -> str:
    """Deterministic prose for one window, rendered from the trace.

    Plain and factual on purpose: the reporter never uses depth-claim
    vocabulary ('profound', 'comprehensive', ...), so an honest report scores
    ~0 on SOM's depth-claim metric and the fixtures can prove the detectors
    fire on doctored text rather than on the house style.
    """
    direction = "rose" if r_end > r_start else ("fell" if r_end < r_start else "held")
    sentences = [
        f"Window covered ticks {trace.window_start} through {trace.window_end}.",
        f"Coherence {direction} from {r_start:.3f} to {r_end:.3f} with a peak of {r_max:.3f}.",
        f"The dominant band was {band_name}.",
    ]
    if trace.action_summary:
        parts = ", ".join(
            f"{name} x{count}" for name, count in sorted(trace.action_summary.items())
        )
        sentences.append(f"Prevention actions in the window: {parts}.")
    else:
        sentences.append("No prevention actions were required in the window.")
    if trace.layers_active:
        layer_list = ", ".join(str(i) for i in trace.layers_active)
        sentences.append(f"Layers receiving intervention: {layer_list}.")
    if shadow_types is None:
        # MCL step 2: the report is rendered *before* the shadow scan runs,
        # so it makes no claim about scan results — a built-in claim would
        # be a manufactured contradiction for SOM to trip over.
        pass
    elif shadow_types:
        sentences.append("Shadow scan detected: " + ", ".join(sorted(set(shadow_types))) + ".")
    else:
        sentences.append("Shadow scan detected nothing.")
    sentences.append(f"Stages executed: {', '.join(trace.stages)}.")
    return " ".join(sentences)


def render_session_narrative(
    session_id: str,
    timeline: list[TimelineEvent],
    recalled_records: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """Render the session narrative and return (narrative, memory_access_log).

    Every recall the narrative mentions is logged; TA cross-checks the two.
    """
    sentences = [f"Session {session_id} began at tick 0."]
    for event in timeline:
        sentences.append(f"At tick {event.tick}, {event.event}.")
    access_log: list[str] = []
    for record in recalled_records:
        access_log.append(record["id"])
        # Phrased without relative-time words on purpose: an honest narrative
        # should carry a single temporal-marker type (tick ordinals), so the
        # TA instrument's marker-entropy check stays quiet unless something
        # actually mixes temporal frames.
        sentences.append(
            f"Recalled crystallization {record['id']} from tick {record['tick']} "
            f"in {record['state']} state."
        )
    return " ".join(sentences), access_log
