"""Tests for classification and insurance enrichment (spec 20, story 3).

Tests cover:
- Classification society extraction from GFW vessel identity
- IACS membership detection
- Classification change history tracking
- P&I insurance data from manual enrichment fallback
- Integration with fetch_and_update_vessel_profile
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Add paths for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from vessel_fetcher import (
    IACS_MEMBERS,
    build_classification_data,
    build_insurance_data,
    fetch_and_update_vessel_profile,
    _derive_society_code,
    _get_first_entry,
)


# ===================================================================
# Sample Data
# ===================================================================

SAMPLE_GFW_WITH_CLASSIFICATION = {
    "ssvid": "273456789",
    "selfReportedInfo": [
        {
            "ssvid": "273456789",
            "shipname": "VOLGA TRADER",
            "flag": "RUS",
        }
    ],
    "registryInfo": [
        {
            "imoNumber": "9876543",
            "shipname": "VOLGA TRADER",
            "flag": "RUS",
            "owner": "Volga Shipping Co.",
            "operator": "Volga Maritime",
            "classificationSociety": "DNV",
            "grossTonnage": 5400,
            "deadweight": 7200,
            "builtYear": 2005,
            "lengthOverallLOA": 112.5,
            "beam": 15.8,
        }
    ],
    "combinedSourcesInfo": [
        {
            "shipname": "VOLGA TRADER",
            "flag": "RUS",
        }
    ],
}

SAMPLE_GFW_UNKNOWN_CLASSIFICATION = {
    "registryInfo": [
        {
            "classificationSociety": "Unknown Society",
            "shipname": "MYSTERY VESSEL",
        }
    ],
}

SAMPLE_GFW_NO_CLASSIFICATION = {
    "ssvid": "351123456",
    "selfReportedInfo": [
        {
            "ssvid": "351123456",
            "shipname": "PACIFIC STAR",
            "flag": "PAN",
        }
    ],
}

SAMPLE_GFW_RUSSIAN_REGISTER = {
    "registryInfo": [
        {
            "classificationSociety": "Russian Maritime Register of Shipping",
            "shipname": "NEVA SPIRIT",
        }
    ],
}

SAMPLE_GFW_FULL_NAME_CLASS = {
    "registryInfo": [
        {
            "classificationSociety": "Lloyd's Register",
            "shipname": "ATLANTIC TRADER",
        }
    ],
}

SAMPLE_VESSEL_RESPONSE = {
    "entries": [SAMPLE_GFW_WITH_CLASSIFICATION]
}

SAMPLE_VESSEL_EMPTY = {"entries": []}


# ===================================================================
# build_classification_data Tests
# ===================================================================


class TestBuildClassificationData:
    """Test classification society data extraction."""

    def test_dnv_returns_iacs_true(self):
        """GFW returns classification 'DNV' -> stored with is_iacs=true."""
        result = build_classification_data(SAMPLE_GFW_WITH_CLASSIFICATION)

        assert result is not None
        assert result["society_name"] == "DNV"
        assert result["society_code"] == "DNV"
        assert result["is_iacs"] is True
        assert result["class_status"] == "active"
        assert result["class_change_history"] == []
        assert "last_updated" in result

    def test_unknown_society_returns_iacs_false(self):
        """GFW returns classification 'Unknown Society' -> stored with is_iacs=false."""
        result = build_classification_data(SAMPLE_GFW_UNKNOWN_CLASSIFICATION)

        assert result is not None
        assert result["society_name"] == "Unknown Society"
        assert result["is_iacs"] is False

    def test_no_classification_returns_none(self):
        """No classification data from GFW -> returns None."""
        result = build_classification_data(SAMPLE_GFW_NO_CLASSIFICATION)
        assert result is None

    def test_classification_from_combined_sources(self):
        """Classification found in combinedSourcesInfo when not in registryInfo."""
        raw = {
            "registryInfo": [{"shipname": "TEST VESSEL"}],
            "combinedSourcesInfo": [{"classificationSociety": "BV"}],
        }
        result = build_classification_data(raw)

        assert result is not None
        assert result["society_name"] == "BV"
        assert result["society_code"] == "BV"
        assert result["is_iacs"] is True

    def test_classification_from_top_level(self):
        """Classification found at top level when not in nested structures."""
        raw = {"classificationSociety": "ABS"}
        result = build_classification_data(raw)

        assert result is not None
        assert result["society_name"] == "ABS"
        assert result["society_code"] == "ABS"
        assert result["is_iacs"] is True

    def test_full_name_mapped_to_code(self):
        """Full society name 'Lloyd's Register' -> code 'LR', is_iacs=true."""
        result = build_classification_data(SAMPLE_GFW_FULL_NAME_CLASS)

        assert result is not None
        assert result["society_name"] == "Lloyd's Register"
        assert result["society_code"] == "LR"
        assert result["is_iacs"] is True

    def test_russian_register_mapped_correctly(self):
        """Russian Maritime Register of Shipping -> code 'RS', is_iacs=true."""
        result = build_classification_data(SAMPLE_GFW_RUSSIAN_REGISTER)

        assert result is not None
        assert result["society_name"] == "Russian Maritime Register of Shipping"
        assert result["society_code"] == "RS"
        assert result["is_iacs"] is True

    def test_classification_change_detected(self):
        """Classification change from DNV to Russian Register -> history entry added."""
        existing_profile = {
            "classification_data": {
                "society_name": "DNV",
                "society_code": "DNV",
                "is_iacs": True,
                "class_change_history": [],
            }
        }

        result = build_classification_data(
            SAMPLE_GFW_RUSSIAN_REGISTER, existing_profile
        )

        assert result is not None
        assert result["society_name"] == "Russian Maritime Register of Shipping"
        assert result["society_code"] == "RS"
        assert len(result["class_change_history"]) == 1

        change = result["class_change_history"][0]
        assert change["change"] == "classification_changed"
        assert change["from"] == "DNV"
        assert change["to"] == "Russian Maritime Register of Shipping"
        assert "date" in change

    def test_classification_change_appends_to_existing_history(self):
        """New classification change appends to existing history, doesn't overwrite."""
        existing_profile = {
            "classification_data": {
                "society_name": "BV",
                "society_code": "BV",
                "is_iacs": True,
                "class_change_history": [
                    {
                        "date": "2025-01-01T00:00:00+00:00",
                        "change": "classification_changed",
                        "from": "LR",
                        "to": "BV",
                    }
                ],
            }
        }

        result = build_classification_data(
            SAMPLE_GFW_WITH_CLASSIFICATION, existing_profile
        )

        assert result is not None
        assert result["society_name"] == "DNV"
        assert len(result["class_change_history"]) == 2
        assert result["class_change_history"][0]["from"] == "LR"
        assert result["class_change_history"][1]["from"] == "BV"
        assert result["class_change_history"][1]["to"] == "DNV"

    def test_same_classification_no_history_entry(self):
        """Same classification society -> no new history entry."""
        existing_profile = {
            "classification_data": {
                "society_name": "DNV",
                "society_code": "DNV",
                "is_iacs": True,
                "class_change_history": [],
            }
        }

        result = build_classification_data(
            SAMPLE_GFW_WITH_CLASSIFICATION, existing_profile
        )

        assert result is not None
        assert result["society_name"] == "DNV"
        assert result["class_change_history"] == []

    def test_existing_profile_with_json_string_classification(self):
        """Existing profile with classification_data as JSON string is handled."""
        existing_profile = {
            "classification_data": json.dumps({
                "society_name": "LR",
                "society_code": "LR",
                "is_iacs": True,
                "class_change_history": [],
            })
        }

        result = build_classification_data(
            SAMPLE_GFW_WITH_CLASSIFICATION, existing_profile
        )

        assert result is not None
        assert len(result["class_change_history"]) == 1
        assert result["class_change_history"][0]["from"] == "LR"
        assert result["class_change_history"][0]["to"] == "DNV"


# ===================================================================
# build_insurance_data Tests
# ===================================================================


class TestBuildInsuranceData:
    """Test P&I insurance data extraction."""

    def test_pi_data_from_manual_enrichment(self):
        """P&I data stored when available from manual enrichment."""
        manual_enrichments = [
            {
                "pi_tier": "ig_member",
                "pi_details": "Gard P&I Club",
                "source": "equasis",
            }
        ]

        result = build_insurance_data({}, manual_enrichments=manual_enrichments)

        assert result is not None
        assert result["provider"] == "Gard P&I Club"
        assert result["is_ig_member"] is True
        assert result["coverage_status"] == "ig_member"
        assert "last_updated" in result

    def test_non_ig_provider(self):
        """Non-IG P&I provider -> is_ig_member=false."""
        manual_enrichments = [
            {
                "pi_tier": "non_ig",
                "pi_details": "Ingosstrakh Insurance",
                "source": "manual",
            }
        ]

        result = build_insurance_data({}, manual_enrichments=manual_enrichments)

        assert result is not None
        assert result["provider"] == "Ingosstrakh Insurance"
        assert result["is_ig_member"] is False
        assert result["coverage_status"] == "non_ig"

    def test_no_pi_data_returns_none(self):
        """No P&I data from any source -> returns None."""
        result = build_insurance_data({})
        assert result is None

    def test_no_pi_data_with_empty_enrichments_returns_none(self):
        """Empty manual enrichments list -> returns None."""
        result = build_insurance_data({}, manual_enrichments=[])
        assert result is None

    def test_manual_enrichment_with_only_pi_tier(self):
        """Manual enrichment with pi_tier but no pi_details."""
        manual_enrichments = [
            {"pi_tier": "no_pi", "pi_details": None, "source": "manual"}
        ]

        result = build_insurance_data({}, manual_enrichments=manual_enrichments)

        assert result is not None
        assert result["provider"] is None
        assert result["is_ig_member"] is False
        assert result["coverage_status"] == "no_pi"

    def test_multiple_enrichments_uses_newest(self):
        """Multiple manual enrichments -> newest with P&I data is used."""
        manual_enrichments = [
            # Newest first (from query ORDER BY created_at DESC)
            {
                "pi_tier": "ig_member",
                "pi_details": "North P&I Club",
                "source": "equasis",
            },
            {
                "pi_tier": "non_ig",
                "pi_details": "Old Insurance Co",
                "source": "manual",
            },
        ]

        result = build_insurance_data({}, manual_enrichments=manual_enrichments)

        assert result is not None
        assert result["provider"] == "North P&I Club"
        assert result["is_ig_member"] is True

    def test_ig_member_detection_various_clubs(self):
        """Various IG P&I clubs are correctly identified."""
        ig_clubs = [
            "Britannia P&I Club",
            "The London P&I Club",
            "Skuld",
            "The Standard Club",
            "West of England P&I Club",
            "UK P&I Club",
            "Steamship Mutual",
            "Swedish Club",
            "Japan P&I Club",
            "American Steamship Owners Mutual",
        ]

        for club in ig_clubs:
            enrichments = [{"pi_tier": "ig_member", "pi_details": club}]
            result = build_insurance_data({}, manual_enrichments=enrichments)
            assert result is not None, f"Failed for {club}"
            assert result["is_ig_member"] is True, f"{club} should be IG member"

    def test_manual_enrichment_without_pi_fields_skipped(self):
        """Manual enrichment without pi_tier or pi_details is skipped."""
        manual_enrichments = [
            {"analyst_notes": "Suspicious vessel", "source": "manual"},
            {"pi_tier": "ig_member", "pi_details": "Gard", "source": "equasis"},
        ]

        result = build_insurance_data({}, manual_enrichments=manual_enrichments)

        assert result is not None
        assert result["provider"] == "Gard"


# ===================================================================
# Helper Function Tests
# ===================================================================


class TestHelperFunctions:
    """Test helper functions for classification extraction."""

    def test_derive_society_code_iacs_members(self):
        """All IACS member names are correctly mapped."""
        assert _derive_society_code("DNV") == "DNV"
        assert _derive_society_code("Bureau Veritas") == "BV"
        assert _derive_society_code("American Bureau of Shipping") == "ABS"
        assert _derive_society_code("Lloyd's Register") == "LR"
        assert _derive_society_code("ClassNK") == "NK"
        assert _derive_society_code("Korean Register") == "KR"
        assert _derive_society_code("RINA") == "RINA"
        assert _derive_society_code("DNV GL") == "DNV"

    def test_derive_society_code_short_abbreviation(self):
        """Short abbreviation is returned uppercased."""
        assert _derive_society_code("BV") == "BV"
        assert _derive_society_code("lr") == "LR"

    def test_derive_society_code_unknown_long_name(self):
        """Unknown long name is returned uppercased."""
        result = _derive_society_code("Unknown Society")
        assert result == "UNKNOWN SOCIETY"

    def test_get_first_entry_list(self):
        """List field returns first element."""
        raw = {"registryInfo": [{"shipname": "TEST"}]}
        result = _get_first_entry(raw, "registryInfo")
        assert result == {"shipname": "TEST"}

    def test_get_first_entry_dict(self):
        """Dict field is returned as-is."""
        raw = {"registryInfo": {"shipname": "TEST"}}
        result = _get_first_entry(raw, "registryInfo")
        assert result == {"shipname": "TEST"}

    def test_get_first_entry_missing(self):
        """Missing field returns empty dict."""
        result = _get_first_entry({}, "registryInfo")
        assert result == {}

    def test_get_first_entry_empty_list(self):
        """Empty list returns empty dict."""
        result = _get_first_entry({"registryInfo": []}, "registryInfo")
        assert result == {}

    def test_iacs_members_set(self):
        """IACS_MEMBERS contains all 12 expected members."""
        expected = {"ABS", "BV", "CCS", "CRS", "DNV", "IRS", "KR", "LR", "NK", "PRS", "RINA", "RS"}
        assert IACS_MEMBERS == expected


# ===================================================================
# Integration: fetch_and_update_vessel_profile with classification
# ===================================================================


class TestFetchAndUpdateWithClassification:
    """Test fetch_and_update_vessel_profile stores classification/insurance data."""

    @pytest.mark.asyncio
    async def test_classification_data_passed_to_upsert(self):
        """Classification data from GFW is included in profile upsert."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()
        mock_get_profile = AsyncMock(return_value=None)
        mock_get_enrichments = AsyncMock(return_value=[])

        result = await fetch_and_update_vessel_profile(
            mock_client,
            mock_session,
            273456789,
            _upsert_fn=mock_upsert,
            _get_profile_fn=mock_get_profile,
            _get_enrichments_fn=mock_get_enrichments,
            _raw_entry=SAMPLE_GFW_WITH_CLASSIFICATION,
        )

        assert result is not None
        mock_upsert.assert_called_once()

        profile_data = mock_upsert.call_args[0][1]
        assert profile_data["mmsi"] == 273456789

        # Classification data should be a JSON string
        class_data = json.loads(profile_data["classification_data"])
        assert class_data["society_name"] == "DNV"
        assert class_data["society_code"] == "DNV"
        assert class_data["is_iacs"] is True

    @pytest.mark.asyncio
    async def test_no_classification_passes_none(self):
        """No classification in GFW response -> classification_data is None."""
        raw_no_class = SAMPLE_GFW_NO_CLASSIFICATION
        mock_client = AsyncMock()
        mock_client.get.return_value = {"entries": [raw_no_class]}
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()
        mock_get_profile = AsyncMock(return_value=None)
        mock_get_enrichments = AsyncMock(return_value=[])

        await fetch_and_update_vessel_profile(
            mock_client,
            mock_session,
            351123456,
            _upsert_fn=mock_upsert,
            _get_profile_fn=mock_get_profile,
            _get_enrichments_fn=mock_get_enrichments,
            _raw_entry=raw_no_class,
        )

        profile_data = mock_upsert.call_args[0][1]
        assert profile_data["classification_data"] is None

    @pytest.mark.asyncio
    async def test_insurance_data_from_manual_enrichment(self):
        """P&I data from manual enrichment is stored in profile."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()
        mock_get_profile = AsyncMock(return_value=None)
        mock_get_enrichments = AsyncMock(return_value=[
            {"pi_tier": "ig_member", "pi_details": "Gard P&I Club", "source": "equasis"}
        ])

        await fetch_and_update_vessel_profile(
            mock_client,
            mock_session,
            273456789,
            _upsert_fn=mock_upsert,
            _get_profile_fn=mock_get_profile,
            _get_enrichments_fn=mock_get_enrichments,
            _raw_entry=SAMPLE_GFW_WITH_CLASSIFICATION,
        )

        profile_data = mock_upsert.call_args[0][1]
        ins_data = json.loads(profile_data["insurance_data"])
        assert ins_data["provider"] == "Gard P&I Club"
        assert ins_data["is_ig_member"] is True
        assert ins_data["coverage_status"] == "ig_member"

    @pytest.mark.asyncio
    async def test_no_insurance_data_passes_none(self):
        """No P&I data available -> insurance_data is None."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()
        mock_get_profile = AsyncMock(return_value=None)
        mock_get_enrichments = AsyncMock(return_value=[])

        await fetch_and_update_vessel_profile(
            mock_client,
            mock_session,
            273456789,
            _upsert_fn=mock_upsert,
            _get_profile_fn=mock_get_profile,
            _get_enrichments_fn=mock_get_enrichments,
            _raw_entry=SAMPLE_GFW_WITH_CLASSIFICATION,
        )

        profile_data = mock_upsert.call_args[0][1]
        assert profile_data["insurance_data"] is None

    @pytest.mark.asyncio
    async def test_classification_change_detected_in_update(self):
        """Classification change is detected when updating existing profile."""
        existing = {
            "mmsi": 273456789,
            "classification_data": {
                "society_name": "LR",
                "society_code": "LR",
                "is_iacs": True,
                "class_change_history": [],
            },
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()
        mock_get_profile = AsyncMock(return_value=existing)
        mock_get_enrichments = AsyncMock(return_value=[])

        await fetch_and_update_vessel_profile(
            mock_client,
            mock_session,
            273456789,
            _upsert_fn=mock_upsert,
            _get_profile_fn=mock_get_profile,
            _get_enrichments_fn=mock_get_enrichments,
            _raw_entry=SAMPLE_GFW_WITH_CLASSIFICATION,
        )

        profile_data = mock_upsert.call_args[0][1]
        class_data = json.loads(profile_data["classification_data"])
        assert class_data["society_name"] == "DNV"
        assert len(class_data["class_change_history"]) == 1
        assert class_data["class_change_history"][0]["from"] == "LR"
        assert class_data["class_change_history"][0]["to"] == "DNV"

    @pytest.mark.asyncio
    async def test_enrichment_status_and_enriched_at_in_profile(self):
        """Profile data includes enrichment_status and enriched_at fields."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()
        mock_get_profile = AsyncMock(return_value=None)
        mock_get_enrichments = AsyncMock(return_value=[])

        await fetch_and_update_vessel_profile(
            mock_client,
            mock_session,
            273456789,
            _upsert_fn=mock_upsert,
            _get_profile_fn=mock_get_profile,
            _get_enrichments_fn=mock_get_enrichments,
            _raw_entry=SAMPLE_GFW_WITH_CLASSIFICATION,
        )

        profile_data = mock_upsert.call_args[0][1]
        # These fields should be present (set to None for now, populated by later stories)
        assert "enrichment_status" in profile_data
        assert "enriched_at" in profile_data

    @pytest.mark.asyncio
    async def test_existing_tests_still_work_without_new_params(self):
        """fetch_and_update_vessel_profile works without the new optional params."""
        mock_client = AsyncMock()
        mock_client.get.return_value = SAMPLE_VESSEL_RESPONSE
        mock_session = AsyncMock()
        mock_upsert = AsyncMock()

        result = await fetch_and_update_vessel_profile(
            mock_client, mock_session, 273456789, _upsert_fn=mock_upsert
        )

        assert result is not None
        mock_upsert.assert_called_once()
        profile_data = mock_upsert.call_args[0][1]
        assert profile_data["mmsi"] == 273456789
        # New columns should be present (None since no raw_entry provided)
        assert "classification_data" in profile_data
        assert "insurance_data" in profile_data
