"""Tests for flag state derivation and mismatch detection."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from flag_derivation import (
    derive_and_compare,
    derive_flag_from_mmsi,
    detect_flag_mismatches,
    extract_mid,
    mid_to_flag,
    update_flag_history,
)


# ---------------------------------------------------------------------------
# MID extraction tests
# ---------------------------------------------------------------------------

class TestExtractMID:
    def test_valid_mmsi(self):
        assert extract_mid(273456789) == 273

    def test_another_valid_mmsi(self):
        assert extract_mid(351123456) == 351

    def test_mmsi_too_short(self):
        assert extract_mid(12345) is None

    def test_mmsi_too_long(self):
        assert extract_mid(1234567890) is None

    def test_mmsi_not_int(self):
        assert extract_mid("273456789") is None  # type: ignore


# ---------------------------------------------------------------------------
# MID to flag lookup tests
# ---------------------------------------------------------------------------

class TestMIDToFlag:
    def test_mid_273_is_russia(self):
        assert mid_to_flag(273) == "RU"

    def test_mid_351_is_panama(self):
        assert mid_to_flag(351) == "PA"

    def test_mid_338_is_us(self):
        assert mid_to_flag(338) == "US"

    def test_mid_211_is_germany(self):
        assert mid_to_flag(211) == "DE"

    def test_mid_563_is_singapore(self):
        assert mid_to_flag(563) == "SG"

    def test_unknown_mid(self):
        assert mid_to_flag(999) is None


# ---------------------------------------------------------------------------
# Derive flag from MMSI tests
# ---------------------------------------------------------------------------

class TestDeriveFlagFromMMSI:
    def test_russian_vessel(self):
        assert derive_flag_from_mmsi(273456789) == "RU"

    def test_panamanian_vessel(self):
        assert derive_flag_from_mmsi(351123456) == "PA"

    def test_invalid_mmsi(self):
        assert derive_flag_from_mmsi(0) is None


# ---------------------------------------------------------------------------
# Flag mismatch detection tests
# ---------------------------------------------------------------------------

class TestDetectFlagMismatches:
    def test_no_mismatch_when_all_agree(self):
        mismatches = detect_flag_mismatches(
            mid_flag="RU", gfw_flag="RU", gisis_flag="RU"
        )
        assert mismatches == []

    def test_mismatch_mid_vs_gfw(self):
        mismatches = detect_flag_mismatches(mid_flag="RU", gfw_flag="PA")
        assert len(mismatches) == 1
        m = mismatches[0]
        assert m["source_a"] == "mid"
        assert m["flag_a"] == "RU"
        assert m["source_b"] == "gfw"
        assert m["flag_b"] == "PA"

    def test_mismatch_all_three_different(self):
        mismatches = detect_flag_mismatches(
            mid_flag="RU", gfw_flag="PA", gisis_flag="LR"
        )
        assert len(mismatches) == 3  # RU-PA, RU-LR, PA-LR

    def test_no_flags_no_mismatches(self):
        mismatches = detect_flag_mismatches()
        assert mismatches == []

    def test_single_flag_no_mismatches(self):
        mismatches = detect_flag_mismatches(mid_flag="RU")
        assert mismatches == []

    def test_mismatch_is_detected_and_recorded(self):
        """Flag mismatch between GFW and MID-derived flag is detected."""
        # Vessel has Russian MMSI but GFW says Panama
        mismatches = detect_flag_mismatches(mid_flag="RU", gfw_flag="PA")
        assert len(mismatches) == 1
        assert mismatches[0]["flag_a"] == "RU"
        assert mismatches[0]["flag_b"] == "PA"


# ---------------------------------------------------------------------------
# Flag history update tests
# ---------------------------------------------------------------------------

class TestUpdateFlagHistory:
    def test_first_flag_creates_entry(self):
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        history = update_flag_history([], "RU", ts)
        assert len(history) == 1
        assert history[0]["flag"] == "RU"
        assert history[0]["first_seen"] == ts.isoformat()
        assert history[0]["last_seen"] == ts.isoformat()

    def test_same_flag_updates_last_seen(self):
        ts1 = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 2, 15, 12, 0, 0, tzinfo=timezone.utc)
        history = update_flag_history([], "RU", ts1)
        history = update_flag_history(history, "RU", ts2)
        assert len(history) == 1
        assert history[0]["flag"] == "RU"
        assert history[0]["first_seen"] == ts1.isoformat()
        assert history[0]["last_seen"] == ts2.isoformat()

    def test_different_flag_adds_new_entry(self):
        ts1 = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        history = update_flag_history([], "RU", ts1)
        history = update_flag_history(history, "PA", ts2)
        assert len(history) == 2
        assert history[0]["flag"] == "RU"
        assert history[1]["flag"] == "PA"
        assert history[1]["first_seen"] == ts2.isoformat()

    def test_does_not_mutate_input(self):
        original = [{"flag": "RU", "first_seen": "2024-01-01", "last_seen": "2024-01-01"}]
        original_copy = [e.copy() for e in original]
        update_flag_history(original, "PA")
        assert original == original_copy


# ---------------------------------------------------------------------------
# Full pipeline tests
# ---------------------------------------------------------------------------

class TestDeriveAndCompare:
    def test_russian_vessel_no_mismatch(self):
        result = derive_and_compare(
            273456789,
            gfw_flag="RU",
            timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        assert result["mid_flag"] == "RU"
        assert result["primary_flag"] == "RU"
        assert result["mismatches"] == []
        assert len(result["flag_history"]) == 1
        assert result["flag_history"][0]["flag"] == "RU"

    def test_flag_mismatch_detected(self):
        result = derive_and_compare(
            273456789,  # MID 273 = RU
            gfw_flag="PA",
            timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        assert result["mid_flag"] == "RU"
        assert result["primary_flag"] == "PA"  # GFW takes priority
        assert len(result["mismatches"]) == 1

    def test_flag_history_preserved_and_updated(self):
        existing_history = [
            {
                "flag": "LR",
                "first_seen": "2023-01-01T00:00:00+00:00",
                "last_seen": "2023-06-01T00:00:00+00:00",
            }
        ]
        result = derive_and_compare(
            351123456,
            gfw_flag="PA",
            current_flag_history=existing_history,
            timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        assert result["mid_flag"] == "PA"
        assert len(result["flag_history"]) == 2
        assert result["flag_history"][0]["flag"] == "LR"
        assert result["flag_history"][1]["flag"] == "PA"

    def test_flag_history_same_flag_updates_last_seen(self):
        existing_history = [
            {
                "flag": "PA",
                "first_seen": "2023-01-01T00:00:00+00:00",
                "last_seen": "2023-06-01T00:00:00+00:00",
            }
        ]
        result = derive_and_compare(
            351123456,
            gfw_flag="PA",
            current_flag_history=existing_history,
            timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        assert len(result["flag_history"]) == 1
        assert result["flag_history"][0]["last_seen"] == "2024-06-01T00:00:00+00:00"

    def test_invalid_mmsi(self):
        result = derive_and_compare(0, gfw_flag="PA")
        assert result["mid_flag"] is None
        assert result["primary_flag"] == "PA"

    def test_no_flags_available(self):
        result = derive_and_compare(100000000)  # MID 100 not in table
        assert result["mid_flag"] is None
        assert result["primary_flag"] is None
        assert result["flag_history"] == []
