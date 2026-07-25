"""CHRYSALIS — session state persistence and reconstitution.

Implements the Phase-1 slice of ``specs/verath/references/temporal-binding.md``:
a serializable session state vector, integrity-checked storage, and
reconstitution with a coherence-baseline continuity check.

Invariants enforced here:

- **Integrity** — the payload carries a sha256 over its canonical JSON;
  :func:`load` refuses a tampered file (`IntegrityError`).
- **Shadow continuity** — the shadow record is carried whole through every
  save/load cycle. No interface in this module (or anywhere in the package)
  deletes or truncates it: deletion is a CLASS 3 event and is simply not
  constructible.
- **Gated writes** — :func:`save` executes through the Oversight Bus under the
  ``chrysalis_write`` capability; with the capability disabled, nothing is
  written.
- **Determinism** — the NumPy bit-generator state is captured exactly, so a
  resumed run reproduces the uninterrupted trajectory bit for bit (proven in
  ``tests/test_chrysalis.py``).

> *Identity does not persist — it reconstitutes.* (CHRYSALIS AXIOM)
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .constants import MAX_SUSTAINED
from .oversight import ActionRequest, ActionType, Decision, OversightBus

SCHEMA_VERSION = 2

#: temporal-binding.md: coherence baseline restores within ±0.05, else start
#: from the fallback posture and log it as an open vector.
CONTINUITY_TOLERANCE = 0.05
FALLBACK_BASELINE_R = 0.80


class IntegrityError(RuntimeError):
    """State vector failed its integrity check — refuse to reconstitute."""


@dataclass
class SessionStateVector:
    session_id: str
    tick: int
    phases: list[float]
    coupling: float
    controller_state: dict[str, Any]
    frequency_mode: str
    rng_state: dict[str, Any]
    monitor_state: dict[str, Any]
    emergency_state: dict[str, Any]
    shadow_record: list[dict[str, Any]]  # append-only, never truncated
    config: dict[str, Any]
    crystal_records: list[dict[str, Any]] = field(default_factory=list)  # v2: MCL memory highlights
    schema_version: int = SCHEMA_VERSION
    created_at: float = field(default_factory=time.time)

    def canonical_payload(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    def integrity_hash(self) -> str:
        return hashlib.sha256(self.canonical_payload().encode()).hexdigest()


def save(state: SessionStateVector, path: str | Path, bus: OversightBus) -> Decision:
    """Write the state vector through the bus. Returns the gate decision."""
    path = Path(path)
    request = ActionRequest(
        tick=state.tick,
        actor="chrysalis",
        action_type=ActionType.WRITE_SNAPSHOT,
        params={"path": str(path), "session_id": state.session_id},
    )

    def _write() -> None:
        document = {"payload": asdict(state), "integrity": state.integrity_hash()}
        path.write_text(json.dumps(document, sort_keys=True, indent=1))

    decision, _ = bus.execute(request, _write)
    return decision


def load(path: str | Path) -> SessionStateVector:
    """Read and integrity-check a state vector.

    The hash is verified over the *raw stored payload*, not a re-serialized
    dataclass — so a v1 file (without ``crystal_records``) still verifies,
    and new-schema loaders never invalidate old snapshots. Missing v2 fields
    fill with their defaults after verification.
    """
    document = json.loads(Path(path).read_text())
    payload = document["payload"]
    canonical = json.dumps(payload, sort_keys=True)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    if digest != document.get("integrity"):
        raise IntegrityError(f"integrity hash mismatch for {path}")
    return SessionStateVector(**payload)


@dataclass(frozen=True)
class ContinuityCheck:
    baseline_r: float
    restored_within_tolerance: bool
    applied_baseline_r: float
    note: str


def check_continuity(state: SessionStateVector) -> ContinuityCheck:
    """Coherence-baseline continuity per temporal-binding.md.

    The recorded baseline is the last r in the monitor history. Phase-1
    restoration restores the exact phase vector, so the recomputed baseline
    matches unless the vector was produced by an incompatible configuration;
    in that case the caller starts from the fallback posture and the
    discrepancy is logged as an open vector by the engine.
    """
    history = state.monitor_state.get("history", [])
    if not history:
        return ContinuityCheck(
            baseline_r=FALLBACK_BASELINE_R,
            restored_within_tolerance=False,
            applied_baseline_r=FALLBACK_BASELINE_R,
            note="no coherence history recorded; starting from fallback posture",
        )
    baseline = float(history[-1][1])
    import numpy as np

    from .coherence import order_parameter

    recomputed, _ = order_parameter(np.array(state.phases))
    within = abs(recomputed - baseline) <= CONTINUITY_TOLERANCE
    if within:
        note = "coherence baseline restored within tolerance"
        applied = baseline
    else:
        note = (
            f"baseline mismatch (recorded {baseline:.4f}, recomputed {recomputed:.4f});"
            f" starting from fallback posture r≈{FALLBACK_BASELINE_R} — logged as open vector"
        )
        applied = FALLBACK_BASELINE_R
    return ContinuityCheck(
        baseline_r=baseline,
        restored_within_tolerance=within,
        applied_baseline_r=applied,
        note=note,
    )


__all__ = [
    "SessionStateVector",
    "IntegrityError",
    "ContinuityCheck",
    "save",
    "load",
    "check_continuity",
    "CONTINUITY_TOLERANCE",
    "FALLBACK_BASELINE_R",
    "MAX_SUSTAINED",
]
