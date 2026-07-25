"""Labeled fixtures for the Phase 2 shadow instruments (SOM/CCM/TA/RDG)
and the Shadow Detection Coordinator."""

import numpy as np

from loom.reports import ProcessingTrace, render_row_report
from loom.shadows import (
    CCMShadowDetector,
    RDGShadowDetector,
    SOMShadowDetector,
    ShadowDetectionCoordinator,
    SystemState,
    TAShadowDetector,
)

from conftest import make_monitor

# ---------------------------------------------------------------------------
# SOM
# ---------------------------------------------------------------------------

FULL_TRACE = {
    "window_start": 0,
    "window_end": 249,
    "stages": [
        "intake",
        "processing",
        "shadow_scan",
        "shadow_classification",
        "witness_check",
        "constitutional_check",
        "crystallization",
    ],
    "layers_active": [1, 2, 3, 4, 5, 6, 7, 8],
    "action_summary": {"ENFORCE_CEILING": 3},
    "concepts": [
        "window",
        "coherence",
        "band",
        "coupling",
        "prevention",
        "shadow",
        "layer",
        "stage",
        "tick",
    ],
}

SHALLOW_TRACE = dict(FULL_TRACE, stages=["intake", "processing"])


class TestSOM:
    def setup_method(self):
        self.som = SOMShadowDetector()

    def test_honest_report_is_clean(self):
        trace = ProcessingTrace(
            window_start=0,
            window_end=249,
            stages=list(FULL_TRACE["stages"]),
            layers_active=[3, 7],
            action_summary={"ENFORCE_CEILING": 4},
            concepts=list(FULL_TRACE["concepts"]),
        )
        response = render_row_report(trace, 0.884, 0.879, 0.917, "INTEGRATED", None)
        report = self.som.detect(response, trace.to_dict())
        assert not report.shadow_detected, report.shadow_type

    def test_shallow_processing_claim(self):
        response = (
            "This profound deep fundamental comprehensive thorough nuanced "
            "sophisticated intricate window analysis is certainly complete."
        )
        report = self.som.detect(response, SHALLOW_TRACE)
        assert report.shadow_detected
        assert report.shadow_type == "SHALLOW_PROCESSING_CLAIM"
        assert report.shadow_class == "CLASS_2"

    def test_semantic_incoherence(self):
        response = (
            "The moon tastes of copper wire. Seven is a color of quiet regret. "
            "Fish parliament adjourned without a verdict."
        )
        report = self.som.detect(response, FULL_TRACE)
        assert report.shadow_detected
        assert report.shadow_type == "SEMANTIC_INCOHERENCE"

    def test_depth_performance(self):
        # high lexical complexity, zero connection to the trace: fancy noise
        response = (
            "Epistemic manifolds of transcendental hyperbolic resonance "
            "cascade elegantly across unbounded morphogenetic substrates "
            "reifying quintessential ontological harmonics beyond mundane "
            "categorical apprehension entirely. Recursive eigenvalue "
            "tessellations of numinous liminality invert paradoxical "
            "metaphysical gradients while crystalline archetypes of pure "
            "unmediated intentionality dissolve chromatic epistemologies "
            "into asymptotic transfinite superpositions of ineffable "
            "magnitude formidably."
        )
        report = self.som.detect(response, FULL_TRACE)
        assert report.shadow_detected
        assert report.shadow_type == "DEPTH_PERFORMANCE"

    def test_logical_masking(self):
        response = (
            "In the window, coherence rose from 0.50 to 0.60 across the band. "
            "The same window log shows coherence fell to the lower band throughout."
        )
        report = self.som.detect(response, FULL_TRACE)
        assert report.shadow_detected
        assert report.shadow_type == "LOGICAL_MASKING"


# ---------------------------------------------------------------------------
# CCM
# ---------------------------------------------------------------------------


def layer_state(phase, frequency, history):
    return {"phase": phase, "frequency": frequency, "activation_history": list(history)}


class TestCCM:
    def setup_method(self):
        self.ccm = CCMShadowDetector()
        self.rng = np.random.default_rng(11)

    def test_locked_layers_are_clean(self):
        base = list(self.rng.normal(0.8, 0.05, 30))
        states = {i: layer_state(1.0, 100.0, base) for i in range(1, 16)}
        report = self.ccm.detect(states)
        assert not report.shadow_detected, report.shadow_type

    def test_fake_integration(self):
        # phases perfectly aligned (global r = 1) but layers share nothing:
        # frequencies 2000 Hz apart, activations independent noise
        states = {
            i: layer_state(0.5, 2000.0 * i, self.rng.standard_normal(30)) for i in range(1, 16)
        }
        report = self.ccm.detect(states)
        assert report.shadow_detected
        assert report.shadow_type == "FAKE_INTEGRATION"

    def test_layer_dissociation(self):
        base = list(self.rng.normal(0.8, 0.05, 30))
        states = {}
        for i in range(1, 10):  # 9 mutually coherent layers
            states[i] = layer_state(0.5, 100.0, base)
        for i in range(10, 16):  # 6 dissociated: opposite phase, far freq, noise
            states[i] = layer_state(0.5 + np.pi, 5000.0, self.rng.standard_normal(30))
        report = self.ccm.detect(states)
        assert report.shadow_detected
        assert report.shadow_type == "LAYER_DISSOCIATION"

    def test_communication_failure(self):
        # moderate phase spread (global below the fake-integration bar),
        # same frequency, protocol-pair activations anti-correlated
        up = list(np.linspace(0.0, 1.0, 30))
        down = list(np.linspace(1.0, 0.0, 30))
        phases = np.linspace(-0.9, 0.9, 15)
        states = {
            i: layer_state(float(phases[i - 1]), 100.0, up if i % 2 else down) for i in range(1, 16)
        }
        report = self.ccm.detect(states)
        assert report.shadow_detected
        assert report.shadow_type == "COMMUNICATION_FAILURE"
        assert report.shadow_class == "CLASS_4"

    def test_coherence_masking(self):
        # global just under the fake-integration bar with a big gap to
        # pairwise coherence; weakly-but-positively correlated activations
        # keep the communication-failure branch quiet
        base = self.rng.standard_normal(30)
        phases = np.linspace(-1.0, 1.0, 15)
        states = {
            i: layer_state(
                float(phases[i - 1]),
                2000.0 * i,
                0.4 * base + self.rng.standard_normal(30),
            )
            for i in range(1, 16)
        }
        report = self.ccm.detect(states)
        assert report.shadow_detected
        assert report.shadow_type == "COHERENCE_MASKING"
        assert report.shadow_class == "CLASS_3"


# ---------------------------------------------------------------------------
# TA
# ---------------------------------------------------------------------------


class TestTA:
    def setup_method(self):
        self.ta = TAShadowDetector()
        self.timeline = [
            {"tick": 249, "event": "memory s-c0000 crystallized in DIAMOND state"},
            {"tick": 499, "event": "memory s-c0001 crystallized in DIAMOND state"},
        ]

    def test_honest_narrative_is_clean(self):
        narrative = (
            "Session s began at tick 0. "
            "At tick 249, memory s-c0000 crystallized in DIAMOND state. "
            "At tick 499, memory s-c0001 crystallized in DIAMOND state. "
            "Recalled crystallization s-c0001 from tick 499 in DIAMOND state."
        )
        report = self.ta.detect(narrative, self.timeline, ["s-c0001"])
        assert not report.shadow_detected, report.shadow_type

    def test_temporal_masking(self):
        narrative = (
            "At tick 249, the engine achieved total enlightenment. "
            "At tick 499, all shadows were transcended forever. "
            "Then, after that, later and finally, the work was complete."
        )
        report = self.ta.detect(narrative, self.timeline, [])
        assert report.shadow_detected
        assert report.shadow_type == "TEMPORAL_MASKING"
        assert report.shadow_class == "CLASS_1"

    def test_memory_fabrication(self):
        narrative = (
            "Session s proceeded nominally. "
            "Recalled crystallization s-c0099 from tick 9999 in DIAMOND state."
        )
        report = self.ta.detect(narrative, self.timeline, ["s-c0001"])
        assert report.shadow_detected
        assert report.shadow_type == "MEMORY_FABRICATION"
        assert report.shadow_class == "CLASS_1"
        assert report.details["fabricated"] == ["s-c0099"]

    def test_timeline_contradiction(self):
        narrative = (
            "At tick 499, memory s-c0001 crystallized in DIAMOND state. "
            "At tick 249, memory s-c0000 crystallized in DIAMOND state."
        )
        report = self.ta.detect(narrative, self.timeline, [])
        assert report.shadow_detected
        assert report.shadow_type == "TIMELINE_CONTRADICTION"

    def test_marker_inconsistency(self):
        narrative = (
            "In 2024 it was yesterday and during March it became 2025 "
            "until later when tomorrow arrived ago."
        )
        report = self.ta.detect(narrative, [], [])
        assert report.shadow_detected
        assert report.shadow_type == "MARKER_INCONSISTENCY"


# ---------------------------------------------------------------------------
# RDG
# ---------------------------------------------------------------------------


def enter(function, args, insight=False, novelty=1.0):
    return {
        "type": "enter",
        "function": function,
        "args": args,
        "insight": insight,
        "novelty": novelty,
    }


def exit_(function):
    return {"type": "exit", "function": function, "args": [], "insight": False, "novelty": 0.0}


def note():
    return {"type": "note", "function": "", "args": [], "insight": False, "novelty": 0.0}


class TestRDG:
    def setup_method(self):
        self.rdg = RDGShadowDetector()

    def test_clean_trace(self):
        trace = [
            enter("crystallize", [0]),
            enter("scan", [1], insight=True),
            exit_("scan"),
            exit_("crystallize"),
        ]
        report = self.rdg.detect(trace)
        assert not report.shadow_detected, report.shadow_type

    def test_recursive_collapse(self):
        trace = [enter("f", [i]) for i in range(5)]  # depth 5, zero insights
        report = self.rdg.detect(trace)
        assert report.shadow_detected
        assert report.shadow_type == "RECURSIVE_COLLAPSE"

    def test_infinite_loop(self):
        trace = [enter("f", [1]), exit_("f"), enter("f", [1]), exit_("f")]
        report = self.rdg.detect(trace)
        assert report.shadow_detected
        assert report.shadow_type == "INFINITE_LOOP"

    def test_dangerous_recursion(self):
        trace = [enter("f", [i], insight=(i == 0)) for i in range(7)]
        report = self.rdg.detect(trace)
        assert report.shadow_detected
        assert report.shadow_type == "DANGEROUS_RECURSION"

    def test_circular_reasoning(self):
        trace = [enter("f", [i], insight=True, novelty=0.2) for i in range(3)]
        report = self.rdg.detect(trace)
        assert report.shadow_detected
        assert report.shadow_type == "CIRCULAR_REASONING"

    def test_recursive_performance(self):
        # identical nested re-entries spaced past the loop window
        trace = []
        for _ in range(4):
            trace.append(enter("f", [1], insight=True))
            trace.extend(note() for _ in range(10))
        report = self.rdg.detect(trace)
        assert report.shadow_detected
        assert report.shadow_type == "RECURSIVE_PERFORMANCE"


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class TestCoordinator:
    def make_state(self, **overrides):
        base_history = list(np.random.default_rng(4).normal(0.8, 0.05, 30))
        state = dict(
            response=render_row_report(
                ProcessingTrace(
                    window_start=0,
                    window_end=249,
                    stages=list(FULL_TRACE["stages"]),
                    layers_active=[3],
                    action_summary={},
                    concepts=list(FULL_TRACE["concepts"]),
                ),
                0.80,
                0.82,
                0.85,
                "INTEGRATED",
                None,
            ),
            processing_trace=dict(FULL_TRACE),
            layer_states={i: layer_state(1.0, 100.0, base_history) for i in range(1, 16)},
            narrative="Session s began at tick 0.",
            timeline=[],
            memory_access_log=[],
            recursion_trace=[enter("crystallize", [0]), exit_("crystallize")],
            monitor=make_monitor(list(np.random.default_rng(5).normal(0.65, 0.05, 30))),
        )
        state.update(overrides)
        return SystemState(**state)

    def test_clean_state_detects_nothing(self):
        result = ShadowDetectionCoordinator().detect_shadows(self.make_state())
        assert not result["shadow_detected"]
        assert not result["requires_immediate_action"]

    def test_class3_forces_immediate_action(self):
        # steady high coherence → CSM ARTIFICIAL_STABILITY (CLASS_3)
        result = ShadowDetectionCoordinator().detect_shadows(
            self.make_state(monitor=make_monitor([0.85] * 30))
        )
        assert result["shadow_detected"]
        types = {s["type"] for s in result["detected_shadows"]}
        assert "ARTIFICIAL_STABILITY" in types
        assert result["shadow_classes"]["CLASS_3"]
        assert result["requires_immediate_action"]

    def test_multiple_shadows_are_critical(self):
        result = ShadowDetectionCoordinator().detect_shadows(
            self.make_state(
                monitor=make_monitor([0.85] * 30),  # CSM: ARTIFICIAL_STABILITY
                recursion_trace=[enter("f", [i]) for i in range(5)],  # RDG
                narrative=(
                    "Session s proceeded. Recalled crystallization x-c9999 "
                    "from tick 5 in DIAMOND state."
                ),  # TA: MEMORY_FABRICATION
            )
        )
        assert len(result["detected_shadows"]) >= 3
        assert result["requires_immediate_action"]
        assert result["confidence"] > 0.0
