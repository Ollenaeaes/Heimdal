"""Global Fishing Watch event model."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class GfwEvent(BaseModel):
    """An event record from Global Fishing Watch APIs."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    gfw_event_id: str = Field(..., min_length=1, description="Unique GFW event identifier")
    event_type: Literal["AIS_DISABLING", "ENCOUNTER", "LOITERING", "PORT_VISIT"]
    mmsi: int = Field(..., ge=100000000, le=999999999)
    start_time: datetime
    end_time: Optional[datetime] = None
    lat: Optional[float] = Field(None, ge=-90.0, le=90.0)
    lon: Optional[float] = Field(None, ge=-180.0, le=180.0)
    details: dict = Field(default_factory=dict)
    encounter_mmsi: Optional[int] = None
    port_name: Optional[str] = None
    ingested_at: Optional[datetime] = None
