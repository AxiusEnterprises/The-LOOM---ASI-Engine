"""Recursion tracking — the trace format the RDG shadow instrument consumes.

Phase 2's substrate answer for "recursion trace": the one place this system
genuinely recurses is the MCL shadow-integration loop (scan → integrate →
re-scan until clean or capped), and reconstitution-of-reconstitution chains.
Components record their re-entrant analysis into a :class:`RecursionTracker`;
the resulting trace is a list of enter/exit entries in exactly the shape the
spec's ``RDG_shadow_detector`` expects:

    {"type": "enter"|"exit", "function": str, "args": [...],
     "insight": bool, "novelty": float}

``insight`` marks a level that produced something its parent did not already
have (e.g. a new shadow finding); ``novelty`` in [0, 1] scores how different
this level's inputs are from the previous visit to the same function.

The MCL recursion bound (invariant 6) is enforced here: depth is capped at 7
— "infinite coherence gain impossible in finite time" — and the cap is a
hard error, not a warning, so no caller can quietly recurse past it.
"""

from __future__ import annotations

from typing import Any

MAX_RECURSION_DEPTH = 7  # MCL invariant 6


class RecursionBoundError(RuntimeError):
    """A component tried to recurse past the MCL bound."""


class RecursionTracker:
    """Collects enter/exit entries; enforces the MCL depth bound."""

    def __init__(self) -> None:
        self.trace: list[dict[str, Any]] = []
        self._depth = 0
        self._seen_args: dict[str, list[tuple[Any, ...]]] = {}

    @property
    def depth(self) -> int:
        return self._depth

    def enter(self, function: str, args: list[Any] | None = None, insight: bool = False) -> None:
        if self._depth >= MAX_RECURSION_DEPTH:
            raise RecursionBoundError(
                f"recursion depth {self._depth} at MCL bound entering {function!r}"
            )
        args = args if args is not None else []
        novelty = self._novelty(function, tuple(args))
        self._depth += 1
        self.trace.append(
            {
                "type": "enter",
                "function": function,
                "args": list(args),
                "insight": insight,
                "novelty": novelty,
            }
        )

    def exit(self, function: str, insight: bool = False) -> None:
        self._depth = max(0, self._depth - 1)
        self.trace.append(
            {
                "type": "exit",
                "function": function,
                "args": [],
                "insight": insight,
                "novelty": 0.0,
            }
        )

    def mark_insight(self) -> None:
        """Flag the most recent entry as having produced an insight."""
        if self.trace:
            self.trace[-1]["insight"] = True

    def _novelty(self, function: str, args: tuple[Any, ...]) -> float:
        """1.0 for a never-seen call signature, decaying toward 0 as the
        same function is re-entered with the same arguments."""
        previous = self._seen_args.setdefault(function, [])
        repeats = sum(1 for seen in previous if seen == args)
        previous.append(args)
        return 1.0 / (1.0 + repeats)
