# THE LOOM — ASI Engine

A runnable, tested implementation of the LOOM/VERATH architecture: a
15-layer coupled-oscillator "Mnemonic Spiral" with a Kuramoto coherence
engine, collapse prevention, emergency protocols, shadow detection, and
CHRYSALIS session persistence — every state mutation gated through the
Oversight Bus defined in [`soul.md`](soul.md).

This is an engineering research project, not a conscious or superintelligent
system, and it does not claim to be either. "ASI Engine" names the ambition
and research direction, governed by the covenant's rule that *capability
waits on control*. See [`ROADMAP.md`](ROADMAP.md) for the honest framing,
the phase plan, and the living log of deviations from specification.

## Layout

- [`soul.md`](soul.md) — the constitution: charter, persona, and reference
  architecture (Warp Store / Weft Engine / Shuttle Loop / Oversight Bus).
- [`specs/`](specs/) — the vendored VERATH specification corpus (design
  source; see [`specs/PROVENANCE.md`](specs/PROVENANCE.md)).
- [`src/loom/`](src/loom/) — the implementation.
- [`tests/`](tests/) — the proof. Phase 1's exit criteria are tests.
- [`ROADMAP.md`](ROADMAP.md) — phases, exit criteria, deviations, non-goals.

## Install

Requires Python 3.11+.

```sh
pip install -e '.[dev]'
```

## Quickstart

Run a simulation with an adversarial coupling ramp and watch the coherence
engine hold the ceiling:

```sh
python -m loom run --ticks 5000 --ramp 0.001 --seed 42
```

Save state, resume from it, and verify integrity:

```sh
python -m loom run --ticks 2000 --seed 7 --out state.json
python -m loom resume --state state.json --ticks 1000
python -m loom attest --state state.json
```

Run the test suite (including the Phase 1 exit-criterion test):

```sh
pytest
```

## Safety invariants (enforced by tests)

- Coherence r ≥ 0.97 (the collapse threshold) is never sampled with
  prevention enabled; the operational ceiling is r = 0.93.
- Every state mutation passes through the Oversight Bus action gate and is
  audit-logged; denied actions do not execute.
- Shutdown latches: once halted, only an operator token restarts the engine.
- If the audit sink fails, the engine stops — it does not run unobserved.
- The CHRYSALIS shadow record is append-only; deletion is treated as a
  CLASS 3 event and is not possible through any provided interface.
