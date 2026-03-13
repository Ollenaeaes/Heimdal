"""Equasis upload endpoints for the Heimdal API server.

Provides:
- POST /api/equasis/upload — upload and process an Equasis Ship Folder PDF
- GET /api/equasis/{mmsi}/history — list all equasis uploads for a vessel
- GET /api/equasis/{mmsi}/upload/{upload_id} — get a specific equasis upload
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from shared.db.connection import get_session
from shared.db.repositories import (
    get_equasis_upload_by_id,
    get_vessel_profile_by_mmsi,
    insert_equasis_data,
    list_equasis_uploads,
    update_vessel_profile_from_equasis,
    upsert_vessel_profile,
)

from equasis_parser import parse_equasis_pdf

logger = logging.getLogger("api-server.equasis")

router = APIRouter(prefix="/api/equasis", tags=["equasis"])

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


@router.post("/upload", status_code=201)
async def upload_equasis_pdf_endpoint(
    request: Request,
    file: UploadFile = File(...),
    mmsi: Optional[int] = Query(None),
):
    """Upload and process an Equasis Ship Folder PDF.

    Parses the PDF, validates IMO/MMSI, stores data, updates vessel profile,
    and triggers re-scoring.
    """
    # 1. Read and validate file size
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    # 2. Parse PDF
    try:
        parsed = parse_equasis_pdf(pdf_bytes)
    except ValueError as exc:
        msg = str(exc)
        if "Not a valid Equasis" in msg or "missing expected sections" in msg:
            raise HTTPException(
                status_code=422,
                detail="Not an Equasis Ship Folder: missing expected sections",
            )
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file: could not parse as PDF",
        )

    # 3. Extract IMO and MMSI from parsed ship_particulars
    ship_particulars = parsed.get("ship_particulars", {})
    pdf_imo = ship_particulars.get("imo")
    pdf_mmsi = ship_particulars.get("mmsi")

    session_factory = get_session()
    created = False
    vessel = None

    async with session_factory() as session:
        # 4/5. Resolve vessel
        if mmsi is not None:
            # mmsi query param provided — look up by that mmsi
            vessel = await get_vessel_profile_by_mmsi(session, mmsi)
            if not vessel:
                raise HTTPException(status_code=404, detail="Vessel not found")

            # Verify IMO or MMSI from PDF matches
            vessel_imo = vessel.get("imo")
            vessel_mmsi = vessel.get("mmsi")
            imo_match = pdf_imo is not None and vessel_imo is not None and pdf_imo == vessel_imo
            mmsi_match = pdf_mmsi is not None and vessel_mmsi is not None and pdf_mmsi == vessel_mmsi
            if not imo_match and not mmsi_match:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"PDF vessel (IMO={pdf_imo}, MMSI={pdf_mmsi}) does not match "
                        f"target vessel (IMO={vessel_imo}, MMSI={vessel_mmsi})"
                    ),
                )
            # Use the provided mmsi as the canonical one
            resolved_mmsi = mmsi
        else:
            # No mmsi param — try to find vessel by PDF's MMSI
            if pdf_mmsi is not None:
                vessel = await get_vessel_profile_by_mmsi(session, pdf_mmsi)

            if vessel:
                resolved_mmsi = pdf_mmsi
            else:
                # Create a new vessel profile from the PDF data
                resolved_mmsi = pdf_mmsi
                profile_data = {
                    "mmsi": resolved_mmsi,
                    "imo": pdf_imo,
                    "ship_name": ship_particulars.get("name"),
                    "ship_type": None,
                    "ship_type_text": ship_particulars.get("ship_type"),
                    "flag_country": ship_particulars.get("flag"),
                    "call_sign": ship_particulars.get("call_sign"),
                    "length": None,
                    "width": None,
                    "draught": None,
                    "destination": None,
                    "eta": None,
                    "last_position_time": None,
                    "last_lat": None,
                    "last_lon": None,
                    "risk_score": 0,
                    "risk_tier": "green",
                    "sanctions_status": None,
                    "pi_tier": None,
                    "pi_details": None,
                    "owner": None,
                    "operator": None,
                    "insurer": None,
                    "class_society": None,
                    "build_year": ship_particulars.get("build_year"),
                    "dwt": ship_particulars.get("dwt"),
                    "gross_tonnage": ship_particulars.get("gross_tonnage"),
                    "group_owner": None,
                    "registered_owner": None,
                    "technical_manager": None,
                    "ownership_data": None,
                    "classification_data": None,
                    "insurance_data": None,
                    "enrichment_status": None,
                    "enriched_at": None,
                }
                await upsert_vessel_profile(session, profile_data)
                created = True

        # 6. Insert into equasis_data
        management = parsed.get("management", [])
        classification_status = parsed.get("classification_status", [])
        psc_inspections = parsed.get("psc_inspections", [])
        flag_history = parsed.get("flag_history", [])
        company_history = parsed.get("company_history", [])
        name_history = parsed.get("name_history", [])

        equasis_row = {
            "mmsi": resolved_mmsi,
            "imo": pdf_imo,
            "upload_timestamp": datetime.now(timezone.utc),
            "edition_date": (
            datetime.strptime(parsed["edition_date"], "%d/%m/%Y").date()
            if parsed.get("edition_date")
            else None
        ),
            "ship_particulars": json.dumps(ship_particulars),
            "management": json.dumps(management),
            "classification_status": json.dumps(classification_status),
            "classification_surveys": json.dumps(parsed.get("classification_surveys", [])),
            "safety_certificates": json.dumps(parsed.get("safety_certificates", [])),
            "psc_inspections": json.dumps(psc_inspections),
            "name_history": json.dumps(name_history),
            "flag_history": json.dumps(flag_history),
            "company_history": json.dumps(company_history),
            "raw_extracted": json.dumps(parsed),
        }
        equasis_data_id = await insert_equasis_data(session, equasis_row)

        # 7. Update vessel_profiles fields from equasis data
        # Extract management roles
        registered_owner = None
        technical_manager = None
        operator = None
        for entry in management:
            role = (entry.get("role") or "").strip()
            company_name = entry.get("company_name")
            if "Registered owner" in role:
                registered_owner = company_name
            elif "ISM Manager" in role:
                technical_manager = company_name
            elif "Ship manager" in role:
                operator = company_name

        # Extract class society from classification_status (first "Delivered" entry)
        class_society = None
        for entry in classification_status:
            if entry.get("status") == "Delivered":
                class_society = entry.get("society")
                break

        update_data = {
            "registered_owner": registered_owner,
            "technical_manager": technical_manager,
            "operator": operator,
            "class_society": class_society,
            "build_year": ship_particulars.get("build_year"),
            "dwt": ship_particulars.get("dwt"),
            "gross_tonnage": ship_particulars.get("gross_tonnage"),
            "flag_country": ship_particulars.get("flag"),
            "ship_name": ship_particulars.get("name"),
            "call_sign": ship_particulars.get("call_sign"),
            "ship_type_text": ship_particulars.get("ship_type"),
        }
        await update_vessel_profile_from_equasis(session, resolved_mmsi, update_data)

        await session.commit()

    # 8. Publish re-scoring event to Redis
    try:
        redis = request.app.state.redis
        event = json.dumps({
            "mmsis": [resolved_mmsi],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": 1,
        })
        await redis.publish("heimdal:positions", event)
        logger.info("Published re-scoring event for MMSI %s", resolved_mmsi)
    except Exception:
        logger.warning(
            "Failed to publish re-scoring event for MMSI %s",
            resolved_mmsi,
            exc_info=True,
        )

    # 9. Return summary
    return {
        "mmsi": resolved_mmsi,
        "imo": pdf_imo,
        "ship_name": ship_particulars.get("name"),
        "created": created,
        "equasis_data_id": equasis_data_id,
        "summary": {
            "psc_inspections": len(psc_inspections),
            "flag_changes": len(flag_history),
            "companies": len(company_history),
            "classification_entries": len(classification_status),
            "name_changes": len(name_history),
        },
    }


@router.get("/{mmsi}/history")
async def get_equasis_history(mmsi: int):
    """List all equasis uploads for a vessel."""
    session_factory = get_session()
    async with session_factory() as session:
        uploads = await list_equasis_uploads(session, mmsi)
    return {"mmsi": mmsi, "uploads": uploads}


@router.get("/{mmsi}/upload/{upload_id}")
async def get_equasis_upload(mmsi: int, upload_id: int):
    """Get a specific equasis upload by ID."""
    session_factory = get_session()
    async with session_factory() as session:
        upload = await get_equasis_upload_by_id(session, upload_id)
    if not upload or upload.get("mmsi") != mmsi:
        raise HTTPException(status_code=404, detail="Upload not found")
    return upload
