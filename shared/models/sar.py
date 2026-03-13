"""SAR (Synthetic Aperture Radar) detection model."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SarDetection(BaseModel):
    """A dark-vessel detection from SAR imagery (sourced via GFW)."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    detection_time: datetime
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    heading_deg: Optional[float] = None
    confidence: Optional[float] = None
    is_dark: bool = False
    matched_mmsi: Optional[int] = None
    matched_category: Optional[str] = None
    match_distance_m: Optional[float] = None
    source: str = "gfw"
    gfw_detection_id: Optional[str] = None
    matching_score: Optional[float] = None
    fishing_score: Optional[float] = None
    created_at: Optional[datetime] = None
