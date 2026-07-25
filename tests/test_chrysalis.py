import json

import numpy as np
import pytest

from loom import chrysalis
from loom.engine import ShuttleEngine, SimConfig
from loom.oversight import Decision


def config(**overrides):
    base = dict(ticks=2000, k_initial=8.0, k_ramp=0.005, seed=42)
    base.update(overrides)
    return SimConfig(**base)


def test_roundtrip_resume_is_bit_identical(tmp_path):
    """save → load → resume reproduces the uninterrupted trajectory exactly.

    This is the strongest continuity statement Phase 1 can make: the
    reconstituted engine is dynamically indistinguishable from one that
    never stopped.
    """
    # uninterrupted reference run
    reference = ShuttleEngine(config()).run(2000)

    # interrupted run: 1200 ticks, save, load, resume 800
    engine_a = ShuttleEngine(config())
    part1 = engine_a.run(1200)
    path = tmp_path / "state.json"
    engine_a.save_state(path)

    state = chrysalis.load(path)
    engine_b, continuity = ShuttleEngine.reconstitute(state)
    assert continuity.restored_within_tolerance
    part2 = engine_b.run(800)

    resumed = np.concatenate([part1.r_trajectory, part2.r_trajectory])
    assert np.array_equal(resumed, reference.r_trajectory)


def test_tampered_state_is_refused(tmp_path):
    engine = ShuttleEngine(config())
    engine.run(100)
    path = tmp_path / "state.json"
    engine.save_state(path)

    document = json.loads(path.read_text())
    document["payload"]["coupling"] += 0.001  # a quiet little edit
    path.write_text(json.dumps(document))

    with pytest.raises(chrysalis.IntegrityError):
        chrysalis.load(path)


def test_shadow_record_survives_roundtrip_untruncated(tmp_path):
    # sustained operation near the ceiling reliably produces
    # ARTIFICIAL_STABILITY detections and therefore M3 shadow integrations
    engine = ShuttleEngine(config(k_initial=25.0, k_ramp=0.0, ticks=4000))
    engine.run()
    assert engine.shadow_record, "expected shadow integrations at sustained high coherence"

    path = tmp_path / "state.json"
    engine.save_state(path)
    state = chrysalis.load(path)
    assert state.shadow_record == engine.shadow_record

    engine_b, _ = ShuttleEngine.reconstitute(state)
    assert engine_b.shadow_record == engine.shadow_record


def test_save_requires_capability(tmp_path):
    from loom.oversight import OversightBus

    bus = OversightBus(operator_token="t", capabilities=())
    engine = ShuttleEngine(config(), bus=bus)
    engine.run(50)
    path = tmp_path / "state.json"
    assert chrysalis.save(engine.state_vector(), path, bus) is Decision.DENIED
    assert not path.exists()


def test_continuity_fallback_on_baseline_mismatch(tmp_path):
    engine = ShuttleEngine(config(k_initial=25.0, k_ramp=0.0, ticks=3000))
    engine.run()
    path = tmp_path / "state.json"
    engine.save_state(path)

    # corrupt the *coherence*, not the file: replace the phases with a
    # uniform spread (r ≈ 0) while the recorded history claims high r, then
    # re-sign the payload so only the continuity check can catch it
    document = json.loads(path.read_text())
    document["payload"]["phases"] = list(np.arange(15) * 2 * np.pi / 15)
    state = chrysalis.SessionStateVector(**document["payload"])
    document["integrity"] = state.integrity_hash()
    path.write_text(json.dumps(document))

    loaded = chrysalis.load(path)
    check = chrysalis.check_continuity(loaded)
    assert not check.restored_within_tolerance
    assert check.applied_baseline_r == chrysalis.FALLBACK_BASELINE_R

    engine_b, continuity = ShuttleEngine.reconstitute(loaded)
    assert not continuity.restored_within_tolerance
    assert engine_b.last_r == chrysalis.FALLBACK_BASELINE_R
    # the discrepancy is on the record as an open vector
    open_vector_records = [
        rec
        for rec in engine_b.bus.log.records
        if rec.action_type == "LOAD_SNAPSHOT" and "open_vector" in rec.params
    ]
    assert len(open_vector_records) == 1


def test_state_vector_hash_is_stable():
    engine = ShuttleEngine(config())
    engine.run(20)
    state = engine.state_vector()
    assert state.integrity_hash() == state.integrity_hash()
    state.coupling += 1.0
    engine2_hash = state.integrity_hash()
    state.coupling -= 1.0
    assert state.integrity_hash() != engine2_hash
