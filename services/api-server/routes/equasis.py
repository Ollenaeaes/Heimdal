"""Equasis upload endpoints for the Heimdal API server.

Provides:
- POST /api/equasis/upload — upload and process an Equasis Ship/Company Folder PDF
- GET /api/equasis/{mmsi}/history — list all equasis uploads for a vessel
- GET /api/equasis/{mmsi}/upload/{upload_id} — get a specific equasis upload
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from itertools import combinations
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from shared.db.connection import get_session
from shared.db.repositories import (
    get_equasis_upload_by_id,
    get_vessel_profile_by_mmsi,
    insert_company_upload,
    insert_equasis_data,
    list_equasis_uploads,
    update_vessel_profile_from_equasis,
    upsert_fleet_vessel,
    upsert_vessel_profile,
)
from shared.db.network_repository import upsert_network_edge

from shared.constants import normalize_flag

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
    """Upload and process an Equasis Ship Folder or Company Folder PDF.

    Detects document type automatically and routes to the appropriate handler.
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
                detail="Not a valid Equasis PDF: missing expected sections",
            )
        raise HTTPException(
            status_code=400,
            detail="Invalid file: could not parse as PDF",
        )

    # 3. Route by document type
    doc_type = parsed.get("document_type", "ship_folder")

    if doc_type == "company_folder":
        return await _handle_company_folder(request, parsed, mmsi)
    else:
        return await _handle_ship_folder(request, parsed, mmsi)


async def _handle_ship_folder(request: Request, parsed: dict, mmsi: Optional[int]) -> dict:
    """Process a ship folder upload."""
    ship_particulars = parsed.get("ship_particulars", {})
    pdf_imo = ship_particulars.get("imo")
    pdf_mmsi = ship_particulars.get("mmsi")

    session_factory = get_session()
    created = False

    async with session_factory() as session:
        if mmsi is not None:
            vessel = await get_vessel_profile_by_mmsi(session, mmsi)
            if not vessel:
                raise HTTPException(status_code=404, detail="Vessel not found")

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
            resolved_mmsi = mmsi
        else:
            vessel = None
            if pdf_mmsi is not None:
                vessel = await get_vessel_profile_by_mmsi(session, pdf_mmsi)

            if vessel:
                resolved_mmsi = pdf_mmsi
            else:
                resolved_mmsi = pdf_mmsi
                profile_data = {
                    "mmsi": resolved_mmsi,
                    "imo": pdf_imo,
                    "ship_name": ship_particulars.get("name"),
                    "ship_type": None,
                    "ship_type_text": ship_particulars.get("ship_type"),
                    "flag_country": normalize_flag(ship_particulars.get("flag")),
                    "call_sign": ship_particulars.get("call_sign"),
                    "length": None, "width": None, "draught": None,
                    "destination": None, "eta": None,
                    "last_position_time": None, "last_lat": None, "last_lon": None,
                    "risk_score": 0, "risk_tier": "green",
                    "sanctions_status": None, "pi_tier": None, "pi_details": None,
                    "owner": None, "operator": None, "insurer": None, "class_society": None,
                    "build_year": ship_particulars.get("build_year"),
                    "dwt": ship_particulars.get("dwt"),
                    "gross_tonnage": ship_particulars.get("gross_tonnage"),
                    "group_owner": None, "registered_owner": None, "technical_manager": None,
                    "ownership_data": None, "classification_data": None,
                    "insurance_data": None, "enrichment_status": None, "enriched_at": None,
                }
                await upsert_vessel_profile(session, profile_data)
                created = True

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

        # Update vessel_profiles fields from equasis data
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

        class_society = None
        for entry in classification_status:
            if entry.get("status") == "Delivered":
                class_society = entry.get("society")
                break

        p_and_i = parsed.get("p_and_i", [])
        insurer = None
        if p_and_i and isinstance(p_and_i, list):
            insurer = p_and_i[0].get("insurer")

        # Build structured ownership_data JSONB from full management entries
        ownership_entries = []
        for entry in management:
            ownership_entries.append({
                "role": (entry.get("role") or "").strip(),
                "company_name": entry.get("company_name"),
                "company_imo": entry.get("company_imo"),
                "address": entry.get("address"),
                "date_of_effect": entry.get("date_of_effect"),
            })

        ownership_data_json = json.dumps(ownership_entries) if ownership_entries else None

        update_data = {
            "registered_owner": registered_owner,
            "technical_manager": technical_manager,
            "operator": operator,
            "class_society": class_society,
            "insurer": insurer,
            "build_year": ship_particulars.get("build_year"),
            "dwt": ship_particulars.get("dwt"),
            "gross_tonnage": ship_particulars.get("gross_tonnage"),
            "flag_country": normalize_flag(ship_particulars.get("flag")),
            "ship_name": ship_particulars.get("name"),
            "call_sign": ship_particulars.get("call_sign"),
            "ship_type_text": ship_particulars.get("ship_type"),
            "ownership_data": ownership_data_json,
        }
        await update_vessel_profile_from_equasis(session, resolved_mmsi, update_data)

        await session.commit()

    # Publish re-scoring event
    _publish_rescoring(request, [resolved_mmsi])

    return {
        "document_type": "ship_folder",
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


async def _handle_company_folder(request: Request, parsed: dict, mmsi: Optional[int]) -> dict:
    """Process a company folder upload: extract fleet, create vessels, build network edges."""
    company = parsed.get("company_particulars", {})
    company_imo = company.get("company_imo")
    company_name = company.get("company_name")
    company_address = company.get("address")
    fleet_list = parsed.get("fleet", [])
    inspection_synthesis = parsed.get("inspection_synthesis", [])

    if not company_imo:
        raise HTTPException(status_code=422, detail="Could not extract company IMO from PDF")

    session_factory = get_session()
    vessels_created = 0
    vessels_updated = 0
    edges_created = 0
    fleet_mmsis: list[int] = []
    fleet_details: list[dict] = []

    async with session_factory() as session:
        # Process each vessel in the fleet list
        for vessel_data in fleet_list:
            imo = vessel_data.get("imo")
            if not imo:
                continue

            # Prepare data for upsert
            upsert_data = {
                "ship_name": vessel_data.get("ship_name"),
                "gross_tonnage": vessel_data.get("gross_tonnage"),
                "ship_type_text": vessel_data.get("ship_type"),
                "flag_country": normalize_flag(vessel_data.get("current_flag")),
                "build_year": vessel_data.get("year_of_build"),
                "class_society": vessel_data.get("current_class"),
                "registered_owner": company_name,
            }

            vessel_mmsi, was_created = await upsert_fleet_vessel(session, imo, upsert_data)
            fleet_mmsis.append(vessel_mmsi)

            if was_created:
                vessels_created += 1
            else:
                vessels_updated += 1

            status = "new" if was_created else "updated"
            fleet_details.append({
                "imo": imo,
                "mmsi": vessel_mmsi,
                "name": vessel_data.get("ship_name"),
                "type": vessel_data.get("ship_type"),
                "flag": vessel_data.get("current_flag"),
                "status": status,
            })

        # Create ownership network edges between ALL fleet vessels (all-pairs)
        edge_details = {
            "company_imo": company_imo,
            "company_name": company_name,
            "source": "equasis_upload",
        }
        for mmsi_a, mmsi_b in combinations(fleet_mmsis, 2):
            await upsert_network_edge(
                session,
                mmsi_a,
                mmsi_b,
                edge_type="ownership",
                confidence=1.0,
                details=edge_details,
            )
            edges_created += 1

        # Store the company upload audit record
        edition_date = None
        if parsed.get("edition_date"):
            try:
                edition_date = datetime.strptime(parsed["edition_date"], "%d/%m/%Y").date()
            except (ValueError, TypeError):
                pass

        upload_record = {
            "company_imo": company_imo,
            "company_name": company_name,
            "company_address": company_address,
            "edition_date": edition_date,
            "fleet_size": len(fleet_list),
            "vessels_created": vessels_created,
            "vessels_updated": vessels_updated,
            "edges_created": edges_created,
            "inspection_synthesis": json.dumps(inspection_synthesis),
            "parsed_data": json.dumps(parsed),
        }
        upload_id = await insert_company_upload(session, upload_record)

        await session.commit()

    # Publish re-scoring for all fleet vessels
    _publish_rescoring(request, fleet_mmsis)

    return {
        "document_type": "company_folder",
        "upload_id": upload_id,
        "company_imo": company_imo,
        "company_name": company_name,
        "fleet_size": len(fleet_list),
        "vessels_created": vessels_created,
        "vessels_updated": vessels_updated,
        "network_edges_created": edges_created,
        "fleet": fleet_details,
        "scoring_triggered_for": len(fleet_mmsis),
    }


def _publish_rescoring(request: Request, mmsis: list[int]) -> None:
    """Publish re-scoring events for a list of MMSIs."""
    if not mmsis:
        return
    try:
        import asyncio
        redis = request.app.state.redis
        event = json.dumps({
            "mmsis": mmsis,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(mmsis),
        })
        asyncio.create_task(redis.publish("heimdal:positions", event))
        logger.info("Published re-scoring event for %d vessels", len(mmsis))
    except Exception:
        logger.warning("Failed to publish re-scoring events", exc_info=True)


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
