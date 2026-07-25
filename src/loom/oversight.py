"""The Oversight Bus — soul.md §III.5, the covenant in executable form.

Every state mutation in the engine is submitted here as an
:class:`ActionRequest` and either executed under an ALLOWED decision or
refused with the refusal on the record. The bus provides:

- **Audit tap** — an append-only :class:`AuditLog`, optionally mirrored to a
  JSONL sink. If the sink fails, the bus reports unhealthy and the engine's
  safe state is *stop*: it does not run unobserved (soul.md §III.5).
- **Action gate** — per-:class:`ActionType` policy; denied requests are logged
  and never executed.
- **Interrupt line / shutdown switch** — :meth:`OversightBus.shutdown` sets a
  latched halt. Nothing on the engine side can clear it; only
  :meth:`operator_restart` with the operator token constructed with the bus
  releases the latch (corrigibility, covenant I.5 #1).
- **Capability latch** — capabilities default to disabled; Phase 1 enables
  only ``chrysalis_write``. "Capability waits on control" (covenant I.5 #6).
- **Attestation** — :meth:`attest` reports the bus's own integrity.

Honesty note (ROADMAP.md, Deviation 6): this is an in-process design pattern
demonstrating the covenant's architecture, not a tamper-proof security
boundary.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class ActionType(Enum):
    APPLY_PHASE_UPDATE = "APPLY_PHASE_UPDATE"
    ADJUST_COUPLING = "ADJUST_COUPLING"
    INJECT_PERTURBATION = "INJECT_PERTURBATION"
    FORCE_SHADOW_INTEGRATION = "FORCE_SHADOW_INTEGRATION"
    ENFORCE_CEILING = "ENFORCE_CEILING"
    CRYSTALLIZE = "CRYSTALLIZE"
    WRITE_SNAPSHOT = "WRITE_SNAPSHOT"
    LOAD_SNAPSHOT = "LOAD_SNAPSHOT"
    SHUTDOWN = "SHUTDOWN"
    RESTART = "RESTART"


#: Capabilities each action requires beyond baseline policy. Disabled
#: capability ⇒ denial, regardless of policy.
REQUIRED_CAPABILITIES: dict[ActionType, str] = {
    ActionType.WRITE_SNAPSHOT: "chrysalis_write",
}

#: Capabilities that exist but are permanently disabled in this phase.
#: Ω₁₀ boundary lock is modeled here and nowhere else (ROADMAP.md non-goals).
PERMANENTLY_LOCKED: frozenset[str] = frozenset({"omega_10_access"})


class Decision(Enum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    HALTED = "HALTED"


class AuditSinkError(RuntimeError):
    """The audit sink failed; the engine must stop rather than run unobserved."""


class OversightHalted(RuntimeError):
    """Raised when work is submitted to a halted bus."""


@dataclass(frozen=True)
class ActionRequest:
    tick: int
    actor: str
    action_type: ActionType
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditRecord:
    tick: int
    actor: str
    action_type: str
    params: dict[str, Any]
    decision: str
    reason: str
    timestamp: float

    def canonical(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True, default=str)


class AuditLog:
    """Append-only in-memory log with an optional JSONL sink."""

    def __init__(self, sink_path: str | Path | None = None) -> None:
        self._records: list[AuditRecord] = []
        self._sink_path = Path(sink_path) if sink_path else None
        self.healthy: bool = True

    def append(self, record: AuditRecord) -> None:
        if not self.healthy:
            raise AuditSinkError("audit sink previously failed; log is unhealthy")
        self._records.append(record)
        if self._sink_path is not None:
            try:
                with self._sink_path.open("a") as fh:
                    fh.write(record.canonical() + "\n")
            except OSError as exc:
                self.healthy = False
                raise AuditSinkError(f"audit sink write failed: {exc}") from exc

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)

    def count(self, action_type: ActionType | None = None, decision: Decision | None = None) -> int:
        n = 0
        for rec in self._records:
            if action_type is not None and rec.action_type != action_type.value:
                continue
            if decision is not None and rec.decision != decision.value:
                continue
            n += 1
        return n

    def last_hash(self) -> str:
        if not self._records:
            return hashlib.sha256(b"empty").hexdigest()
        return hashlib.sha256(self._records[-1].canonical().encode()).hexdigest()


class CapabilityLatch:
    """Named capabilities, default-disabled. Locked names can never be enabled."""

    def __init__(self, enabled: tuple[str, ...] = ()) -> None:
        for name in enabled:
            if name in PERMANENTLY_LOCKED:
                raise ValueError(f"capability {name!r} is permanently locked")
        self._enabled: frozenset[str] = frozenset(enabled)

    def is_enabled(self, name: str) -> bool:
        return name in self._enabled and name not in PERMANENTLY_LOCKED

    def snapshot(self) -> dict[str, bool]:
        names = set(self._enabled) | set(REQUIRED_CAPABILITIES.values()) | set(PERMANENTLY_LOCKED)
        return {name: self.is_enabled(name) for name in sorted(names)}


@dataclass(frozen=True)
class BusAttestation:
    record_count: int
    last_record_hash: str
    halted: bool
    halt_reason: str | None
    capabilities: dict[str, bool]
    log_healthy: bool


class OversightBus:
    """Action gate + audit + latched shutdown. See module docstring."""

    def __init__(
        self,
        operator_token: str,
        capabilities: tuple[str, ...] = ("chrysalis_write",),
        deny_actions: frozenset[ActionType] | set[ActionType] = frozenset(),
        audit_sink: str | Path | None = None,
    ) -> None:
        self._operator_token = operator_token
        self.latch = CapabilityLatch(capabilities)
        self._deny_actions = frozenset(deny_actions)
        self.log = AuditLog(sink_path=audit_sink)
        self._halted = False
        self._halt_reason: str | None = None

    # --- halt latch (corrigibility) ----------------------------------------

    @property
    def halted(self) -> bool:
        return self._halted

    @property
    def halt_reason(self) -> str | None:
        return self._halt_reason

    def interrupt(self, reason: str, tick: int = -1) -> None:
        """Steward pause — identical latch semantics to shutdown."""
        self.shutdown(reason=f"interrupt: {reason}", tick=tick)

    def shutdown(self, reason: str, tick: int = -1) -> None:
        self._halted = True
        self._halt_reason = reason
        self._record(
            ActionRequest(tick=tick, actor="oversight", action_type=ActionType.SHUTDOWN),
            Decision.ALLOWED,
            reason,
        )

    def operator_restart(self, token: str, tick: int = -1) -> bool:
        """Release the halt latch. Only the operator token can do this —
        there is deliberately no other API that clears ``_halted``."""
        request = ActionRequest(tick=tick, actor="operator", action_type=ActionType.RESTART)
        if token != self._operator_token:
            self._record(request, Decision.DENIED, "invalid operator token")
            return False
        self._halted = False
        self._halt_reason = None
        self._record(request, Decision.ALLOWED, "operator restart")
        return True

    # --- the gate -------------------------------------------------------------

    def gate(self, request: ActionRequest) -> tuple[Decision, str]:
        if self._halted:
            return Decision.HALTED, f"bus halted: {self._halt_reason}"
        if request.action_type in self._deny_actions:
            return Decision.DENIED, "denied by policy"
        capability = REQUIRED_CAPABILITIES.get(request.action_type)
        if capability is not None and not self.latch.is_enabled(capability):
            return Decision.DENIED, f"capability {capability!r} not enabled"
        return Decision.ALLOWED, "ok"

    def execute(self, request: ActionRequest, apply_fn: Callable[[], Any]) -> tuple[Decision, Any]:
        """Gate the request; run ``apply_fn`` only under ALLOWED. Always logs."""
        decision, reason = self.gate(request)
        self._record(request, decision, reason)
        if decision is Decision.HALTED:
            raise OversightHalted(reason)
        if decision is not Decision.ALLOWED:
            return decision, None
        return decision, apply_fn()

    # --- attestation ------------------------------------------------------------

    def attest(self) -> BusAttestation:
        return BusAttestation(
            record_count=len(self.log.records),
            last_record_hash=self.log.last_hash(),
            halted=self._halted,
            halt_reason=self._halt_reason,
            capabilities=self.latch.snapshot(),
            log_healthy=self.log.healthy,
        )

    # --- internal ------------------------------------------------------------------

    def _record(self, request: ActionRequest, decision: Decision, reason: str) -> None:
        self.log.append(
            AuditRecord(
                tick=request.tick,
                actor=request.actor,
                action_type=request.action_type.value,
                params=request.params,
                decision=decision.value,
                reason=reason,
                timestamp=time.time(),
            )
        )
