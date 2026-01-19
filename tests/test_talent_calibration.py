"""
Tests for talent calibration features.

Covers:
- Derivation functions (derive_overall_performance, derive_future_talent)
- Spreadsheet type detection
- Talent column mapping and parsing
"""
import pytest
from datetime import datetime
import tempfile
import os

from models import derive_overall_performance, derive_future_talent
from xlsx_utils import (
    detect_spreadsheet_type,
    find_talent_column_indices,
    TALENT_COLUMN_MAP,
    TALENT_MARKERS,
    BONUS_MARKERS,
)


class TestDeriveOverallPerformance:
    """Tests for derive_overall_performance() per Spec §4.1."""

    def test_surpasses_surpasses_yields_high_impact(self):
        """Surpasses + Surpasses = High Impact Performer."""
        assert derive_overall_performance(
            "Surpasses Expectations", "Surpasses Expectations"
        ) == "High Impact Performer"

    def test_surpasses_meets_yields_high_impact(self):
        """Surpasses + Meets = High Impact Performer."""
        assert derive_overall_performance(
            "Surpasses Expectations", "Meets Expectations"
        ) == "High Impact Performer"

    def test_meets_meets_yields_successful(self):
        """Meets + Meets = Successful Performer."""
        assert derive_overall_performance(
            "Meets Expectations", "Meets Expectations"
        ) == "Successful Performer"

    def test_meets_surpasses_yields_successful(self):
        """Meets + Surpasses = Successful Performer."""
        assert derive_overall_performance(
            "Meets Expectations", "Surpasses Expectations"
        ) == "Successful Performer"

    def test_surpasses_some_yields_successful(self):
        """Surpasses + Meets Some = Successful Performer."""
        assert derive_overall_performance(
            "Surpasses Expectations", "Meets Some Expectations"
        ) == "Successful Performer"

    def test_meets_some_yields_evolving(self):
        """Meets + Meets Some = Evolving Performer."""
        assert derive_overall_performance(
            "Meets Expectations", "Meets Some Expectations"
        ) == "Evolving Performer"

    def test_some_meets_yields_evolving(self):
        """Meets Some + Meets = Evolving Performer."""
        assert derive_overall_performance(
            "Meets Some Expectations", "Meets Expectations"
        ) == "Evolving Performer"

    def test_some_surpasses_yields_evolving(self):
        """Meets Some + Surpasses = Evolving Performer."""
        assert derive_overall_performance(
            "Meets Some Expectations", "Surpasses Expectations"
        ) == "Evolving Performer"

    def test_some_some_yields_low(self):
        """Meets Some + Meets Some = Low Performer."""
        assert derive_overall_performance(
            "Meets Some Expectations", "Meets Some Expectations"
        ) == "Low Performer"

    def test_any_does_not_meet_yields_low(self):
        """Any What + Does Not Meet = Low Performer."""
        assert derive_overall_performance(
            "Meets Expectations", "Does Not Meet Expectations"
        ) == "Low Performer"
        assert derive_overall_performance(
            "Surpasses Expectations", "Does Not Meet Expectations"
        ) == "Low Performer"
        assert derive_overall_performance(
            "Meets Some Expectations", "Does Not Meet Expectations"
        ) == "Low Performer"

    def test_null_what_returns_none(self):
        """None or empty What returns None."""
        assert derive_overall_performance(None, "Meets Expectations") is None
        assert derive_overall_performance("", "Meets Expectations") is None

    def test_null_how_returns_none(self):
        """None or empty How returns None."""
        assert derive_overall_performance("Meets Expectations", None) is None
        assert derive_overall_performance("Meets Expectations", "") is None

    def test_both_null_returns_none(self):
        """Both None/empty returns None."""
        assert derive_overall_performance(None, None) is None
        assert derive_overall_performance("", "") is None

    def test_case_insensitive(self):
        """Function handles case variations."""
        assert derive_overall_performance(
            "SURPASSES EXPECTATIONS", "MEETS EXPECTATIONS"
        ) == "High Impact Performer"
        assert derive_overall_performance(
            "meets expectations", "meets some expectations"
        ) == "Evolving Performer"


class TestDeriveFutureTalent:
    """Tests for derive_future_talent() per Spec §4.2."""

    def test_both_always_returns_true(self):
        """Both agility = Always/Most of the Time returns True."""
        assert derive_future_talent(
            "Always/Most of the Time", "Always/Most of the Time"
        ) is True

    def test_growth_always_change_sometimes_returns_false(self):
        """Growth Always + Change Sometimes returns False."""
        assert derive_future_talent(
            "Always/Most of the Time", "Sometimes"
        ) is False

    def test_growth_sometimes_change_always_returns_false(self):
        """Growth Sometimes + Change Always returns False."""
        assert derive_future_talent(
            "Sometimes", "Always/Most of the Time"
        ) is False

    def test_both_sometimes_returns_false(self):
        """Both Sometimes returns False."""
        assert derive_future_talent("Sometimes", "Sometimes") is False

    def test_null_growth_returns_false(self):
        """None/empty growth returns False."""
        assert derive_future_talent(None, "Always/Most of the Time") is False
        assert derive_future_talent("", "Always/Most of the Time") is False

    def test_null_change_returns_false(self):
        """None/empty change returns False."""
        assert derive_future_talent("Always/Most of the Time", None) is False
        assert derive_future_talent("Always/Most of the Time", "") is False

    def test_both_null_returns_false(self):
        """Both None/empty returns False (not None)."""
        assert derive_future_talent(None, None) is False
        assert derive_future_talent("", "") is False

    def test_case_insensitive(self):
        """Function handles case variations."""
        assert derive_future_talent(
            "ALWAYS/MOST OF THE TIME", "always/most of the time"
        ) is True


class TestDetectSpreadsheetType:
    """Tests for detect_spreadsheet_type()."""

    def test_bonus_headers_detected_as_bonus(self):
        """Headers with bonus markers detected as bonus."""
        headers = [
            "Associate", "Associate ID", "Bonus Target - Local Currency",
            "Annual Bonus Target Percent", "Current Base Pay", "Proposed Bonus Amount"
        ]
        assert detect_spreadsheet_type(headers) == "bonus"

    def test_talent_headers_detected_as_talent(self):
        """Headers with talent markers detected as talent."""
        headers = [
            "Associate", "Associate ID", "Performance: What", "Performance: How",
            "Future Talent: Growth Agility", "Movement Readiness"
        ]
        assert detect_spreadsheet_type(headers) == "talent"

    def test_mixed_headers_uses_higher_score(self):
        """When both markers present, uses higher score."""
        # More talent markers
        headers_talent = [
            "Associate", "Associate ID", "Performance: What", "Performance: How",
            "Future Talent: Growth Agility", "Movement Readiness", "Bonus Target"
        ]
        assert detect_spreadsheet_type(headers_talent) == "talent"

        # More bonus markers
        headers_bonus = [
            "Associate", "Associate ID", "Performance: What",
            "Bonus Target", "Annual Bonus Target Percent", "Current Base Pay"
        ]
        assert detect_spreadsheet_type(headers_bonus) == "bonus"

    def test_empty_headers_defaults_to_bonus(self):
        """Empty/no markers defaults to bonus."""
        assert detect_spreadsheet_type([]) == "bonus"
        assert detect_spreadsheet_type(["Associate", "Associate ID"]) == "bonus"


class TestTalentColumnMapping:
    """Tests for TALENT_COLUMN_MAP and find_talent_column_indices()."""

    def test_column_map_has_required_fields(self):
        """TALENT_COLUMN_MAP includes all required talent fields."""
        # Required fields per spec
        required_fields = [
            'associate_id', 'associate',
            'talent_perf_what', 'talent_perf_how',
            'talent_growth_agility', 'talent_change_agility',
            'talent_movement_readiness',
        ]
        mapped_fields = set(TALENT_COLUMN_MAP.values())
        for field in required_fields:
            assert field in mapped_fields, f"Missing required field: {field}"

    def test_find_indices_exact_match(self):
        """find_talent_column_indices matches exact column names."""
        headers = [
            "Associate ID", "Worker", "Performance: What", "Performance: How",
            "Movement Readiness", "Future Talent: Growth Agility"
        ]
        indices = find_talent_column_indices(headers)

        assert indices['associate_id'] == 0
        assert indices['associate'] == 1
        assert indices['talent_perf_what'] == 2
        assert indices['talent_perf_how'] == 3
        assert indices['talent_movement_readiness'] == 4
        assert indices['talent_growth_agility'] == 5

    def test_find_indices_case_insensitive_fallback(self):
        """find_talent_column_indices falls back to case-insensitive match."""
        headers = [
            "associate id", "WORKER", "performance: what", "PERFORMANCE: HOW"
        ]
        indices = find_talent_column_indices(headers)

        assert indices['associate_id'] == 0
        assert indices['associate'] == 1
        assert indices['talent_perf_what'] == 2
        assert indices['talent_perf_how'] == 3

    def test_find_indices_missing_columns_are_none(self):
        """Missing columns return None, not raise error."""
        headers = ["Associate ID", "Worker"]
        indices = find_talent_column_indices(headers)

        assert indices['associate_id'] == 0
        assert indices['associate'] == 1
        assert indices.get('talent_perf_what') is None
        assert indices.get('talent_movement_readiness') is None

    def test_worker_and_associate_both_map_to_associate(self):
        """Both 'Worker' and 'Associate' columns map to 'associate' field."""
        # Worker column
        headers_worker = ["Associate ID", "Worker"]
        indices_worker = find_talent_column_indices(headers_worker)
        assert indices_worker['associate'] == 1

        # Associate column
        headers_assoc = ["Associate ID", "Associate"]
        indices_assoc = find_talent_column_indices(headers_assoc)
        assert indices_assoc['associate'] == 1


class TestTalentMarkers:
    """Tests for marker constants."""

    def test_talent_markers_match_spec(self):
        """TALENT_MARKERS match Spec §5.1 markers."""
        expected = ['Performance: What', 'Performance: How', 'Future Talent', 'Movement Readiness']
        assert TALENT_MARKERS == expected

    def test_bonus_markers_match_spec(self):
        """BONUS_MARKERS match Spec §5.1 markers."""
        expected = ['Bonus Target', 'Annual Bonus Target Percent', 'Current Base Pay', 'Proposed Bonus Amount']
        assert BONUS_MARKERS == expected
