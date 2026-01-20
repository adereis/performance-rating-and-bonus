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

    def test_talent_matrix_chart_present(self, client, employees_with_talent):
        """Test that 9-box talent matrix chart is present."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # Check for talent matrix chart canvas and title
        assert 'talentMatrixChart' in html
        assert 'Talent Matrix' in html
        # Check for matrix data in JSON
        assert 'talent_matrix' in html
        assert 'future_talent_yes' in html
        assert 'future_talent_no' in html


class TestTalentAnalyticsSuggestedRanges:
    """Test suggested ranges per Spec §7.3."""

    def test_suggested_ranges_displayed(self, client, employees_with_talent):
        """Test that suggested ranges are shown in the table."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # Check for suggested range values from Spec §7.3
        assert '5-15%' in html  # High Impact
        assert '55-70%' in html  # Successful
        assert '15-25%' in html  # Evolving
        assert '2-10%' in html  # Low
        assert '10-20%' in html  # Future Talent

    def test_status_badges_present(self, client, employees_with_talent):
        """Test that status badges are displayed."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # Check for status badge classes
        assert 'status-badge' in html
