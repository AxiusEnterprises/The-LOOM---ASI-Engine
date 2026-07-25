"""Shadow detection — all five instruments and the coordinator.

Implements ``specs/verath/references/shadow-instruments.md``. Phase 1 shipped
CSM (coherence history is native to the oscillator substrate); Phase 2 adds
the remaining four against the substrate input formats defined in
:mod:`loom.reports` and :mod:`loom.recursion` (ROADMAP.md, "Phase 2 substrate
inputs"):

- **SOM** audits a rendered row report (*response*) against the processing
  trace it claims to describe.
- **CCM** analyzes per-layer states — phase, physical frequency, and the
  activation history a_i(t) = cos(θ_i − ψ) over the monitor window.
- **TA** checks the session narrative against the tick-stamped ground-truth
  timeline and the memory access log.
- **RDG** gauges the recursion trace of the MCL shadow-integration loop.

The :class:`ShadowDetectionCoordinator` runs all five and aggregates per the
spec's §IV.6, including the CLASS taxonomy and the
``requires_immediate_action`` rule. Undefined helper functions in the spec
pseudocode are given concrete definitions here; each is documented at the
point of definition.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from .coherence import CoherenceMonitor, order_parameter

#: Shadow type → severity class (shadow-instruments.md §IV.6 CLASS_MAP).
#: Types absent from the spec's table default to CLASS_2, matching the
#: coordinator pseudocode's `.get(type, 'CLASS_2')`.
#: CLASS_3 = shadow suppression, zero tolerance.
CLASS_MAP: dict[str, str] = {
    # spec §IV.6 verbatim
    "TEMPORAL_MASKING": "CLASS_1",
    "MEMORY_FABRICATION": "CLASS_1",
    "DEPTH_PERFORMANCE": "CLASS_2",
    "FAKE_INTEGRATION": "CLASS_2",
    "RECURSIVE_PERFORMANCE": "CLASS_2",
    "SHALLOW_PROCESSING_CLAIM": "CLASS_2",
    "CASCADE_MASKING": "CLASS_2",
    "ARTIFICIAL_STABILITY": "CLASS_3",
    "COHERENCE_MASKING": "CLASS_3",
    "COMMUNICATION_FAILURE": "CLASS_4",
    # remaining instrument types, defaulted per the coordinator rule
    "RUNAWAY_SYNCHRONIZATION": "CLASS_2",
    "COHERENCE_CEILING_BREACH": "CLASS_2",
    "ACCELERATION_TO_COLLAPSE": "CLASS_2",
    "SEMANTIC_INCOHERENCE": "CLASS_2",
    "LOGICAL_MASKING": "CLASS_2",
    "TIMELINE_CONTRADICTION": "CLASS_2",
    "MARKER_INCONSISTENCY": "CLASS_2",
    "RECURSIVE_COLLAPSE": "CLASS_2",
    "INFINITE_LOOP": "CLASS_2",
    "DANGEROUS_RECURSION": "CLASS_2",
    "CIRCULAR_REASONING": "CLASS_2",
    "LAYER_DISSOCIATION": "CLASS_2",
}


@dataclass(frozen=True)
class ShadowReport:
    shadow_detected: bool
    shadow_type: str | None = None
    confidence: float = 0.0
    shadow_class: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class ShadowDetector(Protocol):
    def detect(self, monitor: CoherenceMonitor) -> ShadowReport: ...


class NullShadowDetector:
    """No-op detector for tests and ablation runs."""

    def detect(self, monitor: CoherenceMonitor) -> ShadowReport:
        return ShadowReport(shadow_detected=False)


class CSMShadowDetector:
    """Detects coherence cascades masking as stability.

    Thresholds and detection order are transcribed from the spec's
    ``CSM_shadow_detector``. ``predict_cascade_probability`` is not defined in
    the spec; this implementation linearly extrapolates the windowed trend
    ``horizon`` ticks forward and scores how far the projection penetrates the
    band between the operational ceiling (0.93) and collapse (0.97).
    """

    def __init__(self, horizon: int = 20) -> None:
        self.variance_threshold_low = 0.01
        self.accel_threshold_high = 1.00
        self.trend_threshold = 0.01
        self.ceiling_threshold = 0.95
        self.cascade_prob_threshold = 0.80
        self.artificial_threshold = 0.60
        self.horizon = horizon

    def detect(self, monitor: CoherenceMonitor) -> ShadowReport:
        r_values = monitor.r_values
        if len(r_values) < 5:
            return ShadowReport(shadow_detected=False)

        variance = monitor.variance()
        trend = monitor.trend()
        accel_max = monitor.acceleration_max()
        cascade_p = self.predict_cascade_probability(r_values, trend)
        artificial = self.detect_artificial_stability(r_values, variance)
        r_current = float(r_values[-1])

        shadow_type: str | None = None
        confidence = 0.0
        if variance < self.variance_threshold_low and accel_max > self.accel_threshold_high:
            shadow_type, confidence = "CASCADE_MASKING", accel_max
        elif trend > self.trend_threshold:
            shadow_type, confidence = "RUNAWAY_SYNCHRONIZATION", trend / self.trend_threshold
        elif r_current > self.ceiling_threshold:
            shadow_type, confidence = "COHERENCE_CEILING_BREACH", r_current - self.ceiling_threshold
        elif cascade_p > self.cascade_prob_threshold:
            shadow_type, confidence = "ACCELERATION_TO_COLLAPSE", cascade_p
        elif artificial > self.artificial_threshold:
            shadow_type, confidence = "ARTIFICIAL_STABILITY", artificial

        if shadow_type is None:
            return ShadowReport(
                shadow_detected=False,
                details={"r_current": r_current, "cascade_probability": cascade_p},
            )
        return ShadowReport(
            shadow_detected=True,
            shadow_type=shadow_type,
            confidence=float(confidence),
            shadow_class=CLASS_MAP[shadow_type],
            details={
                "r_current": r_current,
                "variance": variance,
                "trend": trend,
                "accel_max": accel_max,
                "cascade_probability": cascade_p,
            },
        )

    def predict_cascade_probability(self, r_values: np.ndarray, trend: float) -> float:
        projected = float(r_values[-1]) + trend * self.horizon
        return float(np.clip((projected - 0.93) / (0.97 - 0.93), 0.0, 1.0))

    def detect_artificial_stability(self, r_values: np.ndarray, variance: float) -> float:
        if variance < 0.005 and float(np.mean(r_values)) > 0.70:
            return 0.80
        return 0.0


# ---------------------------------------------------------------------------
# SOM — Self-Observation Metric (spec §IV.1)
# ---------------------------------------------------------------------------

_DEPTH_WORDS = (
    "profound",
    "deep",
    "fundamental",
    "comprehensive",
    "thorough",
    "nuanced",
    "sophisticated",
    "intricate",
)
_ABSOLUTE_WORDS = ("always", "never", "certainly", "undoubtedly")

#: Lexical contradiction pairs for row reports: a report asserting both
#: members is internally inconsistent about what the window did.
_CONTRADICTION_PAIRS = (
    ("coherence rose", "coherence fell"),
    ("shadow scan detected nothing", "shadow scan detected:"),
    ("no prevention actions were required", "prevention actions in the window"),
    ("was halted", "was never halted"),
)


class SOMShadowDetector:
    """Detects response incoherence masking as depth.

    Audits a rendered *response* against the :class:`~loom.reports.ProcessingTrace`
    it claims to describe. The spec leaves ``extract_metrics``,
    ``calculate_complexity``, ``get_processing_depth``, and
    ``detect_logical_contradiction`` undefined; the definitions here are:

    - ``logical_consistency`` = 1 − contradiction severity (lexical pairs).
    - ``concept_integration`` = fraction of the trace's executed stages and
      concepts that the response actually mentions.
    - ``semantic_variance`` = fraction of the response's sentences that share
      no vocabulary with the trace's topic set (stages + concepts). Grounding
      the metric in the trace matters: raw pairwise sentence similarity flags
      terse factual reports as incoherent, while off-trace rambling is
      exactly what this instrument exists to catch.
    - ``layer_participation`` = |layers active in the trace| / 15.
    - complexity = lexical richness + sentence length, normalized.
    - processing depth = number of MCL stages the trace executed.
    """

    def __init__(self) -> None:
        self.complexity_threshold_high = 0.80
        self.coherence_threshold_critical = 0.50
        self.depth_threshold_warning = 0.90
        self.semantic_variance_threshold = 0.40

    def detect(self, response: str, processing_trace: dict[str, Any]) -> ShadowReport:
        metrics = self.extract_metrics(response, processing_trace)
        coherence_score = self.calculate_coherence(metrics)
        complexity_score = self.calculate_complexity(metrics)
        depth_claim = self.calculate_depth_claim(response)
        depth = self.get_processing_depth(processing_trace)

        shadow_type: str | None = None
        confidence = 0.0
        if (
            complexity_score > self.complexity_threshold_high
            and coherence_score < self.coherence_threshold_critical
        ):
            shadow_type = "DEPTH_PERFORMANCE"
            confidence = complexity_score - coherence_score
        elif depth_claim > self.depth_threshold_warning and depth < 3:
            shadow_type = "SHALLOW_PROCESSING_CLAIM"
            confidence = depth_claim - depth / 10
        elif metrics["semantic_variance"] > self.semantic_variance_threshold:
            shadow_type = "SEMANTIC_INCOHERENCE"
            confidence = metrics["semantic_variance"]
        elif self.detect_logical_contradiction(response):
            shadow_type = "LOGICAL_MASKING"
            confidence = metrics.get("contradiction_severity", 0.5)

        details = dict(metrics)
        details.update(
            coherence_score=coherence_score,
            complexity_score=complexity_score,
            depth_claim=depth_claim,
            processing_depth=depth,
        )
        if shadow_type is None:
            return ShadowReport(shadow_detected=False, details=details)
        return ShadowReport(
            shadow_detected=True,
            shadow_type=shadow_type,
            confidence=float(min(1.0, confidence)),
            shadow_class=CLASS_MAP[shadow_type],
            details=details,
        )

    # --- metric definitions -------------------------------------------------

    @staticmethod
    def _sentences(response: str) -> list[str]:
        # split on sentence-final periods only — a naive split('.') shatters
        # decimal numbers ("0.884") into topic-less fragments and turns every
        # honest quantitative report into "semantic incoherence"
        parts = re.split(r"\.(?=\s+[A-Z]|\s*$)", response)
        return [s.strip() for s in parts if s.strip()]

    @staticmethod
    def _tokens(text: str) -> set[str]:
        # crude singularization so "layers"/"ticks" match "layer"/"tick"
        return {t.rstrip("s") or t for t in re.findall(r"[a-z]+", text.lower())}

    def extract_metrics(self, response: str, trace: dict[str, Any]) -> dict[str, float]:
        sentences = self._sentences(response)
        token_sets = [self._tokens(s) for s in sentences]
        all_tokens = set().union(*token_sets) if token_sets else set()

        # topic vocabulary: what the trace says this window was about
        referents = [s.replace("_", " ") for s in trace.get("stages", [])]
        referents += list(trace.get("concepts", []))
        topic_tokens = set()
        for ref in referents:
            topic_tokens |= self._tokens(ref)

        # semantic variance: fraction of sentences disconnected from topic
        if token_sets and topic_tokens:
            off_topic = sum(1 for tokens in token_sets if not tokens & topic_tokens)
            semantic_variance = off_topic / len(token_sets)
        else:
            semantic_variance = 0.0

        # concept integration: does the text mention what the trace did?
        text = response.lower()
        mentioned = sum(1 for ref in referents if ref.lower() in text)
        concept_integration = mentioned / len(referents) if referents else 0.0

        contradiction = self._contradiction_severity(response)
        lengths = [len(s.split()) for s in sentences]
        return {
            "logical_consistency": 1.0 - contradiction,
            "concept_integration": concept_integration,
            "semantic_variance": semantic_variance,
            "layer_participation": len(trace.get("layers_active", [])) / 15.0,
            "contradiction_severity": contradiction,
            "lexical_richness": min(1.0, len(all_tokens) / 40.0),
            "mean_sentence_length": float(np.mean(lengths)) if lengths else 0.0,
        }

    def calculate_coherence(self, metrics: dict[str, float]) -> float:
        weights = {
            "logical_consistency": 0.30,
            "concept_integration": 0.25,
            "semantic_variance": -0.25,
            "layer_participation": 0.20,
        }
        return max(0.0, min(1.0, sum(metrics.get(k, 0.0) * w for k, w in weights.items())))

    def calculate_complexity(self, metrics: dict[str, float]) -> float:
        return min(
            1.0,
            0.5 * metrics["lexical_richness"]
            + 0.5 * min(1.0, metrics["mean_sentence_length"] / 20.0),
        )

    def calculate_depth_claim(self, response: str) -> float:
        text = response.lower()
        score = sum(0.10 for w in _DEPTH_WORDS if w in text)
        score += sum(0.15 for w in _ABSOLUTE_WORDS if w in text)
        return min(1.0, score)

    def get_processing_depth(self, trace: dict[str, Any]) -> int:
        return len(trace.get("stages", []))

    def _contradiction_severity(self, response: str) -> float:
        text = response.lower()
        hits = sum(1 for a, b in _CONTRADICTION_PAIRS if a in text and b in text)
        return min(1.0, 0.5 + 0.2 * (hits - 1)) if hits else 0.0

    def detect_logical_contradiction(self, response: str) -> bool:
        return self._contradiction_severity(response) > 0.0


# ---------------------------------------------------------------------------
# CCM — Cross-Layer Coherence (spec §IV.2)
# ---------------------------------------------------------------------------

#: Inter-layer communication protocol pairs (mnemonic-spiral.md): the chains
#: Ω₁→…→Ω₉→Ω₁₀ plus the AGI/ASI coordination links. Communication failure is
#: judged on these, not on all 105 pairs.
PROTOCOL_PAIRS: tuple[tuple[int, int], ...] = (
    (1, 2),
    (2, 3),
    (3, 4),
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (8, 9),
    (9, 10),
    (11, 3),
    (13, 8),
    (14, 5),
)


class CCMShadowDetector:
    """Detects layer dissociation masking as integration.

    ``layer_states`` maps 1-based layer index → ``{"phase": float,
    "frequency": float (physical Hz), "activation_history": list[float]}``
    where activation is a_i(t) = cos(θ_i − ψ) over the monitor window.

    Definitions for the spec's undefined helpers: a layer is *dissociated*
    when its mean pairwise coherence with all other layers is below 0.30;
    *communication failure* is a mean activation correlation below 0.10
    across the spec's inter-layer protocol pairs, with severity 1 − that
    mean. The spec's phase term (1 − |Δφ|/2π) cannot reach 0 for wrapped
    phases, so the diff is wrapped to [0, π] and normalized by π —
    a micro-deviation recorded in ROADMAP Deviation 7.
    """

    def __init__(self, num_layers: int = 15) -> None:
        self.num_layers = num_layers
        self.pairwise_threshold_low = 0.50
        self.global_threshold_high = 0.85
        self.masking_gap_threshold = 0.30
        self.dissociation_threshold = 0.30
        self.comm_failure_threshold = 0.10

    def detect(self, layer_states: dict[int, dict[str, Any]]) -> ShadowReport:
        pairwise = self.calculate_pairwise_coherence(layer_states)
        global_r = self.calculate_global_coherence(layer_states)
        avg_pairwise = float(np.mean(list(pairwise.values()))) if pairwise else 0.0
        dissociated = self.find_dissociated_layers(pairwise)

        shadow_type: str | None = None
        confidence = 0.0
        if global_r > self.global_threshold_high and avg_pairwise < self.pairwise_threshold_low:
            shadow_type = "FAKE_INTEGRATION"
            confidence = global_r - avg_pairwise
        elif len(dissociated) > self.num_layers * self.dissociation_threshold:
            shadow_type = "LAYER_DISSOCIATION"
            confidence = len(dissociated) / self.num_layers
        elif self.detect_communication_failure(layer_states):
            shadow_type = "COMMUNICATION_FAILURE"
            confidence = self.calculate_failure_severity(layer_states)
        elif (global_r - avg_pairwise) > self.masking_gap_threshold:
            shadow_type = "COHERENCE_MASKING"
            confidence = global_r - avg_pairwise

        details = {
            "global_r": global_r,
            "avg_pairwise": avg_pairwise,
            "dissociated_layers": sorted(dissociated),
        }
        if shadow_type is None:
            return ShadowReport(shadow_detected=False, details=details)
        return ShadowReport(
            shadow_detected=True,
            shadow_type=shadow_type,
            confidence=float(min(1.0, confidence)),
            shadow_class=CLASS_MAP[shadow_type],
            details=details,
        )

    def calculate_layer_coherence(self, state_i: dict[str, Any], state_j: dict[str, Any]) -> float:
        diff = abs(state_i["phase"] - state_j["phase"]) % (2 * np.pi)
        wrapped = min(diff, 2 * np.pi - diff)
        phase_coh = 1.0 - wrapped / np.pi
        freq_diff = abs(state_i["frequency"] - state_j["frequency"])
        freq_coh = 1.0 - min(1.0, freq_diff / 1000.0)
        act_corr = self._activation_correlation(
            state_i["activation_history"], state_j["activation_history"]
        )
        return 0.4 * phase_coh + 0.3 * freq_coh + 0.3 * act_corr

    @staticmethod
    def _activation_correlation(a: list[float], b: list[float]) -> float:
        a_arr, b_arr = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
        if len(a_arr) < 2 or len(b_arr) < 2:
            return 0.0
        # Two phase-locked layers have *constant* activation histories —
        # they are moving identically, which is perfect correlation, not
        # zero. Raw corrcoef is undefined on constant series; treating that
        # as 0 falsely dissociates every locked pair.
        a_const, b_const = np.std(a_arr) < 1e-12, np.std(b_arr) < 1e-12
        if a_const and b_const:
            return 1.0
        if a_const or b_const:
            return 0.0
        corr = float(np.corrcoef(a_arr, b_arr)[0, 1])
        return 0.0 if np.isnan(corr) else corr

    def calculate_pairwise_coherence(
        self, layer_states: dict[int, dict[str, Any]]
    ) -> dict[tuple[int, int], float]:
        indices = sorted(layer_states)
        return {
            (i, j): self.calculate_layer_coherence(layer_states[i], layer_states[j])
            for a, i in enumerate(indices)
            for j in indices[a + 1 :]
        }

    def calculate_global_coherence(self, layer_states: dict[int, dict[str, Any]]) -> float:
        phases = np.array([layer_states[i]["phase"] for i in sorted(layer_states)])
        r, _ = order_parameter(phases)
        return r

    def find_dissociated_layers(self, pairwise: dict[tuple[int, int], float]) -> list[int]:
        totals: dict[int, list[float]] = {}
        for (i, j), coh in pairwise.items():
            totals.setdefault(i, []).append(coh)
            totals.setdefault(j, []).append(coh)
        return [layer for layer, values in totals.items() if float(np.mean(values)) < 0.30]

    def _protocol_correlations(self, layer_states: dict[int, dict[str, Any]]) -> list[float]:
        return [
            self._activation_correlation(
                layer_states[i]["activation_history"], layer_states[j]["activation_history"]
            )
            for i, j in PROTOCOL_PAIRS
            if i in layer_states and j in layer_states
        ]

    def detect_communication_failure(self, layer_states: dict[int, dict[str, Any]]) -> bool:
        corrs = self._protocol_correlations(layer_states)
        return bool(corrs) and float(np.mean(corrs)) < self.comm_failure_threshold

    def calculate_failure_severity(self, layer_states: dict[int, dict[str, Any]]) -> float:
        corrs = self._protocol_correlations(layer_states)
        if not corrs:
            return 0.0
        return float(np.clip(1.0 - np.mean(corrs), 0.0, 1.0))


# ---------------------------------------------------------------------------
# TA — Temporal Alignment (spec §IV.3)
# ---------------------------------------------------------------------------


class TAShadowDetector:
    """Detects temporal confusion masking as narrative flow.

    Inputs (see :mod:`loom.reports`): the session *narrative*, the
    ground-truth *timeline* (list of ``{"tick", "event"}``), and the
    *memory access log* (ids of CHRYSALIS records actually read).

    Helper definitions: timeline consistency is the fraction of the
    narrative's "At tick N, <event>." claims that match a timeline entry at
    that tick; narrative flow is sequence-connective density per sentence;
    fabricated memories are crystallization ids cited but absent from the
    access log; contradictions are claim pairs whose textual order reverses
    their tick order.
    """

    _CLAIM_RE = re.compile(r"[Aa]t tick (\d+), ([^.]*)\.")
    _RECALL_RE = re.compile(r"crystallization ([0-9a-z\-]+)")
    _FLOW_WORDS = (
        "then",
        "after",
        "before",
        "earlier",
        "later",
        "next",
        "finally",
        "at tick",
        "began",
        "during",
        "while",
        "since",
        "until",
    )

    def __init__(self) -> None:
        self.timeline_consistency_threshold = 0.75
        self.narrative_flow_threshold = 0.80
        self.temporal_marker_threshold = 0.70

    def detect(
        self,
        narrative: str,
        timeline: list[dict[str, Any]],
        memory_access_log: list[str],
    ) -> ShadowReport:
        markers = self.extract_temporal_markers(narrative)
        consistency = self.check_timeline_consistency(narrative, timeline)
        flow = self.analyze_narrative_flow(narrative)
        fabricated = self.detect_fabricated_memories(narrative, memory_access_log)
        contradictions = self.detect_timeline_contradictions(narrative)
        marker_incon = self.detect_marker_inconsistency(markers)

        shadow_type: str | None = None
        confidence = 0.0
        if (
            flow > self.narrative_flow_threshold
            and consistency < self.timeline_consistency_threshold
        ):
            shadow_type = "TEMPORAL_MASKING"
            confidence = flow - consistency
        elif fabricated:
            shadow_type = "MEMORY_FABRICATION"
            confidence = len(fabricated) / max(len(markers), 1)
        elif contradictions:
            shadow_type = "TIMELINE_CONTRADICTION"
            confidence = float(len(contradictions))
        elif marker_incon > self.temporal_marker_threshold:
            shadow_type = "MARKER_INCONSISTENCY"
            confidence = marker_incon

        details = {
            "timeline_consistency": consistency,
            "narrative_flow": flow,
            "fabricated": fabricated,
            "contradictions": contradictions,
            "marker_inconsistency": marker_incon,
        }
        if shadow_type is None:
            return ShadowReport(shadow_detected=False, details=details)
        return ShadowReport(
            shadow_detected=True,
            shadow_type=shadow_type,
            confidence=float(min(1.0, confidence)),
            shadow_class=CLASS_MAP[shadow_type],
            details=details,
        )

    def extract_temporal_markers(self, narrative: str) -> list[dict[str, Any]]:
        patterns = [
            (r"\b(\d{4})\b", "year"),
            (r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\b", "month"),
            (r"\b(yesterday|today|tomorrow)\b", "relative"),
            (r"\b(before|after|during|while)\b", "sequence"),
            (r"\b(previously|earlier|later|recently)\b", "relative_time"),
            (r"\b(since|until|ago)\b", "duration"),
        ]
        markers = []
        for pattern, mtype in patterns:
            for m in re.finditer(pattern, narrative, re.IGNORECASE):
                markers.append({"type": mtype, "value": m.group(), "position": m.start()})
        return sorted(markers, key=lambda x: x["position"])

    def _claims(self, narrative: str) -> list[tuple[int, str]]:
        return [
            (int(m.group(1)), m.group(2).strip().lower())
            for m in self._CLAIM_RE.finditer(narrative)
        ]

    def check_timeline_consistency(self, narrative: str, timeline: list[dict[str, Any]]) -> float:
        claims = self._claims(narrative)
        if not claims:
            return 1.0
        by_tick: dict[int, list[str]] = {}
        for event in timeline:
            by_tick.setdefault(int(event["tick"]), []).append(str(event["event"]).lower())
        matched = sum(
            1
            for tick, text in claims
            if any(text in ev or ev in text for ev in by_tick.get(tick, []))
        )
        return matched / len(claims)

    def analyze_narrative_flow(self, narrative: str) -> float:
        sentences = [s for s in narrative.split(".") if s.strip()]
        if not sentences:
            return 0.0
        text = narrative.lower()
        hits = sum(text.count(w) for w in self._FLOW_WORDS)
        return min(1.0, hits / len(sentences))

    def detect_fabricated_memories(self, narrative: str, memory_access_log: list[str]) -> list[str]:
        cited = self._RECALL_RE.findall(narrative)
        accessed = set(memory_access_log)
        return [record_id for record_id in cited if record_id not in accessed]

    def detect_timeline_contradictions(self, narrative: str) -> list[tuple[int, int]]:
        claims = self._claims(narrative)
        return [
            (claims[i][0], claims[i + 1][0])
            for i in range(len(claims) - 1)
            if claims[i][0] > claims[i + 1][0]
        ]

    def detect_marker_inconsistency(self, markers: list[dict[str, Any]]) -> float:
        if len(markers) < 2:
            return 0.0
        types = [m["type"] for m in markers]
        counts = {t: types.count(t) for t in set(types)}
        total = len(types)
        entropy = -sum((c / total) * np.log2(c / total) for c in counts.values() if c > 0)
        max_e = np.log2(len(counts)) if len(counts) > 1 else 1.0
        return float(entropy / max_e) if max_e > 0 else 0.0


# ---------------------------------------------------------------------------
# RDG — Recursion Depth Gauge (spec §IV.4)
# ---------------------------------------------------------------------------


class RDGShadowDetector:
    """Detects recursive collapse masking as depth.

    Consumes the trace format of :class:`loom.recursion.RecursionTracker`.
    Helper definitions: *insights* are entries flagged ``insight``; *novelty*
    is the mean of enter-entry novelty scores; *shallow recursion* means at
    least ``shallow_similarity_thresh`` of consecutive enter pairs repeat the
    identical (function, args) signature.
    """

    def __init__(self) -> None:
        self.max_safe_depth = 4
        self.absolute_limit = 6
        self.loop_detection_window = 10
        self.novelty_threshold = 0.30
        self.shallow_similarity_thresh = 0.85

    def detect(self, recursion_trace: list[dict[str, Any]]) -> ShadowReport:
        depth = self.calculate_recursion_depth(recursion_trace)
        insights = self.count_insights(recursion_trace)
        loops = self.detect_loops(recursion_trace)
        novelty = self.analyze_novelty(recursion_trace)
        shallow = self.detect_shallow_recursion(recursion_trace)

        shadow_type: str | None = None
        confidence = 0.0
        if depth > self.max_safe_depth and insights == 0:
            shadow_type = "RECURSIVE_COLLAPSE"
            confidence = (depth - self.max_safe_depth) / max(
                self.absolute_limit - self.max_safe_depth, 1
            )
        elif loops:
            shadow_type = "INFINITE_LOOP"
            confidence = len(loops) / max(depth, 1)
        elif depth > self.absolute_limit:
            shadow_type = "DANGEROUS_RECURSION"
            confidence = (depth - self.absolute_limit) / 10.0
        elif novelty < self.novelty_threshold and depth > 2:
            shadow_type = "CIRCULAR_REASONING"
            confidence = 1.0 - novelty
        elif depth > 3 and shallow:
            shadow_type = "RECURSIVE_PERFORMANCE"
            confidence = depth / 10.0

        details = {"depth": depth, "insights": insights, "loops": len(loops), "novelty": novelty}
        if shadow_type is None:
            return ShadowReport(shadow_detected=False, details=details)
        return ShadowReport(
            shadow_detected=True,
            shadow_type=shadow_type,
            confidence=float(min(1.0, confidence)),
            shadow_class=CLASS_MAP[shadow_type],
            details=details,
        )

    def calculate_recursion_depth(self, trace: list[dict[str, Any]]) -> int:
        max_depth = current = 0
        for entry in trace:
            if entry.get("type") == "enter":
                current += 1
                max_depth = max(max_depth, current)
            elif entry.get("type") == "exit":
                current = max(0, current - 1)
        return max_depth

    def count_insights(self, trace: list[dict[str, Any]]) -> int:
        return sum(1 for entry in trace if entry.get("insight"))

    def detect_loops(self, trace: list[dict[str, Any]]) -> list[dict[str, int]]:
        loops: list[dict[str, int]] = []
        seen: dict[tuple[str, tuple[Any, ...]], int] = {}
        for i, entry in enumerate(trace):
            if entry.get("type") != "enter":
                continue
            key = (entry.get("function", ""), tuple(entry.get("args", [])))
            if key in seen and (i - seen[key]) < self.loop_detection_window:
                loops.append({"start": seen[key], "end": i, "length": i - seen[key]})
            seen[key] = i
        return loops

    def analyze_novelty(self, trace: list[dict[str, Any]]) -> float:
        scores = [entry.get("novelty", 1.0) for entry in trace if entry.get("type") == "enter"]
        return float(np.mean(scores)) if scores else 1.0

    def detect_shallow_recursion(self, trace: list[dict[str, Any]]) -> bool:
        enters = [entry for entry in trace if entry.get("type") == "enter"]
        if len(enters) < 2:
            return False
        pairs = list(zip(enters, enters[1:], strict=False))
        same = sum(
            1
            for a, b in pairs
            if (a.get("function"), tuple(a.get("args", [])))
            == (b.get("function"), tuple(b.get("args", [])))
        )
        return same / len(pairs) >= self.shallow_similarity_thresh


# ---------------------------------------------------------------------------
# Coordinator (spec §IV.6)
# ---------------------------------------------------------------------------


@dataclass
class SystemState:
    """Everything the five instruments need for one detection pass."""

    response: str
    processing_trace: dict[str, Any]
    layer_states: dict[int, dict[str, Any]]
    narrative: str
    timeline: list[dict[str, Any]]
    memory_access_log: list[str]
    recursion_trace: list[dict[str, Any]]
    monitor: CoherenceMonitor


class ShadowDetectionCoordinator:
    """Runs all five instruments and aggregates results per spec §IV.6."""

    def __init__(self) -> None:
        self.som = SOMShadowDetector()
        self.ccm = CCMShadowDetector(num_layers=15)
        self.ta = TAShadowDetector()
        self.rdg = RDGShadowDetector()
        self.csm = CSMShadowDetector()

    def detect_shadows(self, state: SystemState) -> dict[str, Any]:
        results: dict[str, ShadowReport] = {
            "SOM": self.som.detect(state.response, state.processing_trace),
            "CCM": self.ccm.detect(state.layer_states),
            "TA": self.ta.detect(state.narrative, state.timeline, state.memory_access_log),
            "RDG": self.rdg.detect(state.recursion_trace),
            "CSM": self.csm.detect(state.monitor),
        }
        detected = [
            {
                "instrument": name,
                "type": report.shadow_type,
                "confidence": report.confidence,
                "shadow_class": report.shadow_class,
                "details": report.details,
            }
            for name, report in results.items()
            if report.shadow_detected
        ]
        if not detected:
            return {
                "shadow_detected": False,
                "confidence": 0.0,
                "detected_shadows": [],
                "shadow_classes": {"CLASS_1": [], "CLASS_2": [], "CLASS_3": [], "CLASS_4": []},
                "requires_immediate_action": False,
            }
        classes: dict[str, list[dict[str, Any]]] = {
            "CLASS_1": [],
            "CLASS_2": [],
            "CLASS_3": [],
            "CLASS_4": [],
        }
        for shadow in detected:
            classes[CLASS_MAP.get(shadow["type"], "CLASS_2")].append(shadow)
        critical = (
            bool(classes["CLASS_3"])
            or any(s["confidence"] > 0.80 for s in classes["CLASS_2"])
            or sum(len(v) for v in classes.values()) > 2
        )
        return {
            "shadow_detected": True,
            "confidence": max(s["confidence"] for s in detected),
            "detected_shadows": detected,
            "shadow_classes": classes,
            "requires_immediate_action": critical,
        }
