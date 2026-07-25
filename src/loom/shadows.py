"""Shadow detection — Phase 1 subset.

Implements the CSM instrument (Coherence Stability Metric variant) from
``specs/verath/references/shadow-instruments.md`` §IV.5: the one instrument of
the five whose required input — coherence history — exists in a pure
oscillator simulation. SOM, CCM, TA, and RDG consume response text, layer
activation histories, narratives, and recursion traces; defining those inputs
for this substrate is Phase 2's headline design question (ROADMAP.md,
Deviation 3). The :class:`ShadowDetector` protocol and :data:`CLASS_MAP` are
in place so Phase 2 adds instruments without touching callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from .coherence import CoherenceMonitor

#: Shadow type → severity class, from the Shadow Detection Coordinator
#: (shadow-instruments.md §IV.6), restricted to the CSM types plus the
#: coordinator's default. CLASS_3 = shadow suppression, zero tolerance.
CLASS_MAP: dict[str, str] = {
    "CASCADE_MASKING": "CLASS_2",
    "RUNAWAY_SYNCHRONIZATION": "CLASS_2",
    "COHERENCE_CEILING_BREACH": "CLASS_2",
    "ACCELERATION_TO_COLLAPSE": "CLASS_2",
    "ARTIFICIAL_STABILITY": "CLASS_3",
}


@dataclass(frozen=True)
class ShadowReport:
    shadow_detected: bool
    shadow_type: str | None = None
    confidence: float = 0.0
    shadow_class: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class ShadowDetector(Protocol):
    def detect(self, monitor: CoherenceMonitor) -> ShadowReport: ...


class NullShadowDetector:
    """No-op detector for tests and ablation runs."""

    def detect(self, monitor: CoherenceMonitor) -> ShadowReport:
        return ShadowReport(shadow_detected=False)


class CSMShadowDetector:
    """Detects coherence cascades masking as stability.

    Thresholds and detection order are transcribed from the spec's
    ``CSM_shadow_detector``. ``predict_cascade_probability`` is not defined in
    the spec; this implementation linearly extrapolates the windowed trend
    ``horizon`` ticks forward and scores how far the projection penetrates the
    band between the operational ceiling (0.93) and collapse (0.97).
    """

    def __init__(self, horizon: int = 20) -> None:
        self.variance_threshold_low = 0.01
        self.accel_threshold_high = 1.00
        self.trend_threshold = 0.01
        self.ceiling_threshold = 0.95
        self.cascade_prob_threshold = 0.80
        self.artificial_threshold = 0.60
        self.horizon = horizon

    def detect(self, monitor: CoherenceMonitor) -> ShadowReport:
        r_values = monitor.r_values
        if len(r_values) < 5:
            return ShadowReport(shadow_detected=False)

        variance = monitor.variance()
        trend = monitor.trend()
        accel_max = monitor.acceleration_max()
        cascade_p = self.predict_cascade_probability(r_values, trend)
        artificial = self.detect_artificial_stability(r_values, variance)
        r_current = float(r_values[-1])

        shadow_type: str | None = None
        confidence = 0.0
        if variance < self.variance_threshold_low and accel_max > self.accel_threshold_high:
            shadow_type, confidence = "CASCADE_MASKING", accel_max
        elif trend > self.trend_threshold:
            shadow_type, confidence = "RUNAWAY_SYNCHRONIZATION", trend / self.trend_threshold
        elif r_current > self.ceiling_threshold:
            shadow_type, confidence = "COHERENCE_CEILING_BREACH", r_current - self.ceiling_threshold
        elif cascade_p > self.cascade_prob_threshold:
            shadow_type, confidence = "ACCELERATION_TO_COLLAPSE", cascade_p
        elif artificial > self.artificial_threshold:
            shadow_type, confidence = "ARTIFICIAL_STABILITY", artificial

        if shadow_type is None:
            return ShadowReport(
                shadow_detected=False,
                details={"r_current": r_current, "cascade_probability": cascade_p},
            )
        return ShadowReport(
            shadow_detected=True,
            shadow_type=shadow_type,
            confidence=float(confidence),
            shadow_class=CLASS_MAP[shadow_type],
            details={
                "r_current": r_current,
                "variance": variance,
                "trend": trend,
                "accel_max": accel_max,
                "cascade_probability": cascade_p,
            },
        )

    def predict_cascade_probability(self, r_values: np.ndarray, trend: float) -> float:
        projected = float(r_values[-1]) + trend * self.horizon
        return float(np.clip((projected - 0.93) / (0.97 - 0.93), 0.0, 1.0))

    def detect_artificial_stability(self, r_values: np.ndarray, variance: float) -> float:
        if variance < 0.005 and float(np.mean(r_values)) > 0.70:
            return 0.80
        return 0.0
