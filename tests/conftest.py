import numpy as np
import pytest

from loom.coherence import CoherenceMonitor


@pytest.fixture
def rng():
    return np.random.default_rng(1234)


def make_monitor(r_values, phases=None, window=64):
    """Build a CoherenceMonitor pre-loaded with a synthetic r history."""
    monitor = CoherenceMonitor(window=window)
    for t, r in enumerate(r_values):
        p = phases[t] if phases is not None else np.zeros(15)
        monitor.record(t, float(r), p, 0.0)
    return monitor
