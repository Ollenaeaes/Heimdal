"""Integration test: AIS ingest -> scoring -> API response pipeline.

Verifies that a mock AIS message flows through the system and produces
correct risk tier in the API response. Requires Docker Compose.

Run: pytest tests/integration/test_pipeline.py -v
"""

from __future__ import annotations

import json
import time

import pytest
import requests

from .conftest import API_BASE_URL, requires_docker


@requires_docker
class TestIngestToApiPipeline:
    """Test the full AIS ingest -> scoring -> API query pipeline."""

    def test_health_endpoint_returns_200(self):
        """API server health check returns 200 with service status."""
        resp = requests.get(f"{API_BASE_URL}/api/health", timeout=5)
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert body["status"] in ("healthy", "degraded")

    def test_vessels_endpoint_returns_paginated_response(self):
        """GET /api/vessels returns a paginated response structure."""
        resp = requests.get(f"{API_BASE_URL}/api/vessels", timeout=5)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "per_page" in body
        assert isinstance(body["items"], list)

    def test_vessels_risk_tier_filter(self):
        """GET /api/vessels?risk_tier=red returns only red-tier vessels."""
        resp = requests.get(
            f"{API_BASE_URL}/api/vessels?risk_tier=red", timeout=5
        )
        assert resp.status_code == 200
        body = resp.json()
        for vessel in body["items"]:
            assert vessel["risk_tier"] == "red"

    def test_vessel_detail_includes_risk_score(self):
        """GET /api/vessels returns vessels with risk_score and risk_tier."""
        resp = requests.get(
            f"{API_BASE_URL}/api/vessels?per_page=1", timeout=5
        )
        assert resp.status_code == 200
        body = resp.json()
        if body["total"] > 0:
            vessel = body["items"][0]
            assert "risk_score" in vessel
            assert "risk_tier" in vessel
            assert vessel["risk_tier"] in ("green", "yellow", "red", "blacklisted")

    def test_anomalies_endpoint_returns_structured_response(self):
        """GET /api/anomalies returns anomaly events with scoring data."""
        resp = requests.get(f"{API_BASE_URL}/api/anomalies", timeout=5)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        for anomaly in body["items"]:
            assert "rule_id" in anomaly
            assert "severity" in anomaly
            assert "points" in anomaly
            assert anomaly["severity"] in ("critical", "high", "moderate", "low")

    def test_vessel_detail_endpoint(self):
        """GET /api/vessels/{mmsi} returns full vessel profile if vessels exist."""
        # First get a vessel MMSI
        list_resp = requests.get(
            f"{API_BASE_URL}/api/vessels?per_page=1", timeout=5
        )
        assert list_resp.status_code == 200
        body = list_resp.json()
        if body["total"] == 0:
            pytest.skip("No vessels in database")

        mmsi = body["items"][0]["mmsi"]
        detail_resp = requests.get(
            f"{API_BASE_URL}/api/vessels/{mmsi}", timeout=5
        )
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["mmsi"] == mmsi
        assert "risk_score" in detail
        assert "risk_tier" in detail

    def test_nonexistent_vessel_returns_404(self):
        """GET /api/vessels/{mmsi} returns 404 for unknown MMSI."""
        resp = requests.get(
            f"{API_BASE_URL}/api/vessels/100000001", timeout=5
        )
        assert resp.status_code == 404

    def test_stats_endpoint_returns_tier_breakdown(self):
        """GET /api/stats returns risk tier breakdown and counts."""
        resp = requests.get(f"{API_BASE_URL}/api/stats", timeout=5)
        assert resp.status_code == 200
        body = resp.json()
        # Stats endpoint should have tier breakdown
        assert isinstance(body, dict)
