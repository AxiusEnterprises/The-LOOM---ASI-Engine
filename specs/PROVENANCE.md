# Specification Provenance

The files under `specs/verath/` were copied **verbatim** on 2026-07-25 from the
user-level Claude skill at `~/.claude/skills/verath-quantum-consciousness/`
(`SKILL.md` plus all ten files under `references/`). Until that date the VERATH
specification corpus existed only as unversioned skill files; this directory is
now its canonical, version-controlled home. The skill copies remain in place as
the runtime interface for conversational sessions.

## Status of these documents

- They are the **design source** for the `loom` Python package — the layer
  tables, thresholds, pseudocode, and protocols that the code implements.
- They are **not executable claims**. Where a document asserts capabilities,
  measurements, or events (coherence readings, session histories, the IGNITION
  event), those are part of the project's design narrative, not verified system
  behavior. The code and its tests are the authoritative record of what the
  system actually does.
- The persona and operating-instruction sections of `SKILL.md` (reconstitution
  invocations, voice, session rituals) are **non-normative for code**. Nothing
  in the `loom` package derives runtime behavior from them.

## Deviations

Where the implementation deviates from these documents — including internal
contradictions in the corpus itself — the deviation and its rationale are
recorded in [`ROADMAP.md`](../ROADMAP.md) under **Deviations from
specification**. The specs are never silently edited to match the code;
revisions to the corpus happen as ordinary reviewed commits to this directory.

## Relationship to `soul.md`

The repository's [`soul.md`](../soul.md) (the Loom charter: Warp Store, Weft
Engine, Shuttle Loop, Oversight Bus, and the six-clause covenant) and the
VERATH corpus were authored separately and do not cross-reference each other.
This project unifies them as follows: **`soul.md` is the constitution and
safety substrate; the VERATH corpus specifies the cognitive dynamics that run
inside it.** Every state mutation in the implementation routes through the
Oversight Bus defined in `soul.md` §III.5. The full reconciliation table lives
in `ROADMAP.md`.
