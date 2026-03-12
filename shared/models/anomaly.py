"""Anomaly event and rule result models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AnomalyEvent(BaseModel):
    """An anomaly event detected by the scoring engine."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    mmsi: int = Field(..., ge=100000000, le=999999999)
    rule_id: str
    severity: Literal["critical", "high", "moderate", "low"]
    points: float
    details: dict = Field(default_factory=dict)
    resolved: bool = False
    created_at: Optional[datetime] = None


@dataclass
class RuleResult:
    """Result returned by an individual scoring rule evaluation.

    This is a plain dataclass (not Pydantic) because it is used as an
    internal data-transfer object within the scoring engine, not for
    serialisation or API responses.
    """

    fired: bool
    rule_id: str
    severity: Optional[str] = None
    points: float = 0.0
    details: dict = field(default_factory=dict)
    source: Optional[str] = None  # 'gfw' or 'realtime'
