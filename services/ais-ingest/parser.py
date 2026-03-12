"""AIS message parser for aisstream.io JSON format.

Parses raw WebSocket messages into validated Pydantic models.
Returns None for messages that fail validation (invalid MMSI,
out-of-range coordinates, etc.).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Union

from pydantic import ValidationError

from shared.models.ais_message import Dimension, PositionReport, ShipStaticData

logger = logging.getLogger(__name__)

# AIS "not available" sentinel values (ITU-R M.1371-5)
_SOG_NOT_AVAILABLE = 102.3
_COG_NOT_AVAILABLE = 360.0
_HEADING_NOT_AVAILABLE = 511
_ROT_NOT_AVAILABLE = -128


def _parse_timestamp(meta: dict) -> Optional[datetime]:
    """Extract and parse timestamp from MetaData.time_utc."""
    raw = meta.get("time_utc")
    if raw is None:
        return None
    try:
        # aisstream.io uses ISO 8601 format
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        logger.warning("Failed to parse timestamp: %s", raw)
        return None


def _clean_optional_float(
    value: Optional[float], not_available: float
) -> Optional[float]:
    """Return None if value matches the 'not available' sentinel."""
    if value is None:
        return None
    if value == not_available:
        return None
    return value


def _clean_optional_int(
    value: Optional[int], not_available: int
) -> Optional[int]:
    """Return None if value matches the 'not available' sentinel."""
    if value is None:
        return None
    if value == not_available:
        return None
    return value


def parse_position_report(raw: dict) -> Optional[PositionReport]:
    """Parse an aisstream.io PositionReport message into a Pydantic model.

    Returns None if the message is malformed or fails validation.
    """
    try:
        meta = raw.get("MetaData", {})
        mmsi = meta.get("MMSI")
        timestamp = _parse_timestamp(meta)

        if mmsi is None or timestamp is None:
            logger.debug("Missing MMSI or timestamp in PositionReport")
            return None

        msg = raw.get("Message", {}).get("PositionReport", {})
        if not msg:
            logger.debug("Missing Message.PositionReport payload")
            return None

        sog = _clean_optional_float(msg.get("Sog"), _SOG_NOT_AVAILABLE)
        cog = _clean_optional_float(msg.get("Cog"), _COG_NOT_AVAILABLE)
        heading = _clean_optional_int(msg.get("TrueHeading"), _HEADING_NOT_AVAILABLE)
        rot = _clean_optional_float(msg.get("RateOfTurn"), _ROT_NOT_AVAILABLE)

        return PositionReport(
            timestamp=timestamp,
            mmsi=mmsi,
            latitude=msg.get("Latitude", 91.0),  # will fail validation if missing
            longitude=msg.get("Longitude", 181.0),
            sog=sog,
            cog=cog,
            heading=heading,
            nav_status=msg.get("NavigationalStatus"),
            rot=rot,
        )
    except ValidationError as e:
        logger.debug("PositionReport validation failed: %s", e)
        return None
    except Exception as e:
        logger.warning("Unexpected error parsing PositionReport: %s", e)
        return None


def parse_ship_static_data(raw: dict) -> Optional[ShipStaticData]:
    """Parse an aisstream.io ShipStaticData message into a Pydantic model.

    Returns None if the message is malformed or fails validation.
    """
    try:
        meta = raw.get("MetaData", {})
        mmsi = meta.get("MMSI")

        if mmsi is None:
            logger.debug("Missing MMSI in ShipStaticData")
            return None

        msg = raw.get("Message", {}).get("ShipStaticData")
        if msg is None:
            logger.debug("Missing Message.ShipStaticData payload")
            return None

        # Build Dimension if present
        dim_data = msg.get("Dimension")
        dimension = None
        if dim_data and isinstance(dim_data, dict):
            try:
                dimension = Dimension(
                    A=dim_data.get("A", 0),
                    B=dim_data.get("B", 0),
                    C=dim_data.get("C", 0),
                    D=dim_data.get("D", 0),
                )
            except ValidationError:
                dimension = None

        return ShipStaticData(
            mmsi=mmsi,
            imo=msg.get("ImoNumber") or None,
            ship_name=msg.get("Name") or None,
            ship_type=msg.get("Type"),
            dimension=dimension,
        )
    except ValidationError as e:
        logger.debug("ShipStaticData validation failed: %s", e)
        return None
    except Exception as e:
        logger.warning("Unexpected error parsing ShipStaticData: %s", e)
        return None


def parse_vessel_extras(raw: dict) -> dict:
    """Extract additional vessel fields not in the Pydantic model.

    Returns a dict with call_sign, destination, eta, draught, beam
    for use with upsert_vessel_profile.
    """
    msg = raw.get("Message", {}).get("ShipStaticData", {})
    if not msg:
        return {}

    extras: dict = {}

    if msg.get("CallSign"):
        extras["call_sign"] = msg["CallSign"]
    if msg.get("Destination"):
        extras["destination"] = msg["Destination"]
    if msg.get("MaximumStaticDraught"):
        extras["draught"] = msg["MaximumStaticDraught"]

    # ETA: build datetime from Month/Day/Hour/Minute
    eta_data = msg.get("Eta")
    if eta_data and isinstance(eta_data, dict):
        try:
            month = eta_data.get("Month", 0)
            day = eta_data.get("Day", 0)
            hour = eta_data.get("Hour", 0)
            minute = eta_data.get("Minute", 0)
            if 1 <= month <= 12 and 1 <= day <= 31:
                now = datetime.now(timezone.utc)
                year = now.year
                # If ETA month is earlier than current month, assume next year
                if month < now.month:
                    year += 1
                eta = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
                extras["eta"] = eta
        except (ValueError, TypeError):
            pass

    # Beam from Dimension C + D
    dim_data = msg.get("Dimension")
    if dim_data and isinstance(dim_data, dict):
        c = dim_data.get("C", 0)
        d = dim_data.get("D", 0)
        if c + d > 0:
            extras["beam"] = c + d

    return extras


def parse_message(raw: dict) -> Optional[Union[PositionReport, ShipStaticData]]:
    """Parse any aisstream.io message into the appropriate Pydantic model.

    Returns None if the message type is unsupported or validation fails.
    """
    msg_type = raw.get("MessageType")

    if msg_type == "PositionReport":
        return parse_position_report(raw)
    elif msg_type == "ShipStaticData":
        return parse_ship_static_data(raw)
    else:
        logger.debug("Unsupported message type: %s", msg_type)
        return None
