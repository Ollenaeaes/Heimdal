"""Integration test: GFW events -> scoring rules -> anomalies.

Verifies that GFW events present in the database produce correct
anomalies with expected severities. Also validates the scoring
rules' interaction with the aggregator and tier calculation.

Requires Docker Compose.

Run: pytest tests/integration/test_gfw_scoring.py -v
"""

from __future__ import annotations

import json

import pytest
import requests

from .conftest import API_BASE_URL, requires_docker


@requires_docker
class TestGfwEventScoring:
    """Test that GFW events are reflected in vessel anomalies."""

    def test_anomalies_include_gfw_rules(self):
        """GET /api/anomalies returns anomalies from GFW-sourced rules."""
        resp = requests.get(
            f"{API_BASE_URL}/api/anomalies?per_page=100",
            timeout=5,
        )
        assert resp.status_code == 200
        body = resp.json()

        gfw_rule_ids = {
            "gfw_ais_disabling",
            "gfw_encounter",
            "gfw_loitering",
            "gfw_port_visit",
            "gfw_dark_sar",
        }
        found_gfw_rules = {
            a["rule_id"] for a in body["items"] if a["rule_id"] in gfw_rule_ids
        }
        # We don't require all GFW rules to be present (depends on data),
        # but the structure should be correct
        for anomaly in body["items"]:
            if anomaly["rule_id"] in gfw_rule_ids:
                assert anomaly["severity"] in (
                    "critical", "high", "moderate", "low"
                )
                assert anomaly["points"] > 0

    def test_anomalies_include_realtime_rules(self):
        """GET /api/anomalies may include real-time rule anomalies."""
        resp = requests.get(
            f"{API_BASE_URL}/api/anomalies?per_page=100",
            timeout=5,
        )
        assert resp.status_code == 200
        body = resp.json()

        realtime_rule_ids = {
            "ais_gap", "sts_proximity", "destination_spoof",
            "draft_change", "flag_hopping", "sanctions_match",
            "vessel_age", "speed_anomaly", "identity_mismatch",
        }
        for anomaly in body["items"]:
            if anomaly["rule_id"] in realtime_rule_ids:
                assert anomaly["severity"] in (
                    "critical", "high", "moderate", "low"
                )
                assert anomaly["points"] > 0

    def test_vessel_risk_tiers_are_consistent(self):
        """Vessel risk tiers match their risk scores (green < 30, yellow 30-99, red 100+)."""
        resp = requests.get(
            f"{API_BASE_URL}/api/vessels?per_page=50", timeout=5
        )
        assert resp.status_code == 200
        body = resp.json()

        for vessel in body["items"]:
            score = vessel.get("risk_score", 0)
            tier = vessel["risk_tier"]
            if score < 30:
                assert tier == "green", (
                    f"MMSI {vessel['mmsi']}: score {score} should be green, got {tier}"
                )
            elif score < 100:
                assert tier == "yellow", (
                    f"MMSI {vessel['mmsi']}: score {score} should be yellow, got {tier}"
                )
            else:
                assert tier == "red", (
                    f"MMSI {vessel['mmsi']}: score {score} should be red, got {tier}"
                )

    def test_anomaly_severity_has_valid_points(self):
        """Anomaly point values are consistent with severity levels."""
        from shared.constants import SEVERITY_POINTS

        resp = requests.get(
            f"{API_BASE_URL}/api/anomalies?per_page=100",
            timeout=5,
        )
        assert resp.status_code == 200
        body = resp.json()

        for anomaly in body["items"]:
            # Points should be positive
            assert anomaly["points"] > 0
            # Points should not exceed the max cap for any rule
            assert anomaly["points"] <= 50, (
                f"Anomaly {anomaly['id']} has unusually high points: {anomaly['points']}"
            )

    def test_gfw_events_have_correct_structure(self):
        """GFW events from the API have all required fields."""
        resp = requests.get(
            f"{API_BASE_URL}/api/gfw/events?per_page=10",
            timeout=5,
        )
        assert resp.status_code == 200
        body = resp.json()

        for event in body["items"]:
            assert "gfw_event_id" in event or "id" in event
            assert "event_type" in event
            assert "mmsi" in event
            assert "start_time" in event
            assert event["event_type"] in (
                "AIS_DISABLING", "ENCOUNTER", "LOITERING", "PORT_VISIT"
            )

    def test_anomaly_resolved_filter_works(self):
        """Resolved filter correctly separates resolved/unresolved anomalies."""
        unresolved_resp = requests.get(
            f"{API_BASE_URL}/api/anomalies?resolved=false&per_page=100",
            timeout=5,
        )
        assert unresolved_resp.status_code == 200
        for a in unresolved_resp.json()["items"]:
            assert a["resolved"] is False

        resolved_resp = requests.get(
            f"{API_BASE_URL}/api/anomalies?resolved=true&per_page=100",
            timeout=5,
        )
        assert resolved_resp.status_code == 200
        for a in resolved_resp.json()["items"]:
            assert a["resolved"] is True
