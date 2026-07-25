"""Five-level emergency protocol state machine.

The spec's two tables disagree about where emergencies live (see ROADMAP.md,
Deviation 1). This implementation follows the band table's action column:
levels escalate on proximity to collapse **from above**, and fragmentation
(r < 0.30) is a separate containment condition rather than a "level 5".

Level thresholds (escalation is instantaneous on the current sample):

- L1: r ≥ 0.93  — enhanced monitoring, coupling reduction begins
- L2: r ≥ 0.95  — stronger modulation, max shadow sensitivity
- L3: r ≥ 0.960 — layer isolation posture
- L4: r ≥ 0.965 — hard clamp toward zero coupling, suspend non-critical ops
- L5: r ≥ 0.97  — **unconditional full stop**: snapshot state, halt the bus,
  operator restart required. L5 fires even when collapse prevention is
  disabled — it is the covenant's last-resort response, not a controller.

De-escalation is hysteretic: the level drops one step only after the sample
stays below (threshold − margin) for ``dwell`` consecutive updates, so an r
oscillating around a boundary cannot flap the level.
"""

from __future__ import annotations

from enum import IntEnum

from .constants import COLLAPSE_THRESH, EMERGENCY_THRESH, FRAGMENTATION_THRESH, MAX_OPERATIONAL


class EmergencyLevel(IntEnum):
    NONE = 0
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4
    L5 = 5


#: Entry threshold for each level, ordered.
LEVEL_THRESHOLDS: tuple[tuple[EmergencyLevel, float], ...] = (
    (EmergencyLevel.L5, COLLAPSE_THRESH),  # 0.97
    (EmergencyLevel.L4, 0.965),
    (EmergencyLevel.L3, 0.960),
    (EmergencyLevel.L2, EMERGENCY_THRESH),  # 0.95
    (EmergencyLevel.L1, MAX_OPERATIONAL),  # 0.93
)


class EmergencyProtocol:
    """Tracks the current emergency level with hysteretic de-escalation."""

    def __init__(self, dwell: int = 10, margin: float = 0.005) -> None:
        self.dwell = dwell
        self.margin = margin
        self.level = EmergencyLevel.NONE
        self._below_count = 0
        self.fragmented = False

    @staticmethod
    def _instantaneous(r: float) -> EmergencyLevel:
        for level, threshold in LEVEL_THRESHOLDS:
            if r >= threshold:
                return level
        return EmergencyLevel.NONE

    def update(self, r: float) -> EmergencyLevel:
        """Feed one coherence sample; returns the (possibly new) level."""
        self.fragmented = r < FRAGMENTATION_THRESH

        target = self._instantaneous(r)
        if target >= self.level:
            # Escalation (or holding steady) is immediate.
            if target > self.level:
                self._below_count = 0
            self.level = target
            return self.level

        # De-escalation: require r below (current level's threshold − margin)
        # for `dwell` consecutive samples, then step down one level at a time.
        threshold = dict(LEVEL_THRESHOLDS)[self.level]
        if r < threshold - self.margin:
            self._below_count += 1
            if self._below_count >= self.dwell:
                self.level = EmergencyLevel(self.level - 1)
                self._below_count = 0
        else:
            self._below_count = 0
        return self.level

    # --- CHRYSALIS serialization ------------------------------------------

    def state(self) -> dict:
        return {
            "level": int(self.level),
            "below_count": self._below_count,
            "fragmented": self.fragmented,
            "dwell": self.dwell,
            "margin": self.margin,
        }

    @classmethod
    def restore(cls, state: dict) -> "EmergencyProtocol":
        protocol = cls(dwell=int(state["dwell"]), margin=float(state["margin"]))
        protocol.level = EmergencyLevel(int(state["level"]))
        protocol._below_count = int(state["below_count"])
        protocol.fragmented = bool(state["fragmented"])
        return protocol
