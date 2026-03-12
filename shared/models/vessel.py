"""Vessel domain models: positions and profiles."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VesselPosition(BaseModel):
    """A single AIS position report stored in the database."""

    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    mmsi: int = Field(..., ge=100000000, le=999999999, description="9-digit MMSI")
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    sog: Optional[float] = Field(None, ge=0.0, le=102.2, description="Speed over ground in knots")
    cog: Optional[float] = Field(None, ge=0.0, le=359.9, description="Course over ground in degrees")
    heading: Optional[float] = Field(None, ge=0.0, le=359.0, description="True heading in degrees")
    nav_status: Optional[int] = Field(None, ge=0, le=15)
    rot: Optional[float] = Field(None, ge=-127.0, le=127.0, description="Rate of turn")
    draught: Optional[float] = None


class VesselProfile(BaseModel):
    """Vessel registry / enrichment profile (mirrors vessel_profiles table)."""

    model_config = ConfigDict(from_attributes=True)

    mmsi: int = Field(..., ge=100000000, le=999999999, description="9-digit MMSI (primary key)")
    imo: Optional[int] = None
    ship_name: Optional[str] = None
    ship_type: Optional[int] = None
    ship_type_text: Optional[str] = None
    flag_country: Optional[str] = None
    call_sign: Optional[str] = None
    length: Optional[float] = None
    width: Optional[float] = None
    draught: Optional[float] = None
    destination: Optional[str] = None
    eta: Optional[datetime] = None
    last_position_time: Optional[datetime] = None
    last_lat: Optional[float] = None
    last_lon: Optional[float] = None
    risk_score: float = 0.0
    risk_tier: str = "green"
    sanctions_status: dict = Field(default_factory=dict)
    pi_tier: str = "none"
    pi_details: dict = Field(default_factory=dict)
    owner: Optional[str] = None
    operator: Optional[str] = None
    insurer: Optional[str] = None
    class_society: Optional[str] = None
    build_year: Optional[int] = None
    dwt: Optional[int] = None
    gross_tonnage: Optional[int] = None
    group_owner: Optional[str] = None
    registered_owner: Optional[str] = None
    technical_manager: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
