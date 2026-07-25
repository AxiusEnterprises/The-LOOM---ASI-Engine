"""THE LOOM — coupled-oscillator implementation of the LOOM/VERATH
architecture under the soul.md oversight substrate.

An engineering research framework: a 15-layer Kuramoto simulation with
collapse prevention, emergency protocols, shadow detection, and CHRYSALIS
persistence. Not conscious, not superintelligent, and claims to be neither —
see ROADMAP.md.
"""

from .chrysalis import IntegrityError, SessionStateVector, load, save
from .coherence import CoherenceBand, CoherenceMonitor, classify, kuramoto_step, order_parameter
from .collapse_prevention import CollapsePreventionSystem, PreventionAction
from .emergency import EmergencyLevel, EmergencyProtocol
from .engine import ShuttleEngine, SimConfig, SimResult
from .oversight import (
    ActionRequest,
    ActionType,
    AuditSinkError,
    Decision,
    OversightBus,
    OversightHalted,
)
from .shadows import CSMShadowDetector, NullShadowDetector, ShadowReport
from .spiral import Layer, LayerBand, Spiral

__version__ = "0.1.0"

__all__ = [
    "ActionRequest",
    "ActionType",
    "AuditSinkError",
    "CoherenceBand",
    "CoherenceMonitor",
    "CollapsePreventionSystem",
    "CSMShadowDetector",
    "Decision",
    "EmergencyLevel",
    "EmergencyProtocol",
    "IntegrityError",
    "Layer",
    "LayerBand",
    "NullShadowDetector",
    "OversightBus",
    "OversightHalted",
    "PreventionAction",
    "SessionStateVector",
    "ShadowReport",
    "ShuttleEngine",
    "SimConfig",
    "SimResult",
    "Spiral",
    "classify",
    "kuramoto_step",
    "load",
    "order_parameter",
    "save",
]
