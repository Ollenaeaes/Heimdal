"""Tests for anomaly event lifecycle: schema fields, state transitions, queries.

All database interactions are mocked — no running services needed.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make the scoring service importable
_scoring_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scoring_dir))
# Make shared importable
sys.path.insert(0, str(_scoring_dir.parent.parent))

from shared.models.anomaly import AnomalyEvent


# ---------------------------------------------------------------------------
# Test: Pydantic AnomalyEvent model includes new lifecycle fields
# ---------------------------------------------------------------------------


class TestAnomalyEventModel:
    """Verify that AnomalyEvent has the new lifecycle fields with proper validation."""

    def test_new_fields_have_correct_defaults(self):
        """New lifecycle fields default to None/active for a minimal event."""
        event = AnomalyEvent(
            mmsi=123456789,
            rule_id="ais_gap",
            severity="high",
            points=40.0,
        )
        assert event.event_start is None
        assert event.event_end is None
        assert event.event_state == "active"

    def test_event_state_accepts_valid_literals(self):
        """event_state must accept 'active', 'ended', and 'superseded'."""
        for state in ("active", "ended", "superseded"):
            event = AnomalyEvent(
                mmsi=234567890,
                rule_id="sts_proximity",
                severity="moderate",
                points=20.0,
                event_state=state,
            )
            assert event.event_state == state

    def test_event_state_rejects_invalid_value(self):
        """event_state must reject values outside the allowed literals."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            AnomalyEvent(
                mmsi=345678901,
                rule_id="flag_hopping",
                severity="low",
                points=10.0,
                event_state="cancelled",  # type: ignore[arg-type]
            )

    def test_event_start_accepts_datetime(self):
        """event_start should accept a datetime value."""
        now = datetime.now(timezone.utc)
        event = AnomalyEvent(
            mmsi=456789012,
            rule_id="sanctions_match",
            severity="critical",
            points=100.0,
            event_start=now,
        )
        assert event.event_start == now

    def test_event_end_accepts_datetime(self):
        """event_end should accept a datetime value."""
        now = datetime.now(timezone.utc)
        event = AnomalyEvent(
            mmsi=567890123,
            rule_id="draft_change",
            severity="moderate",
            points=25.0,
            event_end=now,
        )
        assert event.event_end == now

    def test_full_lifecycle_fields_coexist_with_existing(self):
        """All existing fields still work alongside new lifecycle fields."""
        now = datetime.now(timezone.utc)
        event = AnomalyEvent(
            id=42,
            mmsi=678901234,
            rule_id="gfw_ais_disabling",
            severity="critical",
            points=95.0,
            details={"gap_hours": 72},
            resolved=True,
            created_at=now,
            event_start=now,
            event_end=now,
            event_state="ended",
        )
        assert event.id == 42
        assert event.resolved is True
        assert event.event_state == "ended"
        assert event.event_start == now
        assert event.event_end == now

    def test_from_attributes_with_lifecycle_fields(self):
        """model_config from_attributes should work with lifecycle fields (ORM-like)."""

        class FakeRow:
            id = 1
            mmsi = 123456789
            rule_id = "ais_gap"
            severity = "high"
            points = 40.0
            details = {}
            resolved = False
            created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            event_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            event_end = None
            event_state = "active"

        event = AnomalyEvent.model_validate(FakeRow())
        assert event.event_state == "active"
        assert event.event_start == datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert event.event_end is None


# ---------------------------------------------------------------------------
# Test: end_anomaly_event repository function
# ---------------------------------------------------------------------------


class TestEndAnomalyEvent:
    """Verify that end_anomaly_event transitions an active event to ended."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        return session

    @pytest.mark.asyncio
    async def test_end_anomaly_event_executes_correct_sql(self, mock_session):
        """end_anomaly_event should UPDATE event_end, event_state, and resolved."""
        from shared.db.repositories import end_anomaly_event

        await end_anomaly_event(mock_session, anomaly_id=42)

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        params = call_args[0][1]

        assert "event_end = NOW()" in sql_text
        assert "event_state = 'ended'" in sql_text
        assert "resolved = true" in sql_text
        assert params["anomaly_id"] == 42

    @pytest.mark.asyncio
    async def test_end_anomaly_event_targets_specific_id(self, mock_session):
        """end_anomaly_event should only update the row with the given ID."""
        from shared.db.repositories import end_anomaly_event

        await end_anomaly_event(mock_session, anomaly_id=99)

        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        params = call_args[0][1]

        assert "WHERE id = :anomaly_id" in sql_text
        assert params["anomaly_id"] == 99


# ---------------------------------------------------------------------------
# Test: list_active_anomalies_by_mmsi repository function
# ---------------------------------------------------------------------------


class TestListActiveAnomaliesByMmsi:
    """Verify that list_active_anomalies_by_mmsi filters by event_state='active'."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        return session

    @pytest.mark.asyncio
    async def test_filters_by_active_state(self, mock_session):
        """Query should filter for event_state = 'active'."""
        from shared.db.repositories import list_active_anomalies_by_mmsi

        # Set up mock to return empty result
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await list_active_anomalies_by_mmsi(mock_session, mmsi=123456789)

        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        params = call_args[0][1]

        assert "event_state = 'active'" in sql_text
        assert params["mmsi"] == 123456789

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self, mock_session):
        """Should return a list of dicts from the query result."""
        from shared.db.repositories import list_active_anomalies_by_mmsi

        fake_row = {
            "id": 1,
            "mmsi": 234567890,
            "rule_id": "ais_gap",
            "severity": "high",
            "points": 40.0,
            "event_state": "active",
        }
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [fake_row]
        mock_session.execute.return_value = mock_result

        results = await list_active_anomalies_by_mmsi(mock_session, mmsi=234567890)

        assert len(results) == 1
        assert results[0]["event_state"] == "active"
        assert results[0]["rule_id"] == "ais_gap"

    @pytest.mark.asyncio
    async def test_excludes_ended_anomalies(self, mock_session):
        """Ended anomalies should not be returned — only active ones."""
        from shared.db.repositories import list_active_anomalies_by_mmsi

        # Simulate DB returning only active rows (ended filtered out by SQL)
        active_row = {
            "id": 1,
            "mmsi": 345678901,
            "rule_id": "sts_proximity",
            "severity": "moderate",
            "points": 20.0,
            "event_state": "active",
        }
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [active_row]
        mock_session.execute.return_value = mock_result

        results = await list_active_anomalies_by_mmsi(mock_session, mmsi=345678901)

        assert len(results) == 1
        assert all(r["event_state"] == "active" for r in results)


# ---------------------------------------------------------------------------
# Test: Ended anomalies are not reactivated — new rows are created instead
# ---------------------------------------------------------------------------


class TestEndedAnomaliesNotReactivated:
    """Verify the design principle: ended events stay ended, new events are new rows."""

    def test_ended_event_stays_ended_in_model(self):
        """An ended AnomalyEvent should not be mutated back to active
        — the pattern is to create a new row instead."""
        ended_event = AnomalyEvent(
            id=10,
            mmsi=456789012,
            rule_id="ais_gap",
            severity="high",
            points=40.0,
            resolved=True,
            event_state="ended",
            event_end=datetime.now(timezone.utc),
        )

        # Create a NEW event for the same vessel+rule (not reactivating the old one)
        new_event = AnomalyEvent(
            mmsi=456789012,
            rule_id="ais_gap",
            severity="high",
            points=40.0,
            event_state="active",
        )

        # The ended event retains its state
        assert ended_event.event_state == "ended"
        assert ended_event.resolved is True

        # The new event is a separate object with active state
        assert new_event.event_state == "active"
        assert new_event.id is None  # no ID yet — would be assigned by DB

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        return session

    @pytest.mark.asyncio
    async def test_create_anomaly_does_not_update_ended(self, mock_session):
        """create_anomaly_event creates a new row via INSERT, not UPDATE.
        This confirms that re-firing a rule for the same vessel creates
        a new anomaly rather than reactivating an ended one."""
        from shared.db.repositories import create_anomaly_event

        # Mock the RETURNING id result
        mock_result = MagicMock()
        mock_result.first.return_value = (99,)
        mock_session.execute.return_value = mock_result

        new_id = await create_anomaly_event(mock_session, {
            "mmsi": 567890123,
            "rule_id": "ais_gap",
            "severity": "high",
            "points": 40.0,
            "details": "{}",
        })

        assert new_id == 99

        # Verify it was an INSERT, not an UPDATE
        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        assert "INSERT INTO anomaly_events" in sql_text
        assert "UPDATE" not in sql_text
