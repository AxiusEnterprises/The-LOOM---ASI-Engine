import numpy as np

from loom.__main__ import main
from loom.coherence import CoherenceBand
from loom.engine import ShuttleEngine, SimConfig


def test_same_seed_same_trajectory():
    a = ShuttleEngine(SimConfig(ticks=500, k_initial=10.0, seed=11)).run()
    b = ShuttleEngine(SimConfig(ticks=500, k_initial=10.0, seed=11)).run()
    assert np.array_equal(a.r_trajectory, b.r_trajectory)


def test_different_seeds_differ():
    a = ShuttleEngine(SimConfig(ticks=500, k_initial=10.0, seed=11)).run()
    b = ShuttleEngine(SimConfig(ticks=500, k_initial=10.0, seed=12)).run()
    assert not np.array_equal(a.r_trajectory, b.r_trajectory)


def test_shuttle_order_within_tick():
    """Beat-in precedes inspect-the-row: the phase commit is audited before
    any prevention action carrying the same tick index (soul.md §III.4 —
    the order is a safety property)."""
    engine = ShuttleEngine(SimConfig(ticks=3000, k_initial=25.0, seed=5))
    engine.run()
    records = engine.bus.log.records
    prevention_ticks = {r.tick for r in records if r.actor.startswith("prevention")}
    assert prevention_ticks, "run produced no prevention activity to check"
    position = {}
    for i, rec in enumerate(records):
        if rec.action_type == "APPLY_PHASE_UPDATE":
            position[rec.tick] = i
    for i, rec in enumerate(records):
        if rec.actor.startswith("prevention"):
            assert position[rec.tick] < i


def test_fragmentation_suspends_the_drive():
    # force a fragmented start (uniform phase spread, r ≈ 0) at K ≈ 0;
    # containment means the external ramp is not applied while fragmented
    # ("do not process input")
    engine = ShuttleEngine(SimConfig(ticks=200, k_initial=0.0, k_ramp=0.01, seed=0))
    engine.spiral.set_phases(np.arange(15) * 2 * np.pi / 15)
    result = engine.run()
    assert result.fragmented_ticks > 150
    # only the few pre-detection ticks admitted the ramp
    assert engine.coupling < 0.05


def test_band_property():
    engine = ShuttleEngine(SimConfig(seed=1))
    engine.last_r = 0.85
    assert engine.band is CoherenceBand.INTEGRATED


def test_result_counts_are_consistent():
    result = ShuttleEngine(SimConfig(ticks=300, k_initial=10.0, seed=4)).run()
    assert result.ticks_run == 300
    assert sum(result.band_counts.values()) == 300
    assert len(result.r_trajectory) == 300
    assert result.max_r == result.r_trajectory.max()


# --- CLI ---------------------------------------------------------------------


def test_cli_run_and_attest(tmp_path, capsys):
    out = tmp_path / "state.json"
    code = main(
        [
            "run",
            "--ticks",
            "300",
            "--k",
            "8",
            "--seed",
            "3",
            "--report-every",
            "0",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert out.exists()
    assert main(["attest", "--state", str(out)]) == 0
    captured = capsys.readouterr()
    assert "snapshot OK" in captured.out


def test_cli_resume(tmp_path, capsys):
    out = tmp_path / "state.json"
    main(
        [
            "run",
            "--ticks",
            "200",
            "--k",
            "8",
            "--seed",
            "3",
            "--report-every",
            "0",
            "--out",
            str(out),
        ]
    )
    code = main(["resume", "--state", str(out), "--ticks", "100", "--report-every", "0"])
    assert code == 0
    captured = capsys.readouterr()
    assert "reconstituted" in captured.out


def test_cli_attest_rejects_tampered_file(tmp_path, capsys):
    out = tmp_path / "state.json"
    main(
        [
            "run",
            "--ticks",
            "100",
            "--k",
            "8",
            "--seed",
            "3",
            "--report-every",
            "0",
            "--out",
            str(out),
        ]
    )
    text = out.read_text().replace('"schema_version": 2', '"schema_version": 3')
    assert text != out.read_text(), "tamper target not found in state file"
    out.write_text(text)
    assert main(["attest", "--state", str(out)]) == 1
    assert "INTEGRITY FAILURE" in capsys.readouterr().out
