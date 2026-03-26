"""Tests for Geographic Inference Engine — D1-D7 signals (Story 5).

Tests mock PostgreSQL to focus on inference logic rather than database
connectivity.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call

from services.geographic_inference.engine import (
    GeographicInference,
    SIGNAL_WEIGHTS,
    GULF_OF_FINLAND_APPROACHES_WKT,
    KOLA_BAY_APPROACHES_WKT,
    BALTIC_TRANSIT_WKT,
    NON_RUSSIAN_BALTIC_TERMINALS,
    STAGING_LOITER_HOURS,
    AIS_GAP_HOURS,
    _bearing_to_point,
    _bearing_difference,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)


def _make_position(mmsi: int, hours_ago: float, lat: float, lon: float,
                   sog: float = 0.3, cog: float = 180.0,
                   nav_status: int = 1) -> dict:
    """Create a position dict as returned by _get_recent_positions."""
    return {
        "mmsi": mmsi,
        "timestamp": NOW - timedelta(hours=hours_ago),
        "lat": lat,
        "lon": lon,
        "sog": sog,
        "cog": cog,
        "nav_status": nav_status,
    }


def _make_profile(mmsi: int, ship_type: int = 80,
                  flag_country: str = "PA", imo: int = 9876543,
                  risk_tier: str = "green") -> dict:
    """Create a vessel profile dict."""
    return {
        "mmsi": mmsi,
        "imo": imo,
        "ship_type": ship_type,
        "flag_country": flag_country,
        "risk_tier": risk_tier,
    }


class MockCursor:
    """A mock cursor that supports context manager and configurable fetchone/fetchall."""

    def __init__(self):
        self.queries = []
        self._fetchone_results = []
        self._fetchall_results = []

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchone(self):
        if self._fetchone_results:
            return self._fetchone_results.pop(0)
        return None

    def fetchall(self):
        if self._fetchall_results:
            return self._fetchall_results.pop(0)
        return []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockConnection:
    """A mock psycopg2 connection."""

    def __init__(self):
        self._cursors = []
        self.committed = False

    def add_cursor(self, cursor: MockCursor):
        self._cursors.append(cursor)

    def cursor(self, cursor_factory=None):
        if self._cursors:
            return self._cursors.pop(0)
        return MockCursor()

    def commit(self):
        self.committed = True

    def close(self):
        pass


# ---------------------------------------------------------------------------
# D1: Gulf of Finland staging area loiter
# ---------------------------------------------------------------------------


class TestD1StagingLoiterGulfOfFinland:
    """D1: vessel anchored in Gulf of Finland approaches for >12h."""

    def test_d1_fires_for_14h_loiter(self):
        """D1 fires for vessel anchored in Gulf of Finland approaches for 14 hours."""
        mmsi = 273123456

        # Gulf of Finland approaches center: ~26.0, 59.7
        positions = [
            _make_position(mmsi, 14, 59.7, 26.0, sog=0.2, nav_status=1),
            _make_position(mmsi, 10, 59.7, 26.1, sog=0.3, nav_status=1),
            _make_position(mmsi, 6, 59.7, 26.0, sog=0.1, nav_status=1),
            _make_position(mmsi, 0, 59.7, 26.0, sog=0.4, nav_status=1),
        ]

        conn = MockConnection()

        # Cursor for _get_vessel_profile
        profile_cursor = MockCursor()
        profile_cursor._fetchone_results = [_make_profile(mmsi)]
        conn.add_cursor(profile_cursor)

        # Cursor for _get_recent_positions
        positions_cursor = MockCursor()
        positions_cursor._fetchall_results = [positions]
        conn.add_cursor(positions_cursor)

        # Cursor for _positions_in_zone (D1 — Gulf of Finland)
        zone_cursor = MockCursor()
        zone_cursor._fetchall_results = [positions]  # All in zone
        conn.add_cursor(zone_cursor)

        # Cursor for _positions_in_zone (D2 — Kola Bay) — empty
        zone_cursor2 = MockCursor()
        zone_cursor2._fetchall_results = [[]]
        conn.add_cursor(zone_cursor2)

        # D3/D4: _positions_in_zone for Baltic transit
        baltic_cursor = MockCursor()
        baltic_cursor._fetchall_results = [[]]
        conn.add_cursor(baltic_cursor)

        # D4: _positions_in_zone for Barents transit
        barents_cursor = MockCursor()
        barents_cursor._fetchall_results = [[]]
        conn.add_cursor(barents_cursor)

        # D5: profile already loaded (uses data from profile)
        # D6: anomaly_events cursor
        sts_cursor = MockCursor()
        sts_cursor._fetchall_results = [[]]
        conn.add_cursor(sts_cursor)

        # D7: _positions_in_zone for Gulf of Finland (loiter-then-vanish)
        d7_gof_cursor = MockCursor()
        d7_gof_cursor._fetchall_results = [positions]
        conn.add_cursor(d7_gof_cursor)

        # D7: _positions_in_zone for Kola Bay
        d7_kola_cursor = MockCursor()
        d7_kola_cursor._fetchall_results = [[]]
        conn.add_cursor(d7_kola_cursor)

        engine = GeographicInference(conn)
        signals = engine.evaluate_vessel(mmsi)

        d1_signals = [s for s in signals if s["signal_id"] == "D1"]
        assert len(d1_signals) == 1
        assert d1_signals[0]["weight"] == 3
        assert d1_signals[0]["details"]["duration_hours"] >= 14

    def test_d1_does_not_fire_for_6h_loiter(self):
        """D1 does NOT fire for vessel anchored for 6 hours (under threshold)."""
        mmsi = 273123456

        positions = [
            _make_position(mmsi, 6, 59.7, 26.0, sog=0.2, nav_status=1),
            _make_position(mmsi, 3, 59.7, 26.1, sog=0.3, nav_status=1),
            _make_position(mmsi, 0, 59.7, 26.0, sog=0.1, nav_status=1),
        ]

        conn = MockConnection()

        # Profile
        profile_cursor = MockCursor()
        profile_cursor._fetchone_results = [_make_profile(mmsi)]
        conn.add_cursor(profile_cursor)

        # Positions
        positions_cursor = MockCursor()
        positions_cursor._fetchall_results = [positions]
        conn.add_cursor(positions_cursor)

        # D1 zone positions
        zone_cursor = MockCursor()
        zone_cursor._fetchall_results = [positions]
        conn.add_cursor(zone_cursor)

        # D2 zone — empty
        zone_cursor2 = MockCursor()
        zone_cursor2._fetchall_results = [[]]
        conn.add_cursor(zone_cursor2)

        # D3 Baltic
        baltic_cursor = MockCursor()
        baltic_cursor._fetchall_results = [[]]
        conn.add_cursor(baltic_cursor)

        # D4 Barents
        barents_cursor = MockCursor()
        barents_cursor._fetchall_results = [[]]
        conn.add_cursor(barents_cursor)

        # D6 STS
        sts_cursor = MockCursor()
        sts_cursor._fetchall_results = [[]]
        conn.add_cursor(sts_cursor)

        # D7 GoF
        d7_gof = MockCursor()
        d7_gof._fetchall_results = [positions]
        conn.add_cursor(d7_gof)

        # D7 Kola
        d7_kola = MockCursor()
        d7_kola._fetchall_results = [[]]
        conn.add_cursor(d7_kola)

        engine = GeographicInference(conn)
        signals = engine.evaluate_vessel(mmsi)

        d1_signals = [s for s in signals if s["signal_id"] == "D1"]
        assert len(d1_signals) == 0


# ---------------------------------------------------------------------------
# D3: Baltic Russian-origin transit
# ---------------------------------------------------------------------------


class TestD3BalticRussianOriginTransit:
    """D3: tanker transiting Baltic with no non-Russian terminal footprint."""

    def test_d3_fires_no_non_russian_port_call(self):
        """D3 fires for a vessel transiting Baltic with no non-Russian port call."""
        mmsi = 273456789

        # Southbound positions in Baltic
        baltic_positions = [
            _make_position(mmsi, 48, 58.0, 20.0, sog=12.0, cog=200.0, nav_status=0),
            _make_position(mmsi, 36, 57.0, 19.5, sog=11.5, cog=195.0, nav_status=0),
            _make_position(mmsi, 24, 56.0, 18.5, sog=12.0, cog=200.0, nav_status=0),
            _make_position(mmsi, 12, 55.0, 17.5, sog=11.0, cog=210.0, nav_status=0),
        ]

        conn = MockConnection()

        # Profile — tanker
        profile_cursor = MockCursor()
        profile_cursor._fetchone_results = [_make_profile(mmsi, ship_type=80)]
        conn.add_cursor(profile_cursor)

        # All positions
        positions_cursor = MockCursor()
        positions_cursor._fetchall_results = [baltic_positions]
        conn.add_cursor(positions_cursor)

        # D1 GoF — empty
        d1_cursor = MockCursor()
        d1_cursor._fetchall_results = [[]]
        conn.add_cursor(d1_cursor)

        # D2 Kola — empty
        d2_cursor = MockCursor()
        d2_cursor._fetchall_results = [[]]
        conn.add_cursor(d2_cursor)

        # D3 Baltic positions
        d3_cursor = MockCursor()
        d3_cursor._fetchall_results = [baltic_positions]
        conn.add_cursor(d3_cursor)

        # D3 port call footprint checks (5 terminals, all return False)
        for _ in NON_RUSSIAN_BALTIC_TERMINALS:
            port_cursor = MockCursor()
            port_cursor._fetchone_results = [(False,)]
            conn.add_cursor(port_cursor)

        # D4 Barents — empty
        d4_cursor = MockCursor()
        d4_cursor._fetchall_results = [[]]
        conn.add_cursor(d4_cursor)

        # D6 STS
        sts_cursor = MockCursor()
        sts_cursor._fetchall_results = [[]]
        conn.add_cursor(sts_cursor)

        # D7 GoF
        d7_gof = MockCursor()
        d7_gof._fetchall_results = [[]]
        conn.add_cursor(d7_gof)

        # D7 Kola
        d7_kola = MockCursor()
        d7_kola._fetchall_results = [[]]
        conn.add_cursor(d7_kola)

        engine = GeographicInference(conn)
        signals = engine.evaluate_vessel(mmsi)

        d3_signals = [s for s in signals if s["signal_id"] == "D3"]
        assert len(d3_signals) == 1
        assert d3_signals[0]["weight"] == 4

    def test_d3_does_not_fire_with_gdansk_footprint(self):
        """D3 does NOT fire for a vessel with port call footprint at Gdańsk."""
        mmsi = 273456789

        baltic_positions = [
            _make_position(mmsi, 48, 58.0, 20.0, sog=12.0, cog=200.0, nav_status=0),
            _make_position(mmsi, 36, 57.0, 19.5, sog=11.5, cog=195.0, nav_status=0),
        ]

        conn = MockConnection()

        # Profile — tanker
        profile_cursor = MockCursor()
        profile_cursor._fetchone_results = [_make_profile(mmsi, ship_type=80)]
        conn.add_cursor(profile_cursor)

        # All positions
        positions_cursor = MockCursor()
        positions_cursor._fetchall_results = [baltic_positions]
        conn.add_cursor(positions_cursor)

        # D1 GoF — empty
        d1_cursor = MockCursor()
        d1_cursor._fetchall_results = [[]]
        conn.add_cursor(d1_cursor)

        # D2 Kola — empty
        d2_cursor = MockCursor()
        d2_cursor._fetchall_results = [[]]
        conn.add_cursor(d2_cursor)

        # D3 Baltic positions
        d3_cursor = MockCursor()
        d3_cursor._fetchall_results = [baltic_positions]
        conn.add_cursor(d3_cursor)

        # First terminal check (Gdańsk) returns True — has footprint
        gdansk_cursor = MockCursor()
        gdansk_cursor._fetchone_results = [(True,)]
        conn.add_cursor(gdansk_cursor)

        # Remaining terminals won't be checked (short-circuit)

        # D4 Barents — empty
        d4_cursor = MockCursor()
        d4_cursor._fetchall_results = [[]]
        conn.add_cursor(d4_cursor)

        # D6 STS
        sts_cursor = MockCursor()
        sts_cursor._fetchall_results = [[]]
        conn.add_cursor(sts_cursor)

        # D7 GoF
        d7_gof = MockCursor()
        d7_gof._fetchall_results = [[]]
        conn.add_cursor(d7_gof)

        # D7 Kola
        d7_kola = MockCursor()
        d7_kola._fetchall_results = [[]]
        conn.add_cursor(d7_kola)

        engine = GeographicInference(conn)
        signals = engine.evaluate_vessel(mmsi)

        d3_signals = [s for s in signals if s["signal_id"] == "D3"]
        assert len(d3_signals) == 0


# ---------------------------------------------------------------------------
# D5: MMSI/flag mismatch
# ---------------------------------------------------------------------------


class TestD5MmsiFlagMismatch:
    """D5: MMSI MID maps to different flag than recorded."""

    def test_d5_fires_mid_273_flag_gabon(self):
        """D5 fires when MMSI MID=273 (Russia) but flag is recorded as Gabon."""
        mmsi = 273111222

        conn = MockConnection()

        # Profile with Gabon flag
        profile_cursor = MockCursor()
        profile_cursor._fetchone_results = [
            _make_profile(mmsi, flag_country="GA")
        ]
        conn.add_cursor(profile_cursor)

        # Positions — minimal
        positions_cursor = MockCursor()
        positions_cursor._fetchall_results = [[]]
        conn.add_cursor(positions_cursor)

        # D1 GoF
        d1_cursor = MockCursor()
        d1_cursor._fetchall_results = [[]]
        conn.add_cursor(d1_cursor)

        # D2 Kola
        d2_cursor = MockCursor()
        d2_cursor._fetchall_results = [[]]
        conn.add_cursor(d2_cursor)

        # D3 Baltic (tanker)
        d3_cursor = MockCursor()
        d3_cursor._fetchall_results = [[]]
        conn.add_cursor(d3_cursor)

        # D4 Barents
        d4_cursor = MockCursor()
        d4_cursor._fetchall_results = [[]]
        conn.add_cursor(d4_cursor)

        # D6 STS
        sts_cursor = MockCursor()
        sts_cursor._fetchall_results = [[]]
        conn.add_cursor(sts_cursor)

        # D7 GoF
        d7_gof = MockCursor()
        d7_gof._fetchall_results = [[]]
        conn.add_cursor(d7_gof)

        # D7 Kola
        d7_kola = MockCursor()
        d7_kola._fetchall_results = [[]]
        conn.add_cursor(d7_kola)

        engine = GeographicInference(conn)
        signals = engine.evaluate_vessel(mmsi)

        d5_signals = [s for s in signals if s["signal_id"] == "D5"]
        assert len(d5_signals) == 1
        assert d5_signals[0]["weight"] == 2
        assert d5_signals[0]["details"]["mid_flag"] == "RU"
        assert d5_signals[0]["details"]["recorded_flag"] == "GA"

    def test_d5_does_not_fire_matching_flag(self):
        """D5 does NOT fire when MMSI MID matches recorded flag."""
        mmsi = 273111222  # MID 273 = Russia

        conn = MockConnection()

        # Profile with Russia flag — matches MID
        profile_cursor = MockCursor()
        profile_cursor._fetchone_results = [
            _make_profile(mmsi, flag_country="RU")
        ]
        conn.add_cursor(profile_cursor)

        # Positions
        positions_cursor = MockCursor()
        positions_cursor._fetchall_results = [[]]
        conn.add_cursor(positions_cursor)

        # D1 GoF
        d1_cursor = MockCursor()
        d1_cursor._fetchall_results = [[]]
        conn.add_cursor(d1_cursor)

        # D2 Kola
        d2_cursor = MockCursor()
        d2_cursor._fetchall_results = [[]]
        conn.add_cursor(d2_cursor)

        # D3 Baltic
        d3_cursor = MockCursor()
        d3_cursor._fetchall_results = [[]]
        conn.add_cursor(d3_cursor)

        # D4 Barents
        d4_cursor = MockCursor()
        d4_cursor._fetchall_results = [[]]
        conn.add_cursor(d4_cursor)

        # D6 STS
        sts_cursor = MockCursor()
        sts_cursor._fetchall_results = [[]]
        conn.add_cursor(sts_cursor)

        # D7 GoF
        d7_gof = MockCursor()
        d7_gof._fetchall_results = [[]]
        conn.add_cursor(d7_gof)

        # D7 Kola
        d7_kola = MockCursor()
        d7_kola._fetchall_results = [[]]
        conn.add_cursor(d7_kola)

        engine = GeographicInference(conn)
        signals = engine.evaluate_vessel(mmsi)

        d5_signals = [s for s in signals if s["signal_id"] == "D5"]
        assert len(d5_signals) == 0


# ---------------------------------------------------------------------------
# D7: Loiter-then-vanish
# ---------------------------------------------------------------------------


class TestD7LoiterThenVanish:
    """D7: staging area loiter + AIS gap >6h toward Russian port."""

    def test_d7_fires_with_loiter_and_gap(self):
        """D7 requires both staging area loiter AND subsequent AIS gap toward Russian port."""
        mmsi = 273999888

        # Positions: loiter in GoF for 14h, then gap with COG toward Primorsk
        gof_positions = [
            _make_position(mmsi, 24, 59.7, 26.0, sog=0.2, nav_status=1),
            _make_position(mmsi, 18, 59.7, 26.1, sog=0.3, nav_status=1),
            _make_position(mmsi, 10, 59.7, 26.0, sog=0.1, nav_status=1),
        ]

        # After loiter: one position, then gap >6h
        # COG ~65 degrees = roughly toward Primorsk (60.35, 28.67) from (59.7, 26.0)
        bearing_to_primorsk = _bearing_to_point(59.7, 26.0, 60.35, 28.67)
        post_loiter_pos = _make_position(
            mmsi, 9, 59.8, 26.5, sog=10.0,
            cog=bearing_to_primorsk, nav_status=0,
        )

        # Next position is 3 hours ago (gap of 6h from 9h ago)
        late_pos = _make_position(
            mmsi, 3, 60.1, 27.5, sog=8.0, cog=60.0, nav_status=0,
        )

        all_positions = gof_positions + [post_loiter_pos, late_pos]

        conn = MockConnection()

        # Profile
        profile_cursor = MockCursor()
        profile_cursor._fetchone_results = [_make_profile(mmsi, ship_type=80)]
        conn.add_cursor(profile_cursor)

        # All positions
        positions_cursor = MockCursor()
        positions_cursor._fetchall_results = [all_positions]
        conn.add_cursor(positions_cursor)

        # D1 GoF — loiter positions
        d1_cursor = MockCursor()
        d1_cursor._fetchall_results = [gof_positions]
        conn.add_cursor(d1_cursor)

        # D2 Kola — empty
        d2_cursor = MockCursor()
        d2_cursor._fetchall_results = [[]]
        conn.add_cursor(d2_cursor)

        # D3 Baltic
        d3_cursor = MockCursor()
        d3_cursor._fetchall_results = [[]]
        conn.add_cursor(d3_cursor)

        # D4 Barents
        d4_cursor = MockCursor()
        d4_cursor._fetchall_results = [[]]
        conn.add_cursor(d4_cursor)

        # D6 STS
        sts_cursor = MockCursor()
        sts_cursor._fetchall_results = [[]]
        conn.add_cursor(sts_cursor)

        # D7 GoF zone positions — the loiter + post-loiter positions
        d7_gof = MockCursor()
        d7_gof._fetchall_results = [gof_positions]
        conn.add_cursor(d7_gof)

        # D7 Kola — empty
        d7_kola = MockCursor()
        d7_kola._fetchall_results = [[]]
        conn.add_cursor(d7_kola)

        engine = GeographicInference(conn)
        signals = engine.evaluate_vessel(mmsi)

        d7_signals = [s for s in signals if s["signal_id"] == "D7"]
        assert len(d7_signals) == 1
        assert d7_signals[0]["weight"] == 4
        assert "loiter" in d7_signals[0]["details"]["description"].lower()

    def test_d7_does_not_fire_without_loiter(self):
        """D7 does NOT fire without staging area loiter (just an AIS gap)."""
        mmsi = 273999888

        # No loiter positions (all high speed, not in staging area)
        transit_positions = [
            _make_position(mmsi, 12, 57.0, 20.0, sog=12.0, cog=200.0, nav_status=0),
            _make_position(mmsi, 0, 55.0, 18.0, sog=12.0, cog=200.0, nav_status=0),
        ]

        conn = MockConnection()

        # Profile
        profile_cursor = MockCursor()
        profile_cursor._fetchone_results = [_make_profile(mmsi, ship_type=80)]
        conn.add_cursor(profile_cursor)

        # Positions
        positions_cursor = MockCursor()
        positions_cursor._fetchall_results = [transit_positions]
        conn.add_cursor(positions_cursor)

        # D1 GoF — empty
        d1_cursor = MockCursor()
        d1_cursor._fetchall_results = [[]]
        conn.add_cursor(d1_cursor)

        # D2 Kola — empty
        d2_cursor = MockCursor()
        d2_cursor._fetchall_results = [[]]
        conn.add_cursor(d2_cursor)

        # D3 Baltic
        d3_cursor = MockCursor()
        d3_cursor._fetchall_results = [[]]
        conn.add_cursor(d3_cursor)

        # D4 Barents
        d4_cursor = MockCursor()
        d4_cursor._fetchall_results = [[]]
        conn.add_cursor(d4_cursor)

        # D6 STS
        sts_cursor = MockCursor()
        sts_cursor._fetchall_results = [[]]
        conn.add_cursor(sts_cursor)

        # D7 GoF — empty (no staging area presence)
        d7_gof = MockCursor()
        d7_gof._fetchall_results = [[]]
        conn.add_cursor(d7_gof)

        # D7 Kola — empty
        d7_kola = MockCursor()
        d7_kola._fetchall_results = [[]]
        conn.add_cursor(d7_kola)

        engine = GeographicInference(conn)
        signals = engine.evaluate_vessel(mmsi)

        d7_signals = [s for s in signals if s["signal_id"] == "D7"]
        assert len(d7_signals) == 0

    def test_d7_does_not_fire_without_gap(self):
        """D7 does NOT fire with loiter but no AIS gap toward Russian port."""
        mmsi = 273999888

        # Loiter in GoF but continuous positions after (no gap)
        gof_positions = [
            _make_position(mmsi, 20, 59.7, 26.0, sog=0.2, nav_status=1),
            _make_position(mmsi, 14, 59.7, 26.1, sog=0.3, nav_status=1),
            _make_position(mmsi, 8, 59.7, 26.0, sog=0.1, nav_status=1),
        ]

        # Continuous positions after loiter (no gap)
        post_positions = [
            _make_position(mmsi, 7, 59.8, 26.5, sog=10.0, cog=180.0, nav_status=0),
            _make_position(mmsi, 6, 59.6, 26.5, sog=10.0, cog=180.0, nav_status=0),
            _make_position(mmsi, 5, 59.4, 26.5, sog=10.0, cog=180.0, nav_status=0),
            _make_position(mmsi, 4, 59.2, 26.5, sog=10.0, cog=180.0, nav_status=0),
            _make_position(mmsi, 3, 59.0, 26.5, sog=10.0, cog=180.0, nav_status=0),
            _make_position(mmsi, 2, 58.8, 26.5, sog=10.0, cog=180.0, nav_status=0),
            _make_position(mmsi, 1, 58.6, 26.5, sog=10.0, cog=180.0, nav_status=0),
            _make_position(mmsi, 0, 58.4, 26.5, sog=10.0, cog=180.0, nav_status=0),
        ]

        all_positions = gof_positions + post_positions

        conn = MockConnection()

        # Profile
        profile_cursor = MockCursor()
        profile_cursor._fetchone_results = [_make_profile(mmsi, ship_type=80)]
        conn.add_cursor(profile_cursor)

        # Positions
        positions_cursor = MockCursor()
        positions_cursor._fetchall_results = [all_positions]
        conn.add_cursor(positions_cursor)

        # D1 GoF
        d1_cursor = MockCursor()
        d1_cursor._fetchall_results = [gof_positions]
        conn.add_cursor(d1_cursor)

        # D2 Kola
        d2_cursor = MockCursor()
        d2_cursor._fetchall_results = [[]]
        conn.add_cursor(d2_cursor)

        # D3 Baltic
        d3_cursor = MockCursor()
        d3_cursor._fetchall_results = [[]]
        conn.add_cursor(d3_cursor)

        # D4 Barents
        d4_cursor = MockCursor()
        d4_cursor._fetchall_results = [[]]
        conn.add_cursor(d4_cursor)

        # D6 STS
        sts_cursor = MockCursor()
        sts_cursor._fetchall_results = [[]]
        conn.add_cursor(sts_cursor)

        # D7 GoF zone positions — loiter only
        d7_gof = MockCursor()
        d7_gof._fetchall_results = [gof_positions]
        conn.add_cursor(d7_gof)

        # D7 Kola
        d7_kola = MockCursor()
        d7_kola._fetchall_results = [[]]
        conn.add_cursor(d7_kola)

        engine = GeographicInference(conn)
        signals = engine.evaluate_vessel(mmsi)

        d7_signals = [s for s in signals if s["signal_id"] == "D7"]
        assert len(d7_signals) == 0


# ---------------------------------------------------------------------------
# Bearing helpers
# ---------------------------------------------------------------------------


class TestBearingHelpers:
    """Unit tests for bearing calculation utilities."""

    def test_bearing_north(self):
        """Bearing from equator to north pole is ~0 degrees."""
        b = _bearing_to_point(0, 0, 90, 0)
        assert abs(b) < 1 or abs(b - 360) < 1

    def test_bearing_east(self):
        """Bearing east is ~90 degrees."""
        b = _bearing_to_point(0, 0, 0, 10)
        assert abs(b - 90) < 1

    def test_bearing_difference_same(self):
        assert _bearing_difference(90, 90) == 0

    def test_bearing_difference_opposite(self):
        assert abs(_bearing_difference(0, 180) - 180) < 0.01

    def test_bearing_difference_wrap(self):
        """350 to 10 is 20 degrees, not 340."""
        assert abs(_bearing_difference(350, 10) - 20) < 0.01


# ---------------------------------------------------------------------------
# Signal weights
# ---------------------------------------------------------------------------


class TestSignalWeights:
    """Verify signal weight constants match spec."""

    def test_weights(self):
        assert SIGNAL_WEIGHTS["D1"] == 3
        assert SIGNAL_WEIGHTS["D2"] == 3
        assert SIGNAL_WEIGHTS["D3"] == 4
        assert SIGNAL_WEIGHTS["D4"] == 4
        assert SIGNAL_WEIGHTS["D5"] == 2
        assert SIGNAL_WEIGHTS["D6"] == 4
        assert SIGNAL_WEIGHTS["D7"] == 4
