"""Tests for AIS message parser."""

import json
from pathlib import Path

import pytest

from shared.models.ais_message import PositionReport, ShipStaticData

# Add services to path so we can import the parser
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "ais-ingest"))

from parser import (
    parse_message,
    parse_position_report,
    parse_ship_static_data,
    parse_vessel_extras,
)


@pytest.fixture
def fixtures():
    """Load sample AIS messages from fixtures file."""
    path = Path(__file__).resolve().parent / "fixtures" / "sample_ais_messages.json"
    with open(path) as f:
        return json.load(f)


# ===================================================================
# PositionReport parsing tests
# ===================================================================


class TestParsePositionReport:
    """Tests for position report parsing."""

    def test_standard_position_report(self, fixtures):
        msg = fixtures["valid_position_reports"][0]
        result = parse_position_report(msg)
        assert result is not None
        assert isinstance(result, PositionReport)
        assert result.mmsi == 259000420
        assert result.latitude == 68.123
        assert result.longitude == 15.456
        assert result.sog == 12.3
        assert result.cog == 180.5
        assert result.heading == 179
        assert result.nav_status == 0
        assert result.rot == 5.0

    def test_all_valid_position_reports_parse(self, fixtures):
        for msg in fixtures["valid_position_reports"]:
            result = parse_position_report(msg)
            assert result is not None, f"Failed to parse: {msg['description']}"
            assert isinstance(result, PositionReport)

    def test_timestamp_extracted_from_metadata(self, fixtures):
        msg = fixtures["valid_position_reports"][0]
        result = parse_position_report(msg)
        assert result is not None
        assert result.timestamp.year == 2024
        assert result.timestamp.month == 1
        assert result.timestamp.day == 15
        assert result.timestamp.hour == 10
        assert result.timestamp.minute == 30

    def test_vessel_at_equator_prime_meridian(self, fixtures):
        msg = fixtures["valid_position_reports"][9]
        result = parse_position_report(msg)
        assert result is not None
        assert result.latitude == 0.0
        assert result.longitude == 0.0

    def test_vessel_at_extreme_valid_coordinates(self, fixtures):
        msg = fixtures["valid_position_reports"][10]
        result = parse_position_report(msg)
        assert result is not None
        assert result.latitude == 90.0
        assert result.longitude == 180.0

    def test_vessel_at_extreme_negative_coordinates(self, fixtures):
        msg = fixtures["valid_position_reports"][11]
        result = parse_position_report(msg)
        assert result is not None
        assert result.latitude == -90.0
        assert result.longitude == -180.0

    def test_max_valid_sog(self, fixtures):
        msg = fixtures["valid_position_reports"][12]
        result = parse_position_report(msg)
        assert result is not None
        assert result.sog == 102.2

    def test_max_valid_rot(self, fixtures):
        msg = fixtures["valid_position_reports"][13]
        result = parse_position_report(msg)
        assert result is not None
        assert result.rot == 127.0

    def test_negative_rot(self, fixtures):
        msg = fixtures["valid_position_reports"][14]
        result = parse_position_report(msg)
        assert result is not None
        assert result.rot == -127.0

    # --- Not available markers ---

    def test_sog_not_available_becomes_none(self, fixtures):
        msg = fixtures["not_available_markers"][0]
        result = parse_position_report(msg)
        assert result is not None
        assert result.sog is None

    def test_cog_not_available_becomes_none(self, fixtures):
        msg = fixtures["not_available_markers"][1]
        result = parse_position_report(msg)
        assert result is not None
        assert result.cog is None

    def test_heading_not_available_becomes_none(self, fixtures):
        msg = fixtures["not_available_markers"][2]
        result = parse_position_report(msg)
        assert result is not None
        assert result.heading is None

    def test_rot_not_available_becomes_none(self, fixtures):
        msg = fixtures["not_available_markers"][3]
        result = parse_position_report(msg)
        assert result is not None
        assert result.rot is None

    def test_all_not_available_at_once(self, fixtures):
        msg = fixtures["not_available_markers"][4]
        result = parse_position_report(msg)
        assert result is not None
        assert result.sog is None
        assert result.cog is None
        assert result.heading is None
        assert result.rot is None
        # Core fields should still be present
        assert result.mmsi == 259000425
        assert result.latitude == 68.123

    # --- Invalid messages return None ---

    def test_mmsi_too_short_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][0]
        result = parse_position_report(msg)
        assert result is None

    def test_mmsi_too_long_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][1]
        result = parse_position_report(msg)
        assert result is None

    def test_mmsi_zero_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][2]
        result = parse_position_report(msg)
        assert result is None

    def test_latitude_91_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][3]
        result = parse_position_report(msg)
        assert result is None

    def test_latitude_negative_91_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][4]
        result = parse_position_report(msg)
        assert result is None

    def test_longitude_181_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][5]
        result = parse_position_report(msg)
        assert result is None

    def test_longitude_negative_181_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][6]
        result = parse_position_report(msg)
        assert result is None

    def test_missing_metadata_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][7]
        result = parse_position_report(msg)
        assert result is None

    def test_missing_mmsi_in_metadata_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][8]
        result = parse_position_report(msg)
        assert result is None

    def test_missing_timestamp_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][9]
        result = parse_position_report(msg)
        assert result is None

    def test_missing_message_payload_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][10]
        result = parse_position_report(msg)
        assert result is None

    def test_empty_position_report_payload_returns_none(self, fixtures):
        """Empty PositionReport has no lat/lon, should fail validation."""
        msg = fixtures["invalid_messages"][11]
        result = parse_position_report(msg)
        assert result is None

    def test_missing_latitude_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][12]
        result = parse_position_report(msg)
        assert result is None

    def test_missing_longitude_returns_none(self, fixtures):
        msg = fixtures["invalid_messages"][13]
        result = parse_position_report(msg)
        assert result is None

    def test_all_invalid_messages_return_none(self, fixtures):
        for msg in fixtures["invalid_messages"]:
            result = parse_position_report(msg)
            assert result is None, f"Should have rejected: {msg['description']}"


# ===================================================================
# ShipStaticData parsing tests
# ===================================================================


class TestParseShipStaticData:
    """Tests for ship static data parsing."""

    def test_full_static_data(self, fixtures):
        msg = fixtures["valid_static_data"][0]
        result = parse_ship_static_data(msg)
        assert result is not None
        assert isinstance(result, ShipStaticData)
        assert result.mmsi == 259000420
        assert result.imo == 9876543
        assert result.ship_name == "NORDIC EXPLORER"
        assert result.ship_type == 70
        assert result.dimension is not None
        assert result.dimension.A == 100
        assert result.dimension.B == 50
        assert result.length == 150

    def test_all_valid_static_data_parse(self, fixtures):
        for msg in fixtures["valid_static_data"]:
            result = parse_ship_static_data(msg)
            assert result is not None, f"Failed to parse: {msg['description']}"

    def test_tanker_dimensions(self, fixtures):
        msg = fixtures["valid_static_data"][1]
        result = parse_ship_static_data(msg)
        assert result is not None
        assert result.dimension.A == 200
        assert result.dimension.B == 130
        assert result.length == 330

    def test_fishing_vessel_zero_imo_becomes_none(self, fixtures):
        msg = fixtures["valid_static_data"][2]
        result = parse_ship_static_data(msg)
        assert result is not None
        # ImoNumber 0 should be treated as None (falsy)
        assert result.imo is None

    def test_empty_name_becomes_none(self, fixtures):
        """Static data with empty CallSign and Destination."""
        msg = fixtures["valid_static_data"][5]
        result = parse_ship_static_data(msg)
        assert result is not None
        assert result.ship_name == "DESERT WIND"

    def test_invalid_mmsi_returns_none(self, fixtures):
        msg = fixtures["invalid_static_data"][0]
        result = parse_ship_static_data(msg)
        assert result is None

    def test_missing_mmsi_returns_none(self, fixtures):
        msg = fixtures["invalid_static_data"][1]
        result = parse_ship_static_data(msg)
        assert result is None

    def test_missing_static_data_payload_returns_none(self, fixtures):
        msg = fixtures["invalid_static_data"][2]
        result = parse_ship_static_data(msg)
        assert result is None

    def test_empty_static_data_payload(self, fixtures):
        """Empty ShipStaticData has no MMSI in the payload, but MMSI is in MetaData."""
        msg = fixtures["invalid_static_data"][3]
        result = parse_ship_static_data(msg)
        # Should still parse since MMSI comes from MetaData
        # But the payload is empty, so it's just MMSI with no other data
        assert result is not None
        assert result.mmsi == 259000420

    def test_all_invalid_static_data_return_none(self, fixtures):
        """First 3 invalid static data should return None (4th is valid edge case)."""
        for msg in fixtures["invalid_static_data"][:3]:
            result = parse_ship_static_data(msg)
            assert result is None, f"Should have rejected: {msg['description']}"


# ===================================================================
# Vessel extras parsing tests
# ===================================================================


class TestParseVesselExtras:
    """Tests for extracting extra vessel fields."""

    def test_full_extras(self, fixtures):
        msg = fixtures["valid_static_data"][0]
        extras = parse_vessel_extras(msg)
        assert extras["call_sign"] == "LABC1"
        assert extras["destination"] == "BERGEN"
        assert extras["draught"] == 8.5
        assert extras["beam"] == 30  # C(15) + D(15)
        assert "eta" in extras

    def test_empty_callsign_not_included(self, fixtures):
        msg = fixtures["valid_static_data"][5]
        extras = parse_vessel_extras(msg)
        assert "call_sign" not in extras

    def test_empty_destination_not_included(self, fixtures):
        msg = fixtures["valid_static_data"][5]
        extras = parse_vessel_extras(msg)
        assert "destination" not in extras

    def test_zero_draught_not_included(self, fixtures):
        msg = fixtures["valid_static_data"][5]
        extras = parse_vessel_extras(msg)
        assert "draught" not in extras

    def test_zero_dimensions_no_beam(self, fixtures):
        msg = fixtures["valid_static_data"][5]
        extras = parse_vessel_extras(msg)
        assert "beam" not in extras

    def test_invalid_eta_month_zero_not_included(self, fixtures):
        msg = fixtures["valid_static_data"][4]  # tug with Month=0, Day=0
        extras = parse_vessel_extras(msg)
        assert "eta" not in extras

    def test_no_message_returns_empty_dict(self):
        extras = parse_vessel_extras({})
        assert extras == {}

    def test_no_static_data_in_message_returns_empty_dict(self):
        extras = parse_vessel_extras({"Message": {}})
        assert extras == {}


# ===================================================================
# Generic parse_message dispatch tests
# ===================================================================


class TestParseMessage:
    """Tests for the top-level parse_message dispatcher."""

    def test_dispatches_position_report(self, fixtures):
        msg = fixtures["valid_position_reports"][0]
        result = parse_message(msg)
        assert isinstance(result, PositionReport)

    def test_dispatches_ship_static_data(self, fixtures):
        msg = fixtures["valid_static_data"][0]
        result = parse_message(msg)
        assert isinstance(result, ShipStaticData)

    def test_unsupported_message_type_returns_none(self, fixtures):
        for msg in fixtures["unsupported_message_types"]:
            result = parse_message(msg)
            assert result is None, f"Should have returned None for: {msg['description']}"

    def test_empty_message_returns_none(self):
        result = parse_message({})
        assert result is None

    def test_null_message_type_returns_none(self):
        result = parse_message({"MessageType": None})
        assert result is None

    def test_mmsi_boundary_lower_valid(self, fixtures):
        msg = fixtures["edge_cases"][4]
        result = parse_message(msg)
        assert result is not None
        assert result.mmsi == 100000000

    def test_mmsi_boundary_upper_valid(self, fixtures):
        msg = fixtures["edge_cases"][5]
        result = parse_message(msg)
        assert result is not None
        assert result.mmsi == 999999999

    def test_mmsi_below_lower_bound_returns_none(self, fixtures):
        msg = fixtures["edge_cases"][6]
        result = parse_message(msg)
        assert result is None

    def test_malformed_timestamp_returns_none(self, fixtures):
        msg = fixtures["edge_cases"][3]
        result = parse_message(msg)
        assert result is None
