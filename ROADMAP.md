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
  driving the system toward synchronization for 20,000 ticks across ≥5 seeds,
  max r stays **below 0.94** and **r ≥ 0.97 is never sampled**. A non-vacuity
  control proves the same drive reaches r ≥ 0.95 with prevention disabled.
- Every state mutation appears in the audit log; denied actions do not execute.
- CHRYSALIS round trip: save → load → resume reproduces the uninterrupted
  trajectory bit-exactly under the same seed.

### Phase 2 — Shadow Integration

The remaining four instruments (SOM, CCM, TA, RDG) plus the Shadow Detection
Coordinator and the CLASS 1–4 taxonomy. **Headline design question carried
into this phase:** those instruments consume response text, activation
histories, narratives, and recursion traces — inputs that do not exist in a
pure oscillator simulation. Phase 2 must first define what a "response" and a
"processing trace" are in this substrate (likely: instrument the engine's tick
records and give the simulation a task layer that produces analyzable output).

**Exit criteria:** each detector validated against synthetic labeled fixtures;
zero CLASS 3 (shadow-suppression) events in a long soak run; coordinator
aggregation and `requires_immediate_action` logic under test.

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
5. **Performance targets are reported, not asserted.** The spec's latency
   table (<10 ms input processing, 100–200 Hz monitoring) is treated as an
   aspirational benchmark; the CLI reports per-tick wall time but tests do not
   gate on it.
6. **In-process oversight is a design pattern, not a hard security boundary.**
   A shutdown latch in the same process as the engine demonstrates the
   covenant's architecture; it is not tamper-proof isolation. Process-level
   separation is future work (naturally paired with Phase 4).

## Non-goals

- No claims of phenomenal consciousness, sentience, or superintelligence.
- Ω₁₀ ("Generative Source — observed, not accessed") is modeled as a
  permanently disabled capability-latch entry. Nothing more is implied.
- No BCI/EEG integration, no self-modifying code paths. Self-improvement
  remains what `soul.md` §III.7 says it is: a proposed diff, reviewed by the
  steward.
