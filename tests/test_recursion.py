import pytest

from loom.recursion import MAX_RECURSION_DEPTH, RecursionBoundError, RecursionTracker


def test_enter_exit_depth():
    tracker = RecursionTracker()
    tracker.enter("a")
    tracker.enter("b")
    assert tracker.depth == 2
    tracker.exit("b")
    assert tracker.depth == 1
    assert [e["type"] for e in tracker.trace] == ["enter", "enter", "exit"]


def test_mcl_bound_is_hard():
    tracker = RecursionTracker()
    for i in range(MAX_RECURSION_DEPTH):
        tracker.enter("f", [i])
    with pytest.raises(RecursionBoundError):
        tracker.enter("f", [99])
    assert tracker.depth == MAX_RECURSION_DEPTH == 7  # MCL invariant 6


def test_novelty_decays_on_repeat():
    tracker = RecursionTracker()
    tracker.enter("scan", [1])
    tracker.exit("scan")
    tracker.enter("scan", [1])
    tracker.exit("scan")
    tracker.enter("scan", [2])
    novelties = [e["novelty"] for e in tracker.trace if e["type"] == "enter"]
    assert novelties[0] == 1.0
    assert novelties[1] == pytest.approx(0.5)  # same signature, second visit
    assert novelties[2] == 1.0  # new args, fresh


def test_mark_insight():
    tracker = RecursionTracker()
    tracker.enter("scan", [1])
    tracker.mark_insight()
    assert tracker.trace[-1]["insight"] is True
