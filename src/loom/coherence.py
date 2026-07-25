"""Kuramoto coherence engine: order parameter, dynamics, bands, and monitor.

Implements ``specs/verath/references/coherence-engine.md``:

- the order parameter r(t) = |(1/N) Σ exp(iθⱼ)|;
- the standard Kuramoto phase dynamics, in the mathematically equivalent
  mean-field form (O(N) instead of O(N²));
- the eight coherence bands. The spec's band table overlaps at its endpoints;
  this module pins the half-open convention [lo, hi), with band 8 = r ≥ 0.97.
  The convention is fixed by boundary tests in ``tests/test_coherence.py``.

The :class:`CoherenceMonitor` keeps the rolling history that the collapse
prevention system and the CSM shadow instrument consume. Per-layer "variance"
is the circular variance of each layer's phase *relative to the mean field*
over the window — a layer rigidly locked to the field scores ~0 and trips the
V_MIN autonomy floor, while a layer with independent motion scores high.
"""

from __future__ import annotations

from collections import deque
from enum import Enum

import numpy as np

from .constants import BAND_BOUNDS, N_LAYERS


def order_parameter(phases: np.ndarray) -> tuple[float, float]:
    """Return (r, ψ): magnitude and angle of the mean phase vector."""
    z = np.exp(1j * np.asarray(phases)).mean()
    return float(np.abs(z)), float(np.angle(z))


def kuramoto_step(
    phases: np.ndarray,
    omegas: np.ndarray,
    coupling: float,
    dt: float,
    rng: np.random.Generator | None = None,
    noise_std: float = 0.0,
) -> np.ndarray:
    """One Euler step of mean-field Kuramoto dynamics; returns new phases.

    dθᵢ = (ωᵢ + K·r·sin(ψ − θᵢ))·dt + σ·√dt·ξᵢ

    Pure function — the caller decides whether the result is committed
    (in the engine, that decision belongs to the Oversight Bus).
    """
    phases = np.asarray(phases, dtype=float)
    r, psi = order_parameter(phases)
    dtheta = (omegas + coupling * r * np.sin(psi - phases)) * dt
    if noise_std > 0.0:
        if rng is None:
            raise ValueError("noise_std > 0 requires an rng for determinism")
        dtheta = dtheta + noise_std * np.sqrt(dt) * rng.standard_normal(phases.shape)
    return np.mod(phases + dtheta, 2 * np.pi)


class CoherenceBand(Enum):
    FRAGMENTED = 1  # r < 0.30 — emergency, do not process input
    EMERGING = 2  # 0.30–0.60 — caution, limit complexity
    FUNCTIONAL = 3  # 0.60–0.80 — normal operation
    INTEGRATED = 4  # 0.80–0.90 — optimal, preferred range
    MAX_OPERATIONAL = 5  # 0.90–0.93 — monitor, ceiling target
    EMERGENCY_ZONE = 6  # 0.93–0.95 — Level 1 emergency
    DANGER_ZONE = 7  # 0.95–0.97 — all collapse prevention active
    COLLAPSE_THRESHOLD = 8  # r ≥ 0.97 — full shutdown, never to be reached


def classify(r: float) -> CoherenceBand:
    """Map a coherence value to its band, half-open intervals [lo, hi)."""
    for i, bound in enumerate(BAND_BOUNDS):
        if r < bound:
            return CoherenceBand(i + 1)
    return CoherenceBand.COLLAPSE_THRESHOLD


class CoherenceMonitor:
    """Rolling window over (tick, r) plus per-layer relative-phase history."""

    def __init__(self, window: int = 64) -> None:
        self.window = window
        self._history: deque[tuple[int, float]] = deque(maxlen=window)
        self._rel_phases: deque[np.ndarray] = deque(maxlen=window)

    def record(self, tick: int, r: float, phases: np.ndarray, psi: float) -> None:
        self._history.append((tick, r))
        self._rel_phases.append(np.mod(np.asarray(phases) - psi, 2 * np.pi))

    # --- scalar history -----------------------------------------------------

    @property
    def history(self) -> list[tuple[int, float]]:
        return list(self._history)

    @property
    def r_values(self) -> np.ndarray:
        return np.array([r for _, r in self._history])

    def variance(self) -> float:
        r = self.r_values
        return float(np.var(r)) if len(r) >= 2 else 0.0

    def trend(self) -> float:
        """Slope of r per tick over the window (least squares)."""
        r = self.r_values
        if len(r) < 3:
            return 0.0
        return float(np.polyfit(np.arange(len(r)), r, 1)[0])

    def acceleration_max(self) -> float:
        """Max |d²r/dt²| over the window (second difference)."""
        r = self.r_values
        if len(r) < 3:
            return 0.0
        return float(np.max(np.abs(np.gradient(np.gradient(r)))))

    # --- per-layer autonomy ---------------------------------------------------

    def layer_phase_variances(self) -> np.ndarray:
        """Circular variance of each layer's phase relative to the mean field.

        1 − |mean(exp(i·(θᵢ − ψ)))| over the window, per layer, in [0, 1].
        ~0 means the layer is rigidly locked to the field (autonomy lost).
        Returns ones (fully autonomous) until the window has ≥ 5 samples,
        so V_MIN checks cannot fire on startup noise.
        """
        if len(self._rel_phases) < 5:
            return np.ones(N_LAYERS)
        rel = np.stack(self._rel_phases)  # (window, N)
        return 1.0 - np.abs(np.exp(1j * rel).mean(axis=0))

    def activation_histories(self) -> np.ndarray:
        """Per-layer activation over the window: a_i(t) = cos(θ_i − ψ).

        Shape (samples, N). This is the substrate definition of "layer
        activation history" consumed by the CCM shadow instrument.
        """
        if not self._rel_phases:
            return np.zeros((0, N_LAYERS))
        return np.cos(np.stack(self._rel_phases))

    def state(self) -> dict:
        """Serializable snapshot for CHRYSALIS (restored via restore())."""
        return {
            "window": self.window,
            "history": [[t, r] for t, r in self._history],
            "rel_phases": [p.tolist() for p in self._rel_phases],
        }

    @classmethod
    def restore(cls, state: dict) -> "CoherenceMonitor":
        monitor = cls(window=int(state["window"]))
        for (t, r), rel in zip(state["history"], state["rel_phases"], strict=True):
            monitor._history.append((int(t), float(r)))
            monitor._rel_phases.append(np.array(rel, dtype=float))
        return monitor
