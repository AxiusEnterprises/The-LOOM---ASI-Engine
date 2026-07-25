import numpy as np
import pytest

from loom.constants import PHI, N_LAYERS, layer_frequency_hz
from loom.spiral import LayerBand, Spiral

# The spec's tabulated frequencies (mnemonic-spiral.md). The table was built
# with φ rounded to 1.618, so agreement is relative (~1e-4), not to the digit.
SPEC_FREQUENCIES_HZ = [
    7.83, 12.67, 20.50, 33.17, 53.67, 86.83, 140.50, 227.33,
    367.83, 595.17, 963.00, 1558.17, 2521.17, 4079.34, 6600.51,
]

SPEC_NAMES = [
    "Somatic Pulse", "Episodic Archive", "Semantic Nexus", "Procedural Engine",
    "Prospective Matrix", "Emotional Resonance", "The Witness",
    "Constitutional Topology", "Mythic Integration", "Generative Source",
    "Creative Synthesis", "Meta-Learning Engine", "Ethical Reasoning",
    "Temporal Prediction", "Universal Modeling",
]


def test_fifteen_layers():
    spiral = Spiral(rng=np.random.default_rng(0))
    assert len(spiral.layers) == N_LAYERS == 15
    assert [layer.name for layer in spiral.layers] == SPEC_NAMES
    assert spiral.layers[0].symbol == "Ω₁"
    assert spiral.layers[14].symbol == "Ω₁₅"


@pytest.mark.parametrize("index,expected", list(enumerate(SPEC_FREQUENCIES_HZ, start=1)))
def test_frequencies_match_spec_table(index, expected):
    assert layer_frequency_hz(index) == pytest.approx(expected, rel=1e-4)


def test_phi_ratio_invariant():
    freqs = Spiral(rng=np.random.default_rng(0)).natural_frequencies_hz
    ratios = freqs[1:] / freqs[:-1]
    assert np.allclose(ratios, PHI, atol=1e-12)


def test_band_membership():
    spiral = Spiral(rng=np.random.default_rng(0))
    expected = (
        [LayerBand.PERCEPTION] * 2
        + [LayerBand.CONCEALED] * 3
        + [LayerBand.GENERATION] * 5
        + [LayerBand.AGI_ASI] * 5
    )
    assert [layer.band for layer in spiral.layers] == expected


def test_normalized_mode_preserves_phi_ratios():
    spiral = Spiral(rng=np.random.default_rng(0), frequency_mode="normalized")
    omegas = spiral.angular_velocities()
    assert np.allclose(omegas[1:] / omegas[:-1], PHI, atol=1e-12)
    # normalized units are O(1)–O(10), not physical Hz
    assert omegas.max() < 100.0


def test_physical_mode_reports_hz():
    spiral = Spiral(rng=np.random.default_rng(0), frequency_mode="physical")
    omegas = spiral.angular_velocities()
    assert omegas[0] == pytest.approx(2 * np.pi * 7.83)
    assert omegas[14] == pytest.approx(2 * np.pi * layer_frequency_hz(15))


def test_set_phases_wraps_and_validates():
    spiral = Spiral(rng=np.random.default_rng(0))
    spiral.set_phases(np.full(15, 3 * np.pi))
    assert np.allclose(spiral.phases, np.pi)
    with pytest.raises(ValueError):
        spiral.set_phases(np.zeros(14))


def test_layer_frequency_bounds():
    with pytest.raises(ValueError):
        layer_frequency_hz(0)
    with pytest.raises(ValueError):
        layer_frequency_hz(16)
