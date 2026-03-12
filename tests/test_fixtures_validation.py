"""Tests that validate fixture files are well-formed and usable.

These tests load each fixture file, verify structural correctness,
and confirm the data matches expected Pydantic models. This ensures
fixture quality and provides additional model validation coverage.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from shared.models.ais_message import PositionReport, ShipStaticData
from shared.models.gfw_event import GfwEvent
from shared.models.sar import SarDetection
from shared.models.vessel import VesselProfile

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ===================================================================
# AIS message fixtures
# ===================================================================


class TestAisFixtures:
    """Validate sample_ais_messages.json structure and coverage."""

    @pytest.fixture
    def data(self):
        with open(FIXTURES_DIR / "sample_ais_messages.json") as f:
            return json.load(f)

    def test_has_required_sections(self, data):
        required = {
            "valid_position_reports",
            "not_available_markers",
            "invalid_messages",
            "valid_static_data",
            "invalid_static_data",
            "unsupported_message_types",
            "edge_cases",
        }
        assert required.issubset(set(data.keys()))

    def test_at_least_50_total_messages(self, data):
        total = sum(
            len(v) for k, v in data.items() if isinstance(v, list)
        )
        assert total >= 50, f"Only {total} total messages, expected >= 50"

    def test_valid_position_reports_exceed_15(self, data):
        assert len(data["valid_position_reports"]) >= 15

    def test_shadow_fleet_mmsis_present(self, data):
        """Fixture includes known shadow fleet MMSIs (Russian MID 273)."""
        mmsis = [
            msg["MetaData"]["MMSI"]
            for msg in data["valid_position_reports"]
        ]
        russian_mmsis = [m for m in mmsis if str(m).startswith("273")]
        assert len(russian_mmsis) >= 3, (
            f"Expected at least 3 Russian MMSIs, found {len(russian_mmsis)}"
        )

    def test_all_valid_positions_parse_to_model(self, data):
        """Every valid position report can construct a PositionReport model."""
        for msg in data["valid_position_reports"]:
            pr = msg["Message"]["PositionReport"]
            meta = msg["MetaData"]
            sog = pr.get("Sog")
            if sog == 102.3:
                sog = None
            cog = pr.get("Cog")
            if cog == 360.0:
                cog = None
            heading = pr.get("TrueHeading")
            if heading == 511:
                heading = None
            rot = pr.get("RateOfTurn")
            if rot == -128:
                rot = None

            report = PositionReport(
                timestamp=datetime.fromisoformat(
                    meta["time_utc"].replace("Z", "+00:00")
                ),
                mmsi=meta["MMSI"],
                latitude=pr["Latitude"],
                longitude=pr["Longitude"],
                sog=sog,
                cog=cog,
                heading=heading,
                rot=rot,
            )
            assert report.mmsi == meta["MMSI"]

    def test_all_valid_static_data_parse_to_model(self, data):
        """Every valid static data entry can construct a ShipStaticData model."""
        for msg in data["valid_static_data"]:
            sd = msg["Message"]["ShipStaticData"]
            meta = msg["MetaData"]
            imo = sd.get("ImoNumber")
            if imo == 0:
                imo = None
            ssd = ShipStaticData(
                mmsi=meta["MMSI"],
                imo=imo,
                ship_name=sd.get("Name"),
                ship_type=sd.get("Type"),
            )
            assert ssd.mmsi == meta["MMSI"]

    def test_message_type_coverage(self, data):
        """Fixture covers both PositionReport and ShipStaticData message types."""
        types = set()
        for section in data.values():
            if isinstance(section, list):
                for msg in section:
                    mt = msg.get("MessageType")
                    if mt:
                        types.add(mt)
        assert "PositionReport" in types
        assert "ShipStaticData" in types


# ===================================================================
# OpenSanctions fixtures
# ===================================================================


class TestOpenSanctionsFixtures:
    """Validate sample_opensanctions.json (NDJSON format)."""

    @pytest.fixture
    def entities(self):
        entities = []
        with open(FIXTURES_DIR / "sample_opensanctions.json") as f:
            for line in f:
                line = line.strip()
                if line:
                    entities.append(json.loads(line))
        return entities

    def test_has_15_entities(self, entities):
        assert len(entities) == 15

    def test_10_sanctioned_entities(self, entities):
        sanctioned = [
            e for e in entities
            if "sanction" in e.get("properties", {}).get("topics", [])
        ]
        assert len(sanctioned) == 10

    def test_5_non_sanctioned_entities(self, entities):
        clean = [
            e for e in entities
            if "sanction" not in e.get("properties", {}).get("topics", [])
        ]
        assert len(clean) == 5

    def test_all_entities_have_required_fields(self, entities):
        for entity in entities:
            assert "id" in entity
            assert "schema" in entity
            assert "properties" in entity
            assert "name" in entity["properties"]

    def test_ndjson_format_valid(self):
        """Each line is a valid JSON object (NDJSON format)."""
        with open(FIXTURES_DIR / "sample_opensanctions.json") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    obj = json.loads(line)
                    assert isinstance(obj, dict), f"Line {i} is not a JSON object"

    def test_sanctioned_entities_have_datasets(self, entities):
        sanctioned = [
            e for e in entities
            if "sanction" in e.get("properties", {}).get("topics", [])
        ]
        for entity in sanctioned:
            assert len(entity.get("datasets", [])) > 0, (
                f"Sanctioned entity {entity['id']} has no datasets"
            )

    def test_contains_known_shadow_fleet_vessels(self, entities):
        """Fixture includes TURBA and NS CHAMPION."""
        names = []
        for e in entities:
            names.extend(e.get("properties", {}).get("name", []))
        assert "TURBA" in names
        assert "NS CHAMPION" in names


# ===================================================================
# Vessel profile fixtures
# ===================================================================


class TestVesselProfileFixtures:
    """Validate sample_vessel_profiles.json tiers and structure."""

    @pytest.fixture
    def data(self):
        with open(FIXTURES_DIR / "sample_vessel_profiles.json") as f:
            return json.load(f)

    def test_has_three_tiers(self, data):
        assert set(data.keys()) == {"green_tier", "yellow_tier", "red_tier"}

    def test_green_tier_scores(self, data):
        for profile in data["green_tier"]:
            assert profile["risk_score"] < 30, (
                f"{profile['ship_name']} has green tier but score {profile['risk_score']}"
            )
            assert profile["risk_tier"] == "green"

    def test_yellow_tier_scores(self, data):
        for profile in data["yellow_tier"]:
            assert 30 <= profile["risk_score"] < 100, (
                f"{profile['ship_name']} has yellow tier but score {profile['risk_score']}"
            )
            assert profile["risk_tier"] == "yellow"

    def test_red_tier_scores(self, data):
        for profile in data["red_tier"]:
            assert profile["risk_score"] >= 100, (
                f"{profile['ship_name']} has red tier but score {profile['risk_score']}"
            )
            assert profile["risk_tier"] == "red"

    def test_red_tier_have_sanctions(self, data):
        for profile in data["red_tier"]:
            assert profile["sanctions_status"].get("matched") is True, (
                f"Red tier vessel {profile['ship_name']} missing sanctions match"
            )

    def test_all_profiles_have_required_fields(self, data):
        required = {"mmsi", "ship_name", "risk_score", "risk_tier"}
        for tier_name, profiles in data.items():
            for profile in profiles:
                missing = required - set(profile.keys())
                assert not missing, (
                    f"{tier_name} profile {profile.get('mmsi')} missing: {missing}"
                )

    def test_all_mmsis_are_valid_9_digit(self, data):
        for profiles in data.values():
            for profile in profiles:
                mmsi = profile["mmsi"]
                assert 100000000 <= mmsi <= 999999999, (
                    f"Invalid MMSI: {mmsi}"
                )


# ===================================================================
# GFW event fixtures
# ===================================================================


class TestGfwEventFixtures:
    """Validate sample_gfw_events.json structure and types."""

    @pytest.fixture
    def data(self):
        with open(FIXTURES_DIR / "sample_gfw_events.json") as f:
            return json.load(f)

    def test_has_all_four_event_types(self, data):
        assert set(data.keys()) == {
            "ais_disabling", "encounter", "loitering", "port_visit"
        }

    def test_each_type_has_at_least_3_events(self, data):
        for event_type, events in data.items():
            assert len(events) >= 3, (
                f"{event_type} has only {len(events)} events"
            )

    def test_all_events_parse_to_gfw_model(self, data):
        for events in data.values():
            for event in events:
                gfw = GfwEvent(
                    gfw_event_id=event["gfw_event_id"],
                    event_type=event["event_type"],
                    mmsi=event["mmsi"],
                    start_time=datetime.fromisoformat(
                        event["start_time"].replace("Z", "+00:00")
                    ),
                    end_time=(
                        datetime.fromisoformat(
                            event["end_time"].replace("Z", "+00:00")
                        )
                        if event.get("end_time")
                        else None
                    ),
                    lat=event.get("lat"),
                    lon=event.get("lon"),
                    details=event.get("details", {}),
                    encounter_mmsi=event.get("encounter_mmsi"),
                    port_name=event.get("port_name"),
                )
                assert gfw.mmsi == event["mmsi"]

    def test_encounter_events_have_encounter_mmsi(self, data):
        for event in data["encounter"]:
            assert event["encounter_mmsi"] is not None, (
                f"Encounter {event['gfw_event_id']} missing encounter_mmsi"
            )

    def test_port_visit_events_have_port_name(self, data):
        for event in data["port_visit"]:
            assert event["port_name"] is not None, (
                f"Port visit {event['gfw_event_id']} missing port_name"
            )

    def test_ais_disabling_events_have_gap_details(self, data):
        for event in data["ais_disabling"]:
            assert "gap_hours" in event["details"], (
                f"AIS disabling {event['gfw_event_id']} missing gap_hours"
            )

    def test_loitering_events_have_duration(self, data):
        for event in data["loitering"]:
            assert "loitering_hours" in event["details"], (
                f"Loitering {event['gfw_event_id']} missing loitering_hours"
            )


# ===================================================================
# SAR detection fixtures
# ===================================================================


class TestSarDetectionFixtures:
    """Validate sample_gfw_sar_detections.json structure."""

    @pytest.fixture
    def data(self):
        with open(FIXTURES_DIR / "sample_gfw_sar_detections.json") as f:
            return json.load(f)

    def test_has_dark_and_matched_sections(self, data):
        assert set(data.keys()) == {"dark_ships", "matched_ships"}

    def test_dark_ships_are_dark(self, data):
        for det in data["dark_ships"]:
            assert det["is_dark"] is True
            assert det["matched_mmsi"] is None

    def test_matched_ships_are_not_dark(self, data):
        for det in data["matched_ships"]:
            assert det["is_dark"] is False
            assert det["matched_mmsi"] is not None

    def test_at_least_5_dark_detections(self, data):
        assert len(data["dark_ships"]) >= 5

    def test_at_least_5_matched_detections(self, data):
        assert len(data["matched_ships"]) >= 5

    def test_all_detections_parse_to_sar_model(self, data):
        for section in data.values():
            for det in section:
                sar = SarDetection(
                    detection_time=datetime.fromisoformat(
                        det["detection_time"].replace("Z", "+00:00")
                    ),
                    lat=det["lat"],
                    lon=det["lon"],
                    length_m=det.get("length_m"),
                    width_m=det.get("width_m"),
                    heading_deg=det.get("heading_deg"),
                    confidence=det.get("confidence"),
                    is_dark=det["is_dark"],
                    matched_mmsi=det.get("matched_mmsi"),
                    match_distance_m=det.get("match_distance_m"),
                    source=det.get("source", "gfw"),
                    gfw_detection_id=det.get("gfw_detection_id"),
                    matching_score=det.get("matching_score"),
                    fishing_score=det.get("fishing_score"),
                )
                assert sar.source == "gfw"

    def test_matched_ships_have_matching_score(self, data):
        for det in data["matched_ships"]:
            assert det["matching_score"] > 0, (
                f"Matched detection {det['gfw_detection_id']} has zero matching_score"
            )

    def test_all_detections_have_gfw_detection_id(self, data):
        for section in data.values():
            for det in section:
                assert det["gfw_detection_id"] is not None
                assert det["gfw_detection_id"].startswith("gfw-sar-")
