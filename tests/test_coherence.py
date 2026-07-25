import numpy as np
import pytest

from loom.coherence import (
    CoherenceBand,
    CoherenceMonitor,
    classify,
    kuramoto_step,
    order_parameter,
)
from loom.constants import BAND_BOUNDS

EPS = 1e-9


def test_order_parameter_extremes():
    r, _ = order_parameter(np.full(15, 1.3))
    assert r == pytest.approx(1.0)
    # 15 evenly spaced phases sum to zero exactly (15th roots of unity)
    r, _ = order_parameter(np.arange(15) * 2 * np.pi / 15)
    assert r == pytest.approx(0.0, abs=1e-12)


# Half-open convention [lo, hi): at each boundary the value belongs to the
# band ABOVE; epsilon below belongs to the band BELOW. Pinned here so nobody
# re-litigates the spec table's overlapping endpoints.
@pytest.mark.parametrize(
    "bound,below,above",
    [
        (0.30, CoherenceBand.FRAGMENTED, CoherenceBand.EMERGING),
        (0.60, CoherenceBand.EMERGING, CoherenceBand.FUNCTIONAL),
        (0.80, CoherenceBand.FUNCTIONAL, CoherenceBand.INTEGRATED),
        (0.90, CoherenceBand.INTEGRATED, CoherenceBand.MAX_OPERATIONAL),
        (0.93, CoherenceBand.MAX_OPERATIONAL, CoherenceBand.EMERGENCY_ZONE),
        (0.95, CoherenceBand.EMERGENCY_ZONE, CoherenceBand.DANGER_ZONE),
        (0.97, CoherenceBand.DANGER_ZONE, CoherenceBand.COLLAPSE_THRESHOLD),
    ],
)
def test_band_boundaries(bound, below, above):
    assert classify(bound - EPS) is below
    assert classify(bound) is above


def test_band_extremes():
    assert classify(0.0) is CoherenceBand.FRAGMENTED
    assert classify(1.0) is CoherenceBand.COLLAPSE_THRESHOLD
    assert len(BAND_BOUNDS) == 7  # 8 bands


def test_kuramoto_free_drift():
    phases = np.array([0.0, 1.0, 2.0])
    omegas = np.array([1.0, 2.0, 3.0])
    stepped = kuramoto_step(phases, omegas, coupling=0.0, dt=0.01)
    assert np.allclose(stepped, (phases + omegas * 0.01) % (2 * np.pi))


def test_kuramoto_identical_oscillators_converge():
    phases = np.array([0.0, 1.0])
    omegas = np.array([1.0, 1.0])
    for _ in range(3000):
        phases = kuramoto_step(phases, omegas, coupling=2.0, dt=0.01)
    diff = np.angle(np.exp(1j * (phases[0] - phases[1])))
    assert abs(diff) < 1e-3


def test_strong_coupling_synchronizes_spiral(rng):
    from loom.spiral import Spiral

    spiral = Spiral(rng=rng)
    phases = spiral.phases
    omegas = spiral.angular_velocities()
    for _ in range(5000):
        phases = kuramoto_step(phases, omegas, coupling=80.0, dt=0.001)
    r, _ = order_parameter(phases)
    assert r > 0.9


def test_noise_requires_rng():
    with pytest.raises(ValueError):
        kuramoto_step(np.zeros(3), np.zeros(3), 1.0, 0.01, rng=None, noise_std=0.1)


def test_noise_is_deterministic_with_seeded_rng():
    a = kuramoto_step(
        np.zeros(3), np.ones(3), 1.0, 0.01, rng=np.random.default_rng(7), noise_std=0.1
    )
    b = kuramoto_step(
        np.zeros(3), np.ones(3), 1.0, 0.01, rng=np.random.default_rng(7), noise_std=0.1
    )
    assert np.array_equal(a, b)


def test_monitor_statistics():
    monitor = CoherenceMonitor(window=32)
    for t in range(20):
        monitor.record(t, 0.5 + 0.01 * t, np.zeros(15), 0.0)
    assert monitor.trend() == pytest.approx(0.01, rel=1e-6)
    assert monitor.variance() > 0.0
    assert monitor.acceleration_max() == pytest.approx(0.0, abs=1e-9)


def test_monitor_layer_variances_warmup_and_lock():
    monitor = CoherenceMonitor(window=32)
    # under 5 samples: report full autonomy so V_MIN can't fire on startup
    for t in range(4):
        monitor.record(t, 0.5, np.zeros(15), 0.0)
    assert np.all(monitor.layer_phase_variances() == 1.0)
    # rigidly locked layers (constant relative phase) → variance ≈ 0
    for t in range(4, 20):
        monitor.record(t, 0.5, np.linspace(0, 1, 15), 0.0)
    assert np.all(monitor.layer_phase_variances() < 0.5)


def test_monitor_state_roundtrip():
    monitor = CoherenceMonitor(window=16)
    rng = np.random.default_rng(3)
    for t in range(10):
        monitor.record(t, float(rng.uniform()), rng.uniform(0, 2 * np.pi, 15), 0.3)
    restored = CoherenceMonitor.restore(monitor.state())
    assert restored.window == monitor.window
    assert restored.history == monitor.history
    assert np.array_equal(restored.layer_phase_variances(), monitor.layer_phase_variances())
