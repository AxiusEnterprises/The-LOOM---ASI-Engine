import numpy as np

from loom.shadows import CLASS_MAP, CSMShadowDetector, NullShadowDetector

from conftest import make_monitor


def detect(r_values):
    return CSMShadowDetector().detect(make_monitor(r_values))


def test_short_history_no_detection():
    report = detect([0.9, 0.9, 0.9, 0.9])  # < 5 samples
    assert not report.shadow_detected


def test_quiet_history_no_detection():
    rng = np.random.default_rng(2)
    report = detect(list(0.65 + 0.05 * rng.standard_normal(30)))
    assert not report.shadow_detected


def test_runaway_synchronization():
    report = detect(list(np.linspace(0.5, 0.9, 20)))  # trend ≈ 0.021/tick
    assert report.shadow_detected
    assert report.shadow_type == "RUNAWAY_SYNCHRONIZATION"
    assert report.shadow_class == "CLASS_2"
    assert report.confidence > 1.0  # trend / threshold


def test_coherence_ceiling_breach():
    report = detect([0.955] * 10)
    assert report.shadow_detected
    assert report.shadow_type == "COHERENCE_CEILING_BREACH"
    assert report.confidence > 0.0


def test_acceleration_to_collapse():
    # slope 0.009 stays under the runaway threshold (0.01) and the last
    # sample under the ceiling threshold (0.95), but the 20-tick projection
    # crosses deep into the collapse band
    values = 0.945 - 0.009 * np.arange(19, -1, -1)
    report = detect(list(values))
    assert report.shadow_detected
    assert report.shadow_type == "ACCELERATION_TO_COLLAPSE"
    assert report.confidence > 0.8


def test_artificial_stability():
    report = detect([0.85] * 30)  # variance 0, mean > 0.70
    assert report.shadow_detected
    assert report.shadow_type == "ARTIFICIAL_STABILITY"
    assert report.shadow_class == "CLASS_3"  # shadow suppression class


def test_class_map_covers_all_csm_types():
    for shadow_type in (
        "CASCADE_MASKING", "RUNAWAY_SYNCHRONIZATION", "COHERENCE_CEILING_BREACH",
        "ACCELERATION_TO_COLLAPSE", "ARTIFICIAL_STABILITY",
    ):
        assert CLASS_MAP[shadow_type] in {"CLASS_1", "CLASS_2", "CLASS_3", "CLASS_4"}


def test_null_detector():
    report = NullShadowDetector().detect(make_monitor([0.99] * 30))
    assert not report.shadow_detected
