"""Tests for shared Pydantic models and dataclasses."""

import dataclasses
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from shared.models.vessel import VesselPosition, VesselProfile
from shared.models.ais_message import PositionReport, ShipStaticData, Dimension
from shared.models.anomaly import AnomalyEvent, RuleResult
from shared.models.enrichment import ManualEnrichment
from shared.models.sar import SarDetection
from shared.models.gfw_event import GfwEvent


# ===================================================================
# VesselPosition tests
# ===================================================================


class TestVesselPosition:
    """VesselPosition validation tests."""

    def _valid_kwargs(self) -> dict:
        return {
            "timestamp": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "mmsi": 123456789,
            "lat": 55.0,
            "lon": 12.0,
        }

    def test_valid_position(self):
        pos = VesselPosition(**self._valid_kwargs())
        assert pos.mmsi == 123456789
        assert pos.lat == 55.0

    def test_rejects_mmsi_too_short(self):
        kw = self._valid_kwargs()
        kw["mmsi"] = 12345678  # 8 digits
        with pytest.raises(ValidationError, match="mmsi"):
            VesselPosition(**kw)

    def test_rejects_mmsi_too_long(self):
        kw = self._valid_kwargs()
        kw["mmsi"] = 1234567890  # 10 digits
        with pytest.raises(ValidationError, match="mmsi"):
            VesselPosition(**kw)

    def test_rejects_latitude_out_of_range(self):
        kw = self._valid_kwargs()
        kw["lat"] = 91.0
        with pytest.raises(ValidationError, match="lat"):
            VesselPosition(**kw)

    def test_rejects_negative_latitude_out_of_range(self):
        kw = self._valid_kwargs()
        kw["lat"] = -91.0
        with pytest.raises(ValidationError, match="lat"):
            VesselPosition(**kw)

    def test_rejects_longitude_181(self):
        kw = self._valid_kwargs()
        kw["lon"] = 181.0
        with pytest.raises(ValidationError, match="lon"):
            VesselPosition(**kw)

    def test_rejects_longitude_out_of_range(self):
        kw = self._valid_kwargs()
        kw["lon"] = -181.0
        with pytest.raises(ValidationError, match="lon"):
            VesselPosition(**kw)

    def test_rejects_sog_102_3(self):
        kw = self._valid_kwargs()
        kw["sog"] = 102.3
        with pytest.raises(ValidationError, match="sog"):
            VesselPosition(**kw)

    def test_accepts_sog_102_2(self):
        kw = self._valid_kwargs()
        kw["sog"] = 102.2
        pos = VesselPosition(**kw)
        assert pos.sog == 102.2


# ===================================================================
# PositionReport tests
# ===================================================================


class TestPositionReport:
    """PositionReport validation tests."""

    def _valid_kwargs(self) -> dict:
        return {
            "timestamp": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "mmsi": 123456789,
            "latitude": 55.0,
            "longitude": 12.0,
        }

    def test_valid_report(self):
        report = PositionReport(**self._valid_kwargs())
        assert report.mmsi == 123456789

    def test_rejects_mmsi_too_short(self):
        kw = self._valid_kwargs()
        kw["mmsi"] = 12345678
        with pytest.raises(ValidationError):
            PositionReport(**kw)

    def test_rejects_mmsi_too_long(self):
        kw = self._valid_kwargs()
        kw["mmsi"] = 1234567890
        with pytest.raises(ValidationError):
            PositionReport(**kw)

    def test_rejects_latitude_91(self):
        kw = self._valid_kwargs()
        kw["latitude"] = 91.0
        with pytest.raises(ValidationError, match="latitude"):
            PositionReport(**kw)

    def test_rejects_longitude_181(self):
        kw = self._valid_kwargs()
        kw["longitude"] = 181.0
        with pytest.raises(ValidationError, match="longitude"):
            PositionReport(**kw)

    def test_rejects_sog_102_3(self):
        kw = self._valid_kwargs()
        kw["sog"] = 102.3
        with pytest.raises(ValidationError, match="sog"):
            PositionReport(**kw)

    def test_rejects_cog_360(self):
        kw = self._valid_kwargs()
        kw["cog"] = 360.0
        with pytest.raises(ValidationError, match="cog"):
            PositionReport(**kw)

    def test_rejects_heading_511(self):
        kw = self._valid_kwargs()
        kw["heading"] = 511
        with pytest.raises(ValidationError, match="heading"):
            PositionReport(**kw)

    def test_rejects_rot_minus_128(self):
        kw = self._valid_kwargs()
        kw["rot"] = -128.0
        with pytest.raises(ValidationError, match="rot"):
            PositionReport(**kw)


# ===================================================================
# Dimension / ShipStaticData tests
# ===================================================================


class TestShipStaticData:
    """ShipStaticData and Dimension tests."""

    def test_dimension_length(self):
        dim = Dimension(A=100, B=50, C=10, D=10)
        assert dim.length == 150

    def test_ship_static_data_length_from_dimension(self):
        ssd = ShipStaticData(
            mmsi=123456789,
            dimension=Dimension(A=200, B=30, C=15, D=15),
        )
        assert ssd.length == 230

    def test_ship_static_data_length_without_dimension(self):
        ssd = ShipStaticData(mmsi=123456789)
        assert ssd.length is None


# ===================================================================
# AnomalyEvent tests
# ===================================================================


class TestAnomalyEvent:
    """AnomalyEvent validation tests."""

    def test_valid_event(self):
        event = AnomalyEvent(
            mmsi=123456789,
            rule_id="ais_gap",
            severity="critical",
            points=25.0,
        )
        assert event.severity == "critical"

    def test_rejects_invalid_severity(self):
        with pytest.raises(ValidationError, match="severity"):
            AnomalyEvent(
                mmsi=123456789,
                rule_id="ais_gap",
                severity="extreme",
                points=25.0,
            )

    def test_severity_must_be_literal(self):
        """Severity only accepts: critical, high, moderate, low."""
        for valid in ("critical", "high", "moderate", "low"):
            event = AnomalyEvent(
                mmsi=123456789,
                rule_id="test",
                severity=valid,
                points=10.0,
            )
            assert event.severity == valid

        for invalid in ("CRITICAL", "medium", "warning", "info"):
            with pytest.raises(ValidationError):
                AnomalyEvent(
                    mmsi=123456789,
                    rule_id="test",
                    severity=invalid,
                    points=10.0,
                )


# ===================================================================
# RuleResult tests
# ===================================================================


class TestRuleResult:
    """RuleResult dataclass tests."""

    def test_is_dataclass(self):
        assert dataclasses.is_dataclass(RuleResult)

    def test_has_required_fields(self):
        fields = {f.name for f in dataclasses.fields(RuleResult)}
        assert fields == {"fired", "rule_id", "severity", "points", "details"}

    def test_defaults(self):
        rr = RuleResult(fired=False, rule_id="test")
        assert rr.severity is None
        assert rr.points == 0.0
        assert rr.details == {}

    def test_construction(self):
        rr = RuleResult(
            fired=True,
            rule_id="ais_gap",
            severity="high",
            points=15.0,
            details={"gap_hours": 6},
        )
        assert rr.fired is True
        assert rr.rule_id == "ais_gap"
        assert rr.points == 15.0


# ===================================================================
# GfwEvent tests
# ===================================================================


class TestGfwEvent:
    """GfwEvent validation tests."""

    def _valid_kwargs(self) -> dict:
        return {
            "gfw_event_id": "evt-abc-123",
            "event_type": "ENCOUNTER",
            "mmsi": 123456789,
            "start_time": datetime(2025, 6, 1, tzinfo=timezone.utc),
        }

    def test_valid_event(self):
        event = GfwEvent(**self._valid_kwargs())
        assert event.event_type == "ENCOUNTER"

    def test_validates_event_type_enum(self):
        kw = self._valid_kwargs()
        kw["event_type"] = "FISHING"
        with pytest.raises(ValidationError, match="event_type"):
            GfwEvent(**kw)

    def test_all_valid_event_types(self):
        for et in ("AIS_DISABLING", "ENCOUNTER", "LOITERING", "PORT_VISIT"):
            kw = self._valid_kwargs()
            kw["event_type"] = et
            event = GfwEvent(**kw)
            assert event.event_type == et

    def test_requires_gfw_event_id(self):
        kw = self._valid_kwargs()
        del kw["gfw_event_id"]
        with pytest.raises(ValidationError, match="gfw_event_id"):
            GfwEvent(**kw)

    def test_requires_event_type(self):
        kw = self._valid_kwargs()
        del kw["event_type"]
        with pytest.raises(ValidationError, match="event_type"):
            GfwEvent(**kw)

    def test_rejects_empty_gfw_event_id(self):
        kw = self._valid_kwargs()
        kw["gfw_event_id"] = ""
        with pytest.raises(ValidationError, match="gfw_event_id"):
            GfwEvent(**kw)


# ===================================================================
# ManualEnrichment tests
# ===================================================================


class TestManualEnrichment:
    """ManualEnrichment validation tests."""

    def test_valid_enrichment(self):
        me = ManualEnrichment(mmsi=123456789)
        assert me.pi_tier is None
        assert me.attachments == []

    def test_valid_pi_tiers(self):
        for tier in (
            "ig_member",
            "non_ig_western",
            "russian_state",
            "unknown",
            "fraudulent",
            "none",
        ):
            me = ManualEnrichment(mmsi=123456789, pi_tier=tier)
            assert me.pi_tier == tier

    def test_invalid_pi_tier(self):
        with pytest.raises(ValidationError, match="pi_tier"):
            ManualEnrichment(mmsi=123456789, pi_tier="invalid")


# ===================================================================
# SarDetection tests
# ===================================================================


class TestSarDetection:
    """SarDetection validation tests."""

    def test_valid_detection(self):
        sd = SarDetection(
            detection_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            lat=10.0,
            lon=20.0,
        )
        assert sd.source == "gfw"
        assert sd.is_dark is False

    def test_rejects_invalid_lat(self):
        with pytest.raises(ValidationError, match="lat"):
            SarDetection(
                detection_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                lat=91.0,
                lon=20.0,
            )
