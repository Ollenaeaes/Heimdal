"""AIS message models: position reports and static data from aisstream.io."""

from datetime import datetime, timezone, timedelta
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, computed_field


class Dimension(BaseModel):
    """Ship dimensions from AIS static data (type 5 message)."""

    model_config = ConfigDict(from_attributes=True)

    A: int = Field(..., ge=0, description="Distance from reference point to bow")
    B: int = Field(..., ge=0, description="Distance from reference point to stern")
    C: int = Field(..., ge=0, description="Distance from reference point to port")
    D: int = Field(..., ge=0, description="Distance from reference point to starboard")

    @computed_field
    @property
    def length(self) -> int:
        """Overall vessel length = A + B."""
        return self.A + self.B


class PositionReport(BaseModel):
    """Parsed AIS position report with validation.

    Field ranges follow ITU-R M.1371-5 standard.
    Values at 'not available' markers are rejected.
    """

    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    mmsi: int = Field(..., ge=100000000, le=999999999, description="9-digit MMSI, reject 000000000")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Reject 181 (not available)")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Reject 91 (not available)")
    sog: Optional[float] = Field(None, ge=0.0, le=102.2, description="Reject 102.3 (not available)")
    cog: Optional[float] = Field(None, ge=0.0, le=359.9, description="Reject 360 (not available)")
    heading: Optional[int] = Field(None, ge=0, le=359, description="Reject 511 (not available)")
    nav_status: Optional[int] = Field(None, ge=0, le=15)
    rot: Optional[float] = Field(None, ge=-127.0, le=127.0, description="Reject -128 (not available)")

    @field_validator("timestamp")
    @classmethod
    def reject_future_timestamp(cls, v: datetime) -> datetime:
        """Reject timestamps more than 5 minutes in the future."""
        now = datetime.now(timezone.utc)
        # Ensure v is timezone-aware for comparison
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v > now + timedelta(minutes=5):
            raise ValueError("Timestamp is more than 5 minutes in the future")
        return v


class ShipStaticData(BaseModel):
    """AIS static and voyage-related data (message types 5, 24)."""

    model_config = ConfigDict(from_attributes=True)

    mmsi: int = Field(..., ge=100000000, le=999999999)
    imo: Optional[int] = None
    ship_name: Optional[str] = None
    ship_type: Optional[int] = None
    dimension: Optional[Dimension] = None

    @computed_field
    @property
    def length(self) -> Optional[int]:
        """Ship length computed from dimensions A + B, or None if no dimensions."""
        if self.dimension is not None:
            return self.dimension.length
        return None
