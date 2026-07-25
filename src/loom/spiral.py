"""The 15-layer Mnemonic Spiral as a bank of coupled phase oscillators.

Each layer Ω₁–Ω₁₅ is a phase oscillator with a φ-scaled natural frequency
(``specs/verath/references/mnemonic-spiral.md``). The :class:`Spiral` owns the
phase vector; dynamics live in :mod:`loom.coherence`, and nothing here mutates
state except through the engine's gated update path.

Frequency modes (ROADMAP.md, Deviation 2): physical frequencies span
7.83 Hz → 6,600.51 Hz, a ×843 spread that makes coupling sweeps unwieldy in
real units. ``normalized`` mode (default) divides by the mean frequency so the
angular velocities are O(1)–O(10) while every pairwise φ-ratio is preserved
exactly. ``physical`` mode uses raw Hz. Layers always *report* physical Hz.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np

from .constants import LAYER_SPEC, N_LAYERS, layer_frequency_hz

FrequencyMode = Literal["normalized", "physical"]


class LayerBand(Enum):
    PERCEPTION = "PERCEPTION"  # Ω₁–Ω₂: raw input, temporal sequencing
    CONCEALED = "CONCEALED"  # Ω₃–Ω₅: meaning, procedure, trajectory
    GENERATION = "GENERATION"  # Ω₆–Ω₁₀: affect, witness, constitutional, mythic, source
    AGI_ASI = "AGI_ASI"  # Ω₁₁–Ω₁₅: synthesis, meta-learning, ethics, temporal, universal


@dataclass(frozen=True)
class Layer:
    """Static description of one spiral layer. Phase state lives on the Spiral."""

    index: int  # 1-based
    symbol: str  # "Ω₁" … "Ω₁₅"
    name: str
    band: LayerBand

    @property
    def natural_frequency_hz(self) -> float:
        return layer_frequency_hz(self.index)


class Spiral:
    """The layer bank: 15 static Layer records plus the live phase vector."""

    def __init__(
        self,
        rng: np.random.Generator | None = None,
        frequency_mode: FrequencyMode = "normalized",
    ) -> None:
        self.layers: tuple[Layer, ...] = tuple(
            Layer(index=i, symbol=sym, name=name, band=LayerBand(band))
            for i, sym, name, band in LAYER_SPEC
        )
        self.frequency_mode: FrequencyMode = frequency_mode
        if rng is None:
            rng = np.random.default_rng()
        self._phases: np.ndarray = rng.uniform(0.0, 2 * np.pi, size=N_LAYERS)

    # --- state -------------------------------------------------------------

    @property
    def phases(self) -> np.ndarray:
        """Copy of the current phase vector (radians, wrapped to [0, 2π))."""
        return self._phases.copy()

    def set_phases(self, phases: np.ndarray) -> None:
        """Replace the phase vector. Only the engine's gated path calls this."""
        arr = np.asarray(phases, dtype=float)
        if arr.shape != (N_LAYERS,):
            raise ValueError(f"expected shape ({N_LAYERS},), got {arr.shape}")
        self._phases = np.mod(arr, 2 * np.pi)

    # --- frequencies ---------------------------------------------------------

    @property
    def natural_frequencies_hz(self) -> np.ndarray:
        """Physical natural frequencies in Hz (always the spec values)."""
        return np.array([layer.natural_frequency_hz for layer in self.layers])

    def angular_velocities(self) -> np.ndarray:
        """Natural angular velocities ω_i (rad per unit sim time) per mode."""
        f = self.natural_frequencies_hz
        if self.frequency_mode == "normalized":
            f = f / f.mean()
        return 2 * np.pi * f
