"""Manual enrichment endpoint for the Heimdal API server.

Provides:
- POST /api/vessels/{mmsi}/enrich — create a manual enrichment record
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from shared.db.connection import get_session
from shared.db.repositories import (
    create_manual_enrichment,
    get_vessel_profile_by_mmsi,
)

logger = logging.getLogger("api-server.enrichment")

router = APIRouter(prefix="/api", tags=["enrichment"])


class EnrichmentRequest(BaseModel):
    """POST body for creating a manual enrichment record.

    Fields from the spec are mapped to the database schema:
    - source -> source
    - pi_insurer_tier -> pi_tier
    - notes -> analyst_notes
    - ownership_chain, pi_insurer, classification_society,
      classification_iacs, psc_detentions, psc_deficiencies
      -> stored in attachments JSONB
    """

    source: str = Field(..., min_length=1, description="Source of the enrichment data")
    ownership_chain: Optional[list | dict] = Field(
        None, description="Ownership chain data (stored in attachments)"
    )
    pi_insurer: Optional[str] = Field(
        None, description="P&I insurer name (stored in attachments)"
    )
    pi_insurer_tier: Optional[
        Literal[
            "ig_member",
            "non_ig_western",
            "russian_state",
            "unknown",
            "fraudulent",
            "none",
        ]
    ] = Field(None, description="P&I insurer tier classification")
    classification_society: Optional[str] = Field(
        None, description="Classification society (stored in attachments)"
    )
    classification_iacs: Optional[bool] = Field(
        None, description="Whether classification society is IACS member"
    )
    psc_detentions: Optional[int] = Field(
        None, ge=0, description="Number of port state control detentions"
    )
    psc_deficiencies: Optional[int] = Field(
        None, ge=0, description="Number of port state control deficiencies"
    )
    notes: Optional[str] = Field(None, description="Analyst notes")


@router.post("/vessels/{mmsi}/enrich", status_code=201)
async def enrich_vessel(mmsi: int, body: EnrichmentRequest, request: Request):
    """Create a manual enrichment record for a vessel.

    Validates the vessel exists, inserts enrichment data, publishes a
    re-scoring event to Redis, and returns the updated vessel profile.
    """
    session_factory = get_session()

    async with session_factory() as session:
        # Verify vessel exists
        profile = await get_vessel_profile_by_mmsi(session, mmsi)
        if not profile:
            raise HTTPException(status_code=404, detail="Vessel not found")

        # Build attachments JSONB from extra fields
        attachments: dict = {}
        if body.ownership_chain is not None:
            attachments["ownership_chain"] = body.ownership_chain
        if body.pi_insurer is not None:
            attachments["pi_insurer"] = body.pi_insurer
        if body.classification_society is not None:
            attachments["classification_society"] = body.classification_society
        if body.classification_iacs is not None:
            attachments["classification_iacs"] = body.classification_iacs
        if body.psc_detentions is not None:
            attachments["psc_detentions"] = body.psc_detentions
        if body.psc_deficiencies is not None:
            attachments["psc_deficiencies"] = body.psc_deficiencies

        # Insert enrichment record
        enrichment_data = {
            "mmsi": mmsi,
            "analyst_notes": body.notes,
            "source": body.source,
            "pi_tier": body.pi_insurer_tier,
            "confidence": None,
            "attachments": json.dumps(attachments) if attachments else "{}",
        }
        enrichment_id = await create_manual_enrichment(session, enrichment_data)
        await session.commit()

        # Re-fetch the vessel profile to include the new enrichment
        updated_profile = await get_vessel_profile_by_mmsi(session, mmsi)

        # Fetch the latest enrichment record
        enrichment_result = await session.execute(
            text(
                "SELECT * FROM manual_enrichment "
                "WHERE mmsi = :mmsi ORDER BY created_at DESC LIMIT 1"
            ),
            {"mmsi": mmsi},
        )
        enrichment_row = enrichment_result.mappings().first()
        latest_enrichment = dict(enrichment_row) if enrichment_row else None

    # Publish re-scoring event to Redis
    try:
        redis = request.app.state.redis
        await redis.publish("heimdal:positions", str(mmsi))
        logger.info("Published re-scoring event for MMSI %d", mmsi)
    except Exception:
        logger.warning("Failed to publish re-scoring event for MMSI %d", mmsi, exc_info=True)

    return {
        **updated_profile,
        "last_position": {
            "lat": updated_profile.get("last_lat"),
            "lon": updated_profile.get("last_lon"),
            "sog": None,
            "cog": None,
            "timestamp": updated_profile.get("last_position_time").isoformat()
            if updated_profile.get("last_position_time")
            else None,
        },
        "latest_enrichment": latest_enrichment,
    }
