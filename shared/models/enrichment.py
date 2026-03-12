"""Manual enrichment model for analyst-provided data."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ManualEnrichment(BaseModel):
    """Analyst-provided enrichment record for a vessel."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    mmsi: int = Field(..., ge=100000000, le=999999999)
    analyst_notes: Optional[str] = None
    source: Optional[str] = None
    pi_tier: Optional[
        Literal[
            "ig_member",
            "non_ig_western",
            "russian_state",
            "unknown",
            "fraudulent",
            "none",
        ]
    ] = None
    confidence: Optional[float] = None
    attachments: list = Field(default_factory=list)
    created_at: Optional[datetime] = None
