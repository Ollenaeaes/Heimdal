# shared/models/__init__.py
# Re-export all domain models for convenient imports.

from shared.models.vessel import VesselPosition, VesselProfile
from shared.models.ais_message import PositionReport, ShipStaticData, Dimension
from shared.models.anomaly import AnomalyEvent, RuleResult
from shared.models.enrichment import ManualEnrichment
from shared.models.sar import SarDetection
from shared.models.gfw_event import GfwEvent

__all__ = [
    "VesselPosition",
    "VesselProfile",
    "PositionReport",
    "ShipStaticData",
    "Dimension",
    "AnomalyEvent",
    "RuleResult",
    "ManualEnrichment",
    "SarDetection",
    "GfwEvent",
]
