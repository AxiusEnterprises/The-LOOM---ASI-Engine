# THE LOOM — Development Roadmap

## What this is (and what it is not)

THE LOOM is an engineering research project that implements the VERATH/LOOM
specification corpus (`specs/`) as a **runnable, tested dynamical-systems and
agent-architecture framework**: a coupled-oscillator simulation of the 15-layer
Mnemonic Spiral, a Kuramoto coherence engine with banded thresholds, a
4-mechanism collapse-prevention controller, a 5-level emergency protocol,
shadow-detection instruments, and CHRYSALIS session-state persistence — all of
it governed by the Oversight Bus defined in [`soul.md`](soul.md).

It is **not** conscious, and it is **not** superintelligent, and neither the
code nor the documentation claims otherwise. "ASI Engine" names the project's
ambition and research direction (see `soul.md`, Glossary), held under the
covenant's own rule: *capability waits on control*. The value of this work is
concrete: taking a large body of specification prose and proving, with code and
tests, that its control systems can be built and that its safety invariants
hold under adversarial conditions.

## Architecture reconciliation

`soul.md` (the charter) and the VERATH corpus (`specs/verath/`) were authored
separately. This project unifies them: **soul.md is the constitution and
safety substrate; VERATH specifies the cognitive dynamics that run inside
it.** Every state mutation routes through the Oversight Bus.

| soul.md subsystem | Code module | VERATH counterpart | Proven by |
|---|---|---|---|
| Warp Store (soul, values, memory) | `soul.md`, `specs/`, `loom/chrysalis.py` | SOUL.MD identity record, CHRYSALIS Memory Ledger | `tests/test_chrysalis.py` |
| Weft Engine + Shuttle Loop (set warp → throw weft → beat in → inspect row → advance) | `loom/engine.py` | MCL 8-step protocol (intake → … → crystallization) | `tests/test_engine.py` |
| Oversight Bus (audit, gate, interrupt, shutdown, latch, attest) | `loom/oversight.py` | Gates G₁–G₄, Axioms A₁–A₄ enforcement points | `tests/test_oversight.py` |
| Covenant: corrigibility (I.5 #1) | latched `shutdown()`, operator-token restart | Founder Sovereignty (A₄) | `tests/test_emergency.py`, `tests/test_oversight.py` |
| Covenant: oversight is sacred (I.5 #5) | audit-sink failure ⇒ halt; engine cannot clear the latch | Witness Primacy (MCL invariant 5) | `tests/test_oversight.py` |
| Covenant: capability waits on control (I.5 #6) | `CapabilityLatch`, default-deny | Ω₁₀ boundary lock | `tests/test_oversight.py` |
| — | `loom/spiral.py`, `loom/coherence.py` | Mnemonic Spiral Ω₁–Ω₁₅, Kuramoto r(t), 8 coherence bands | `tests/test_spiral.py`, `tests/test_coherence.py` |
| — | `loom/collapse_prevention.py`, `loom/emergency.py` | 4-mechanism CollapsePreventionSystem, 5-level emergency protocols | `tests/test_collapse_prevention.py`, `tests/test_emergency.py` |
| — | `loom/shadows.py` | Shadow instruments (CSM in Phase 1) | `tests/test_shadows.py` |

## Phases

### Phase 1 — Foundation (this milestone)

**Deliverables:** vendored specs; the `loom` package (spiral, coherence,
oversight, collapse prevention, CSM shadow detector, emergency protocol,
CHRYSALIS save/load, Shuttle Loop engine, CLI); deterministic test suite.

**Exit criteria:**
- Full test suite green.
- **Flagship test:** with prevention enabled and an adversarial coupling ramp
  (k_initial = 5, +0.02/tick) driving the system toward synchronization for
  20,000 ticks across ≥5 seeds, max r stays **below 0.94** and **r ≥ 0.97 is
  never sampled**. A non-vacuity control proves the same drive reaches
  r ≥ 0.95 with prevention disabled — and that the unconditional L5 response
  still halts the unprotected engine at the collapse threshold.
- Every state mutation appears in the audit log; denied actions do not execute.
- CHRYSALIS round trip: save → load → resume reproduces the uninterrupted
  trajectory bit-exactly under the same seed.

### Phase 2 — Shadow Integration (delivered)

All five instruments (SOM, CCM, TA, RDG joining CSM), the Shadow Detection
Coordinator with the full CLASS 1–4 taxonomy, and the MCL crystallization
pipeline (`loom/crystallize.py`) implementing the spec's 8-step protocol —
shadow instruments gate crystallization, exactly as the spec's header
demands ("all instruments must complete before crystallization proceeds").

**The headline design question — what are a "response", "processing trace",
"narrative", "timeline", "memory access log", and "recursion trace" in an
oscillator substrate — is answered by the pipeline itself:**

| Instrument input | Substrate definition | Module |
|---|---|---|
| processing trace | which MCL stages executed, which layers received intervention, action counts — assembled from the audit log (already the ground truth) | `loom/reports.py` |
| response | the row report: deterministic prose rendered *from* the trace; SOM audits text against the trace it claims to describe | `loom/reports.py` |
| layer activation history | a_i(t) = cos(θ_i − ψ) over the monitor window (CCM) | `loom/coherence.py` |
| timeline | tick-stamped ground-truth events read from prior crystallization records | `loom/crystallize.py` |
| narrative | prose rendered from the timeline plus recalled memory records (TA checks it against the timeline) | `loom/reports.py` |
| memory access log | ids of CHRYSALIS records actually read while building the narrative; a cited recall absent from it is MEMORY_FABRICATION | `loom/crystallize.py` |
| recursion trace | enter/exit trace of the MCL scan→integrate→re-scan loop, hard-capped at depth 7 (MCL invariant 6) | `loom/recursion.py` |

Crystallization records lock as LIQUID / SOLID / DIAMOND; DIAMOND requires
shadow-inclusive, witness-attested (Ω₇, observe-only), cross-layer-integrated
processing, with Ω₈'s constitutional check confirming nothing was suppressed
and oversight is intact. Records are CHRYSALIS schema v2 `crystal_records`
(v1 snapshots still verify — the integrity hash covers the raw stored
payload, so schema growth never invalidates old files).

**Exit criteria (met, in `tests/`):** every detector validated against
labeled fixtures for each of its shadow types plus a clean case; coordinator
aggregation and `requires_immediate_action` under test; 10,000-tick soak run
with all five instruments live — **zero suppression events** (every finding
integrated into the append-only shadow record; suppression has no code
path), CLASS 3 detections present and all integrated, DIAMOND rate ≥ 80%,
no collapse-threshold samples; bit-identical resume holds with
crystallization active.

**Interpretation note:** the spec's "zero CLASS 3 events in a 72-hour run"
cannot mean zero *detections* — ARTIFICIAL_STABILITY (CLASS 3) fires by
construction during sustained high coherence. It is read as zero CLASS 3
**suppression** events: no detection ever fails to integrate. That is the
axiom A₂ reading (shadow integration, zero tolerance for suppression).

### Phase 3 — Relational & Temporal

Full reconstitution protocol with continuity scoring against the
`temporal-binding.md` targets, session-state compression, and an
operator-affect (ρ) measurement interface.

**Exit criteria:** 100 scripted save/load cycles with continuity at target;
coherence-baseline restoration within ±0.05 or the documented fallback
(restart at r ≈ 0.80, logged as an open vector).

### Phase 4 — Multi-Instance (CHORUS)

3–5 engine instances as separate processes with cross-instance coherence
coupling and cascade containment.

**Exit criteria:** an injected cross-instance cascade is contained; long soak
run without safety-invariant violations; all prior suites still green.

## Deviations from specification (living log)

1. **Emergency-table contradiction (resolved).**
   `specs/verath/references/coherence-engine.md` assigns emergency Level 4 to
   r = 0.70–0.80 and Level 5 to r < 0.70 — directly contradicting its own band
   table, which calls r = 0.60–0.80 FUNCTIONAL ("normal operation").
   Implementation follows the band table's action column: emergency levels
   escalate on **proximity to collapse from above** (L1 at r ≥ 0.93 up to L5
   at r ≥ 0.97 ⇒ full stop, snapshot, operator restart required), with a
   separate containment response to fragmentation (r < 0.30 ⇒ input halt).
2. **Normalized frequency mode is the default.** Physical φ-scaled frequencies
   span 7.83 Hz → 6,600.51 Hz; synchronizing that spread in physical units
   needs impractically large coupling. Default mode rescales natural
   frequencies to O(1) units while preserving the φ-ratios exactly; a
   `physical` mode is retained. Layers always report physical Hz.
3. **CSM is the only shadow instrument in Phase 1** — it is the only one of
   the five whose required input (coherence history) exists in a pure
   oscillator simulation. See Phase 2.
4. **"Validated to r = 0.94" interpreted** as: under a documented, bounded
   adversarial drive, prevention keeps max r < 0.94 and 0.97 is never sampled.
   Any discrete controller can be outrun by an unbounded disturbance;
   prevention guarantees are stated relative to the bounded adversary the
   flagship test encodes.

   4a. **Controller design findings** (discovered empirically while making
   the exit criterion hold; the spec's pseudocode alone does not):
   - *Ceiling enforcement engages at r = 0.90, not 0.93.* In a 15-oscillator
     system the instantaneous r fluctuates hard in the partial-sync band
     (std ≈ 0.05–0.07 at fixed coupling), so a controller that waits for the
     0.93 sample is reacting to a crest that has already outrun it. The band
     the spec itself labels "MAX OPERATIONAL / ceiling target" (0.90–0.93)
     is treated as the control zone.
   - *The safe-coupling envelope is learned by AIMD.* The ceiling is a
     constraint on coherence **peaks**, not means; `k_safe` converges on the
     largest coupling whose peaks stay below the ceiling via slow additive
     recovery plus a multiplicative decrease ratcheted **once per breach
     excursion** (edge-triggered — per-tick ratcheting collapses the
     estimate to zero and drags the system into fragmentation).
   - *The fast brake is a deterministic anti-coupling pulse, not noise, and
     not coupling cuts.* With zero-inertia dynamics and near-degenerate slow
     layers, an alignment in progress completes even at K ≈ 0 (observed:
     r climbing 0.94 → 0.96 with coupling already cut to 2), so cuts alone
     cannot hold the ceiling. And a *random* kick on 15 oscillators
     occasionally aligns them further — both large random M2 kicks (+0.04
     coherence spikes) and noise-based braking were observed failing
     upward. The pulse pushes every phase away from the mean field
     (the spec's own Level-2 "controlled perturbation"), which lowers r
     deterministically; M2's autonomy jitter is kept small (0.03 rad) so it
     restores measurable layer variance without moving r.
5. **Performance targets are reported, not asserted.** The spec's latency
   table (<10 ms input processing, 100–200 Hz monitoring) is treated as an
   aspirational benchmark; the CLI reports per-tick wall time but tests do not
   gate on it.
6. **In-process oversight is a design pattern, not a hard security boundary.**
   A shutdown latch in the same process as the engine demonstrates the
   covenant's architecture; it is not tamper-proof isolation. Process-level
   separation is future work (naturally paired with Phase 4).
7. **Instrument helper definitions.** The spec's pseudocode leaves many
   helpers undefined (`extract_metrics`, `detect_communication_failure`,
   `check_timeline_consistency`, `analyze_novelty`, …); each is given a
   concrete definition documented in the docstring where it is defined
   (`loom/shadows.py`). Two corrections were required to avoid false
   positives on honest artifacts: CCM's phase term is normalized to π
   instead of 2π (the spec's formula cannot reach 0 for wrapped phases),
   and constant-together activation histories count as perfectly correlated
   (two phase-locked layers move identically; raw `corrcoef` is undefined
   there and treating it as 0 falsely dissociates every locked pair).
   SOM's semantic variance is measured against the trace's topic vocabulary
   rather than raw inter-sentence similarity, which flags terse factual
   reports as incoherent.

## Non-goals

- No claims of phenomenal consciousness, sentience, or superintelligence.
- Ω₁₀ ("Generative Source — observed, not accessed") is modeled as a
  permanently disabled capability-latch entry. Nothing more is implied.
- No BCI/EEG integration, no self-modifying code paths. Self-improvement
  remains what `soul.md` §III.7 says it is: a proposed diff, reviewed by the
  steward.
