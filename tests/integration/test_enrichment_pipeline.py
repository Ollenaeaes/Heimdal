"""Integration test: Enrichment pipeline with sanctions matching.

Verifies the enrichment-related API endpoints work correctly:
- Manual enrichment submission
- Watchlist CRUD
- GFW events query
- SAR detections query

Requires Docker Compose.

Run: pytest tests/integration/test_enrichment_pipeline.py -v
"""

from __future__ import annotations

import json

import pytest
import requests

from .conftest import API_BASE_URL, requires_docker


@requires_docker
class TestEnrichmentEndpoints:
    """Test enrichment-related API endpoints in integration."""

    def test_gfw_events_endpoint(self):
        """GET /api/gfw/events returns GFW event data."""
        resp = requests.get(f"{API_BASE_URL}/api/gfw/events", timeout=5)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        for event in body["items"]:
            assert "event_type" in event
            assert event["event_type"] in (
                "AIS_DISABLING", "ENCOUNTER", "LOITERING", "PORT_VISIT"
            )

    def test_gfw_events_type_filter(self):
        """GET /api/gfw/events?event_type=ENCOUNTER filters by type."""
        resp = requests.get(
            f"{API_BASE_URL}/api/gfw/events?event_type=ENCOUNTER",
            timeout=5,
        )
        assert resp.status_code == 200
        body = resp.json()
        for event in body["items"]:
            assert event["event_type"] == "ENCOUNTER"

    def test_sar_detections_endpoint(self):
        """GET /api/sar/detections returns SAR detection data."""
        resp = requests.get(
            f"{API_BASE_URL}/api/sar/detections", timeout=5
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body

    def test_sar_dark_filter(self):
        """GET /api/sar/detections?is_dark=true filters dark ships."""
        resp = requests.get(
            f"{API_BASE_URL}/api/sar/detections?is_dark=true", timeout=5
        )
        assert resp.status_code == 200
        body = resp.json()
        for det in body["items"]:
            assert det["is_dark"] is True


@requires_docker
class TestWatchlistEndpoints:
    """Test watchlist CRUD operations in integration."""

    def test_get_watchlist(self):
        """GET /api/watchlist returns the current watchlist."""
        resp = requests.get(f"{API_BASE_URL}/api/watchlist", timeout=5)
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list) or "items" in body

    def test_watchlist_add_and_remove_cycle(self):
        """POST then DELETE a watchlist entry works end-to-end."""
        test_mmsi = 259000420

        # Add to watchlist
        add_resp = requests.post(
            f"{API_BASE_URL}/api/watchlist",
            json={"mmsi": test_mmsi},
            timeout=5,
        )
        # Accept 201 (created) or 200 (already exists) or 409 (conflict)
        assert add_resp.status_code in (200, 201, 409)

        # Remove from watchlist
        del_resp = requests.delete(
            f"{API_BASE_URL}/api/watchlist/{test_mmsi}",
            timeout=5,
        )
        assert del_resp.status_code in (200, 204, 404)


@requires_docker
class TestManualEnrichment:
    """Test manual enrichment submission in integration."""

    def test_enrichment_requires_existing_vessel(self):
        """POST /api/vessels/{mmsi}/enrich returns 404 for unknown vessel."""
        resp = requests.post(
            f"{API_BASE_URL}/api/vessels/100000001/enrich",
            json={"source": "Integration test"},
            timeout=5,
        )
        assert resp.status_code == 404

    def test_enrichment_rejects_missing_source(self):
        """POST /api/vessels/{mmsi}/enrich returns 422 without source field."""
        resp = requests.post(
            f"{API_BASE_URL}/api/vessels/259000420/enrich",
            json={"notes": "Missing source"},
            timeout=5,
        )
        assert resp.status_code in (404, 422)

    def test_enrichment_for_existing_vessel(self):
        """POST enrichment for a vessel that exists in the database."""
        # First check if we have any vessels
        vessels = requests.get(
            f"{API_BASE_URL}/api/vessels?per_page=1", timeout=5
        )
        if vessels.json()["total"] == 0:
            pytest.skip("No vessels in database")

        mmsi = vessels.json()["items"][0]["mmsi"]
        resp = requests.post(
            f"{API_BASE_URL}/api/vessels/{mmsi}/enrich",
            json={
                "source": "Integration test",
                "notes": "Automated integration test enrichment",
            },
            timeout=5,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["mmsi"] == mmsi
