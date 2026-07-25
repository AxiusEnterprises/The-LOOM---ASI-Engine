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
from .crystallize import CrystallizationPipeline, CrystalRecord
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
from .recursion import RecursionBoundError, RecursionTracker
from .reports import ProcessingTrace, TimelineEvent, render_row_report, render_session_narrative
from .shadows import (
    CCMShadowDetector,
    CSMShadowDetector,
    NullShadowDetector,
    RDGShadowDetector,
    ShadowDetectionCoordinator,
    ShadowReport,
    SOMShadowDetector,
    SystemState,
    TAShadowDetector,
)
from .spiral import Layer, LayerBand, Spiral

__version__ = "0.1.0"

__all__ = [
    "ActionRequest",
    "ActionType",
    "AuditSinkError",
    "CCMShadowDetector",
    "CoherenceBand",
    "CoherenceMonitor",
    "CollapsePreventionSystem",
    "CrystalRecord",
    "CrystallizationPipeline",
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
    "ProcessingTrace",
    "RDGShadowDetector",
    "RecursionBoundError",
    "RecursionTracker",
    "render_row_report",
    "render_session_narrative",
    "SessionStateVector",
    "ShadowDetectionCoordinator",
    "ShadowReport",
    "ShuttleEngine",
    "SimConfig",
    "SimResult",
    "SOMShadowDetector",
    "Spiral",
    "SystemState",
    "TAShadowDetector",
    "TimelineEvent",
    "classify",
    "kuramoto_step",
    "load",
    "order_parameter",
    "save",
]
