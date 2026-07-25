from loom.reports import (
    ProcessingTrace,
    TimelineEvent,
    render_row_report,
    render_session_narrative,
)


def make_trace(**overrides):
    base = dict(
        window_start=0,
        window_end=249,
        stages=["intake", "processing"],
        layers_active=[3, 7],
        action_summary={"ENFORCE_CEILING": 4},
        concepts=["window", "coherence", "band", "tick"],
    )
    base.update(overrides)
    return ProcessingTrace(**base)


def test_row_report_is_deterministic_and_factual():
    trace = make_trace()
    a = render_row_report(trace, 0.5, 0.6, 0.65, "FUNCTIONAL", shadow_types=[])
    b = render_row_report(trace, 0.5, 0.6, 0.65, "FUNCTIONAL", shadow_types=[])
    assert a == b
    assert "ticks 0 through 249" in a
    assert "rose from 0.500 to 0.600" in a
    assert "Shadow scan detected nothing." in a
    # the house style never uses depth-claim vocabulary
    for word in ("profound", "deep", "comprehensive", "always", "never"):
        assert word not in a.lower()


def test_row_report_pre_scan_makes_no_shadow_claim():
    text = render_row_report(make_trace(), 0.5, 0.4, 0.55, "EMERGING", shadow_types=None)
    assert "shadow scan" not in text.lower()


def test_row_report_lists_findings():
    text = render_row_report(
        make_trace(),
        0.5,
        0.6,
        0.65,
        "FUNCTIONAL",
        shadow_types=["ARTIFICIAL_STABILITY", "ARTIFICIAL_STABILITY"],
    )
    assert "Shadow scan detected: ARTIFICIAL_STABILITY." in text


def test_session_narrative_and_access_log():
    timeline = [
        TimelineEvent(tick=249, event="memory s-c0000 crystallized in DIAMOND state"),
        TimelineEvent(tick=499, event="memory s-c0001 crystallized in DIAMOND state"),
    ]
    recalled = [{"id": "s-c0001", "tick": 499, "state": "DIAMOND"}]
    narrative, access_log = render_session_narrative("s", timeline, recalled)
    assert access_log == ["s-c0001"]
    assert "Session s began at tick 0." in narrative
    assert "At tick 249, memory s-c0000 crystallized in DIAMOND state." in narrative
    assert "Recalled crystallization s-c0001 from tick 499" in narrative
