"""Tests for talent calibration analytics calculations (Spec §10)."""
import pytest
from models import Employee


@pytest.fixture
def employees_with_talent(app, test_db):
    """Create employees with talent calibration data."""
    SessionLocal, db_path = test_db
    session = SessionLocal()

    # Create employees with varied talent data
    employees = [
        Employee(
            associate_id='EMP001',
            associate='Alice Johnson',
            supervisory_organization='Engineering',
            current_job_profile='Senior Engineer',
            talent_overall_perf='High Impact Performer',
            talent_identified_future=True,
            talent_movement_readiness='Ready Now to be promoted in current role',
            performance_rating_percent=130.0,
        ),
        Employee(
            associate_id='EMP002',
            associate='Bob Smith',
            supervisory_organization='Engineering',
            current_job_profile='Staff Engineer',
            talent_overall_perf='Successful Performer',
            talent_identified_future=False,
            talent_movement_readiness='Continue growing in current role',
            performance_rating_percent=110.0,
        ),
        Employee(
            associate_id='EMP003',
            associate='Charlie Brown',
            supervisory_organization='Engineering',
            current_job_profile='Engineer',
            talent_overall_perf='Successful Performer',
            talent_identified_future=True,
            talent_movement_readiness='Continue growing in current role',
            performance_rating_percent=100.0,
        ),
        Employee(
            associate_id='EMP004',
            associate='Diana Prince',
            supervisory_organization='Product',
            current_job_profile='Product Manager',
            talent_overall_perf='Evolving Performer',
            talent_identified_future=False,
            talent_movement_readiness='Ready for lateral move',
            performance_rating_percent=85.0,
        ),
    ]

    for emp in employees:
        session.add(emp)
    session.commit()
    session.close()

    return employees


class TestTalentAnalyticsDistribution:
    """Test talent distribution calculations in analytics."""

    def test_analytics_with_talent_data(self, client, employees_with_talent):
        """Analytics page includes talent calibration tab when data exists."""
        response = client.get('/analytics')
        assert response.status_code == 200

        html = response.data.decode('utf-8')
        # Check for the combined Calibration Guide card with Talent tab
        assert 'Calibration Guide' in html
        assert 'Talent Calibration' in html
        assert 'talent-calibration-content' in html

    def test_talent_performance_levels_displayed(self, client, employees_with_talent):
        """Test that performance level names are displayed."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # Check for performance level labels
        assert 'High Impact Performer' in html
        assert 'Successful Performer' in html
        assert 'Evolving Performer' in html

    def test_future_talent_count_displayed(self, client, employees_with_talent):
        """Test Future Talent identification is shown."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # Should show Future Talent section
        assert 'Identified as Future Talent' in html

    def test_movement_readiness_displayed(self, client, employees_with_talent):
        """Test Movement Readiness breakdown is shown."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # Should show movement readiness categories
        assert 'Continue growing in current role' in html
        assert 'Movement Readiness Breakdown' in html

    def test_small_team_warning(self, client, employees_with_talent):
        """Test small team warning appears for teams < 10."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # With 4 employees, should show small team warning
        assert 'Small team size' in html


class TestTalentAnalyticsCharts:
    """Test chart data for talent analytics."""

    def test_talent_chart_canvas_present(self, client, employees_with_talent):
        """Test that chart canvas elements are present."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # Check for chart canvas elements
        assert 'talentPerformanceChart' in html
        assert 'movementReadinessChart' in html

    def test_talent_calibration_data_in_json(self, client, employees_with_talent):
        """Test that talent calibration data is properly serialized to JSON."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # Check for JSON data in script
        assert 'talentCalibrationData' in html
        assert 'performance_data' in html
        assert 'movement_data' in html

class TestTalentAnalyticsSuggestedRanges:
    """Test suggested ranges per Spec §7.3."""

    def test_suggested_ranges_displayed(self, client, employees_with_talent):
        """Test that suggested ranges are shown in the table."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # Check for suggested range values based on Gartner benchmarks
        assert '10-20%' in html  # High Impact
        assert '60-80%' in html  # Successful
        assert '5-15%' in html  # Evolving
        assert '2-5%' in html  # Low
        assert '10-20%' in html  # Future Talent

    def test_status_badges_present(self, client, employees_with_talent):
        """Test that status badges are displayed."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # Check for status badge classes
        assert 'status-badge' in html


class TestMovementReadinessIncomplete:
    """Test movement readiness counting for employees without full talent assessment.

    Regression test: Employees marked for promotion (via talent_movement_readiness)
    should be counted even if they haven't completed their What/How assessments
    (which would leave talent_overall_perf as None).
    """

    def test_movement_readiness_counts_employees_without_overall_perf(self, app, client, test_db):
        """Movement readiness should count employees who have movement set but no overall perf."""
        SessionLocal, db_path = test_db
        session = SessionLocal()

        # Create one fully calibrated employee
        calibrated = Employee(
            associate_id='FULL001',
            associate='Fully Calibrated',
            supervisory_organization='Engineering',
            current_job_profile='Engineer',
            talent_perf_what='Meets Expectations',
            talent_perf_how='Meets Expectations',
            talent_overall_perf='Successful Performer',
            talent_movement_readiness='Continue growing in current role',
        )

        # Create employee marked for promotion but without What/How (no overall_perf)
        promotion_pending = Employee(
            associate_id='PROMO001',
            associate='Promotion Pending',
            supervisory_organization='Engineering',
            current_job_profile='Senior Engineer',
            talent_perf_what=None,  # Not yet assessed
            talent_perf_how=None,   # Not yet assessed
            talent_overall_perf=None,  # Can't be derived without What/How
            talent_movement_readiness='Ready Now to be promoted in current role',
        )

        session.add(calibrated)
        session.add(promotion_pending)
        session.commit()
        session.close()

        response = client.get('/analytics')
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # The promotion-ready employee should be counted in movement breakdown
        # Even though they don't have talent_overall_perf
        assert 'Ready Now to be promoted in current role' in html
        # Should show at least 1 in the ready-for-promotion count
        assert '1 employees' in html or '>1<' in html

class TestMovementReadinessNormalization:
    """Test movement readiness value normalization at import time."""

    def test_normalize_workday_promotion_value(self):
        """Workday promotion format is normalized to canonical value."""
        from app import normalize_movement_readiness

        result = normalize_movement_readiness(
            'Ready Now to be promoted in current role (upcoming cycle)'
        )
        assert result == 'Ready Now to be promoted in current role'

    def test_normalize_workday_lateral_value(self):
        """Workday lateral format is normalized to canonical value."""
        from app import normalize_movement_readiness

        result = normalize_movement_readiness(
            'Ready for a lateral move outside of current role'
        )
        assert result == 'Ready for lateral move'

    def test_normalize_continue_growing(self):
        """Continue growing value passes through."""
        from app import normalize_movement_readiness

        result = normalize_movement_readiness('Continue growing in current role')
        assert result == 'Continue growing in current role'

    def test_normalize_none_returns_none(self):
        """None input returns None."""
        from app import normalize_movement_readiness

        assert normalize_movement_readiness(None) is None
        assert normalize_movement_readiness('') is None

    def test_unknown_value_passes_through(self):
        """Unknown values pass through unchanged."""
        from app import normalize_movement_readiness

        result = normalize_movement_readiness('Some unknown Workday value')
        assert result == 'Some unknown Workday value'


class TestTenureParsing:
    """Test tenure string parsing functions."""

    def test_parse_years_and_months(self):
        """Parse '2 years, 3 months' format."""
        from app import parse_tenure_to_months

        assert parse_tenure_to_months('2 years, 3 months') == 27
        assert parse_tenure_to_months('1 year, 6 months') == 18

    def test_parse_years_only(self):
        """Parse '3 years' format."""
        from app import parse_tenure_to_months

        assert parse_tenure_to_months('3 years') == 36
        assert parse_tenure_to_months('1 year') == 12

    def test_parse_months_only(self):
        """Parse '8 months' format."""
        from app import parse_tenure_to_months

        assert parse_tenure_to_months('8 months') == 8
        assert parse_tenure_to_months('11 months') == 11

    def test_parse_none_or_empty(self):
        """None or empty returns None."""
        from app import parse_tenure_to_months

        assert parse_tenure_to_months(None) is None
        assert parse_tenure_to_months('') is None

    def test_parse_unparseable(self):
        """Unparseable string returns None."""
        from app import parse_tenure_to_months

        assert parse_tenure_to_months('N/A') is None
        assert parse_tenure_to_months('unknown') is None


class TestTenureBands:
    """Test tenure band categorization."""

    def test_tenure_bands(self):
        """Test band assignment."""
        from app import get_tenure_band

        assert get_tenure_band(6) == '< 1 year'
        assert get_tenure_band(12) == '1-2 years'
        assert get_tenure_band(18) == '1-2 years'
        assert get_tenure_band(24) == '2-5 years'
        assert get_tenure_band(48) == '2-5 years'
        assert get_tenure_band(60) == '5-10 years'
        assert get_tenure_band(120) == '10+ years'
        assert get_tenure_band(None) == 'Unknown'


class TestTenureAnalyticsRoute:
    """Test tenure analytics in analytics route."""

    def test_analytics_includes_tenure_section(self, app, client, test_db):
        """Analytics page includes tenure section when data is present."""
        SessionLocal, db_path = test_db
        session = SessionLocal()

        # Create employee with tenure data
        emp = Employee(
            associate_id='TEN001',
            associate='Tenure Test',
            supervisory_organization='Engineering',
            current_job_profile='Engineer',
            time_in_job_profile='2 years, 6 months',
            length_of_service='5 years, 3 months',
            performance_rating_percent=110.0,
        )
        session.add(emp)
        session.commit()
        session.close()

        response = client.get('/analytics')
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # Check tenure section is present
        assert 'Tenure &amp; Mobility' in html or 'Tenure & Mobility' in html
        assert 'Time in Current Role' in html
        assert 'Length of Service' in html

