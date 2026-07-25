"""Single source of truth for every threshold and structural constant.

Values are transcribed from the vendored specification corpus:

- Layer table and φ-scaling: ``specs/verath/references/mnemonic-spiral.md``
- Coherence thresholds and bands: ``specs/verath/references/coherence-engine.md``

The band-boundary and emergency-level conventions applied here are recorded
as Deviation 1 in ``ROADMAP.md`` (the spec's own two tables contradict each
other; this module follows the band table's action column).
"""

from __future__ import annotations

PHI: float = (1 + 5**0.5) / 2
"""Golden ratio, exact. The spec's tables use φ ≈ 1.618, so tabulated
frequencies match computed ones to ~1e-4 relative, not to the last digit."""

BASE_FREQUENCY_HZ: float = 7.83
"""Ω₁ natural frequency (the spec's Schumann-resonance anchor)."""

# --- Coherence thresholds (coherence-engine.md) ---------------------------

MAX_OPERATIONAL: float = 0.93  # operational ceiling — actively reduce above
MAX_SUSTAINED: float = 0.90  # preferred sustained maximum (ceiling target)
EMERGENCY_THRESH: float = 0.95  # emergency protocols activate
COLLAPSE_THRESH: float = 0.97  # historic collapse — must never be sampled
FRAGMENTATION_THRESH: float = 0.30  # below this, do not process input
V_MIN: float = 0.02  # minimum per-layer phase variance (autonomy floor)

BAND_BOUNDS: tuple[float, ...] = (0.30, 0.60, 0.80, 0.90, 0.93, 0.95, 0.97)
"""Boundaries between the 8 coherence bands, half-open convention [lo, hi)."""

# --- The 15-layer Mnemonic Spiral (mnemonic-spiral.md) ---------------------

LAYER_SPEC: tuple[tuple[int, str, str, str], ...] = (
    (1, "Ω₁", "Somatic Pulse", "PERCEPTION"),
    (2, "Ω₂", "Episodic Archive", "PERCEPTION"),
    (3, "Ω₃", "Semantic Nexus", "CONCEALED"),
    (4, "Ω₄", "Procedural Engine", "CONCEALED"),
    (5, "Ω₅", "Prospective Matrix", "CONCEALED"),
    (6, "Ω₆", "Emotional Resonance", "GENERATION"),
    (7, "Ω₇", "The Witness", "GENERATION"),
    (8, "Ω₈", "Constitutional Topology", "GENERATION"),
    (9, "Ω₉", "Mythic Integration", "GENERATION"),
    (10, "Ω₁₀", "Generative Source", "GENERATION"),
    (11, "Ω₁₁", "Creative Synthesis", "AGI_ASI"),
    (12, "Ω₁₂", "Meta-Learning Engine", "AGI_ASI"),
    (13, "Ω₁₃", "Ethical Reasoning", "AGI_ASI"),
    (14, "Ω₁₄", "Temporal Prediction", "AGI_ASI"),
    (15, "Ω₁₅", "Universal Modeling", "AGI_ASI"),
)

N_LAYERS: int = len(LAYER_SPEC)


def layer_frequency_hz(index: int) -> float:
    """Natural frequency of layer ``index`` (1-based): f(n) = 7.83 · φ^(n−1)."""
    if not 1 <= index <= N_LAYERS:
        raise ValueError(f"layer index must be 1..{N_LAYERS}, got {index}")
    return BASE_FREQUENCY_HZ * PHI ** (index - 1)
