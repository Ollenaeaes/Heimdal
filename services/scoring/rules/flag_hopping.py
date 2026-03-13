"""Flag Hopping rule.

Detects vessels that have changed their flag state (derived from MMSI
MID digits) multiple times within a 12-month window.  Frequent flag
changes are a strong indicator of sanctions evasion.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from shared.constants import MID_TO_FLAG
from shared.models.anomaly import RuleResult

from .base import ScoringRule
from .identity_mismatch import _normalize_flag

_WINDOW_MONTHS = 12


def _utcnow() -> datetime:
    """Return current UTC time.  Extracted for easy patching in tests."""
    return datetime.now(timezone.utc)


class FlagHoppingRule(ScoringRule):
    """Fire when a vessel has used multiple flags in the last 12 months."""

    @property
    def rule_id(self) -> str:
        return "flag_hopping"

    @property
    def rule_category(self) -> str:
        return "realtime"

    async def evaluate(
        self,
        mmsi: int,
        profile: dict[str, Any] | None,
        recent_positions: Sequence[dict[str, Any]],
        existing_anomalies: Sequence[dict[str, Any]],
        gfw_events: Sequence[dict[str, Any]],
    ) -> Optional[RuleResult]:
        if not profile:
            return None

        # Derive current flag from MMSI
        current_flag = self._flag_from_mmsi(mmsi)

        # Collect distinct flags from flag history
        flags = self._collect_flags(profile, current_flag)

        if len(flags) >= 3:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="high",
                points=40.0,
                details={
                    "flags": sorted(flags),
                    "flag_count": len(flags),
                    "current_flag": current_flag,
                },
                source="realtime",
            )

        if len(flags) == 2:
            return RuleResult(
                fired=True,
                rule_id=self.rule_id,
                severity="moderate",
                points=15.0,
                details={
                    "flags": sorted(flags),
                    "flag_count": len(flags),
                    "current_flag": current_flag,
                },
                source="realtime",
            )

        return RuleResult(fired=False, rule_id=self.rule_id)

    # ------------------------------------------------------------------

    @staticmethod
    def _flag_from_mmsi(mmsi: int) -> Optional[str]:
        """Extract the MID (first 3 digits) from an MMSI and look up the flag."""
        mid = int(str(mmsi)[:3])
        return MID_TO_FLAG.get(mid)

    @staticmethod
    def _collect_flags(
        profile: dict[str, Any],
        current_flag: Optional[str],
    ) -> set[str]:
        """Collect distinct flags from profile data and the current MMSI-derived flag.

        Looks for flag_history in profile fields like ``flag_history``,
        ``ownership_data``, or ``pi_details``.
        """
        flags: set[str] = set()
        if current_flag:
            flags.add(_normalize_flag(current_flag))

        # Check profile's flag_country (normalize alpha-3 → alpha-2)
        profile_flag = profile.get("flag_country")
        if profile_flag:
            flags.add(_normalize_flag(profile_flag))

        # Check equasis flag_history (has actual dated flag changes)
        equasis_data = profile.get("equasis_data")
        if equasis_data and isinstance(equasis_data.get("flag_history"), list):
            now = _utcnow()
            cutoff = now - timedelta(days=365)
            for entry in equasis_data["flag_history"]:
                if isinstance(entry, dict):
                    flag = entry.get("flag")
                    if not flag:
                        continue
                    # Use date_of_effect for accurate windowing
                    date_str = entry.get("date_of_effect")
                    if date_str:
                        try:
                            parts = date_str.split("/")
                            if len(parts) == 3:
                                flag_date = datetime(
                                    int(parts[2]),
                                    int(parts[1]),
                                    int(parts[0]),
                                    tzinfo=timezone.utc,
                                )
                                if flag_date < cutoff:
                                    continue
                        except (ValueError, IndexError):
                            pass
                    flags.add(_normalize_flag(flag))

        # Check flag_history (list of dicts with 'flag' key)
        flag_history = profile.get("flag_history")
        if isinstance(flag_history, list):
            now = _utcnow()
            cutoff = now - timedelta(days=365)
            for entry in flag_history:
                if isinstance(entry, dict):
                    flag = entry.get("flag")
                    if not flag:
                        continue
                    # Check if within window
                    first_seen = entry.get("first_seen")
                    if first_seen:
                        if isinstance(first_seen, str):
                            first_seen = datetime.fromisoformat(first_seen)
                        if not first_seen.tzinfo:
                            first_seen = first_seen.replace(tzinfo=timezone.utc)
                        if first_seen < cutoff:
                            continue
                    flags.add(_normalize_flag(flag))

        return flags
