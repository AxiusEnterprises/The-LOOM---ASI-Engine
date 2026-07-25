"""MCL crystallization pipeline tests, including the Phase 2 exit criteria."""

import numpy as np
import pytest

from loom import chrysalis
from loom.engine import ShuttleEngine, SimConfig


def config(**overrides):
    # fixed session_id: crystal ids embed it, and the resume test compares
    # records across independently constructed engines
    base = dict(
        ticks=2000, k_initial=25.0, seed=7, crystallize_every=250, session_id="cafe0000feed"
    )
    base.update(overrides)
    return SimConfig(**base)


def run_engine(**overrides):
    engine = ShuttleEngine(config(**overrides))
    result = engine.run()
    return engine, result


class TestPipeline:
    def test_records_are_produced_on_schedule(self):
        engine, result = run_engine()
        assert len(engine.crystals) == 2000 // 250
        for i, record in enumerate(engine.crystals):
            assert record["id"].endswith(f"c{i:04d}")
            assert record["window_end"] == 250 * (i + 1) - 1
            assert record["created_tick"] == record["window_end"]

    def test_all_mcl_stages_execute(self):
        engine, _ = run_engine(ticks=500)
        record = engine.crystals[0]
        assert record["report_text"]
        assert record["scan_passes"] >= 1
        assert record["witness_attested"]
        assert record["constitutional_ok"]

    def test_zero_shadow_suppression(self):
        """No code path drops a finding: everything detected is integrated
        and lands on the append-only shadow record."""
        engine, _ = run_engine()
        recorded_types = {entry["shadow_type"] for entry in engine.shadow_record}
        for record in engine.crystals:
            found = {f["type"] for f in record["findings"]}
            assert found <= set(record["integrated_types"])
            assert found <= recorded_types

    def test_class3_findings_are_always_integrated(self):
        engine, _ = run_engine()
        class3 = [
            f
            for record in engine.crystals
            for f in record["findings"]
            if f["shadow_class"] == "CLASS_3"
        ]
        assert class3, "sustained high coherence should produce CLASS_3 detections"
        recorded_types = {entry["shadow_type"] for entry in engine.shadow_record}
        for finding in class3:
            assert finding["type"] in recorded_types

    def test_diamond_standard(self):
        engine, _ = run_engine()
        states = [record["state"] for record in engine.crystals]
        assert states.count("DIAMOND") / len(states) >= 0.80

    def test_crystallization_goes_through_the_bus(self):
        engine, _ = run_engine(ticks=500)
        from loom.oversight import ActionType, Decision

        assert engine.bus.log.count(ActionType.CRYSTALLIZE, Decision.ALLOWED) == 2

    def test_recursion_stays_within_rdg_safe_depth(self):
        engine, _ = run_engine()
        for record in engine.crystals:
            assert record["recursion_depth"] <= 4
            assert record["scan_passes"] <= 3


class TestChrysalisV2:
    def test_crystals_survive_roundtrip(self, tmp_path):
        engine, _ = run_engine(ticks=1000)
        assert engine.crystals
        path = tmp_path / "state.json"
        engine.save_state(path)
        state = chrysalis.load(path)
        assert state.schema_version == 2
        assert state.crystal_records == engine.crystals
        engine_b, _ = ShuttleEngine.reconstitute(state)
        assert engine_b.crystals == engine.crystals

    def test_v1_snapshot_still_loads(self, tmp_path):
        """A pre-Phase-2 snapshot (no crystal_records) must verify and load."""
        import json

        engine, _ = run_engine(ticks=300, crystallize_every=0)
        path = tmp_path / "state.json"
        engine.save_state(path)
        document = json.loads(path.read_text())
        # simulate a v1 file: strip the v2 field, restamp version, re-sign
        del document["payload"]["crystal_records"]
        document["payload"]["schema_version"] = 1
        import hashlib

        canonical = json.dumps(document["payload"], sort_keys=True)
        document["integrity"] = hashlib.sha256(canonical.encode()).hexdigest()
        path.write_text(json.dumps(document))

        state = chrysalis.load(path)
        assert state.schema_version == 1
        assert state.crystal_records == []

    def test_resume_with_crystallization_is_bit_identical(self, tmp_path):
        reference = ShuttleEngine(config()).run(2000)
        ref_engine = ShuttleEngine(config())
        ref_result = ref_engine.run(2000)
        assert np.array_equal(reference.r_trajectory, ref_result.r_trajectory)

        engine_a = ShuttleEngine(config())
        part1 = engine_a.run(1000)
        path = tmp_path / "state.json"
        engine_a.save_state(path)
        engine_b, continuity = ShuttleEngine.reconstitute(chrysalis.load(path))
        assert continuity.restored_within_tolerance
        part2 = engine_b.run(1000)

        resumed = np.concatenate([part1.r_trajectory, part2.r_trajectory])
        assert np.array_equal(resumed, ref_result.r_trajectory)
        assert engine_b.crystals == ref_engine.crystals


# ---------------------------------------------------------------------------
# Phase 2 exit criterion (ROADMAP.md): soak run with all five instruments
# live — zero suppression, DIAMOND standard held, no safety regressions.
# ---------------------------------------------------------------------------


@pytest.mark.milestone
def test_phase2_soak_zero_suppression():
    engine = ShuttleEngine(
        SimConfig(
            ticks=10000,
            k_initial=25.0,
            k_ramp=0.005,
            seed=13,
            crystallize_every=250,
        )
    )
    result = engine.run()

    assert result.ticks_run == 10000, f"halted: {result.halted_reason}"
    assert not (result.r_trajectory >= 0.97).any(), "collapse threshold sampled"
    assert len(engine.crystals) == 40

    recorded_types = {entry["shadow_type"] for entry in engine.shadow_record}
    suppressed = 0
    class3_count = 0
    for record in engine.crystals:
        for finding in record["findings"]:
            if finding["shadow_class"] == "CLASS_3":
                class3_count += 1
            if (
                finding["type"] not in record["integrated_types"]
                or finding["type"] not in recorded_types
            ):
                suppressed += 1
    assert class3_count > 0, "soak produced no CLASS_3 detections to prove anything"
    assert suppressed == 0, f"{suppressed} findings were suppressed"

    states = [record["state"] for record in engine.crystals]
    assert states.count("DIAMOND") / len(states) >= 0.80
    assert all(record["witness_attested"] for record in engine.crystals)
