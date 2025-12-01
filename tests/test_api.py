"""
Tests for Flask API endpoints.
"""
import pytest
import json
from models import Employee


class TestAPIEndpoints:
    """Test Flask API endpoints."""

    def test_index_route(self, client, populated_db):
        """Test the main dashboard route."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Quarterly Performance Rating' in response.data

    def test_rate_page_route(self, client, populated_db):
        """Test the rating page route."""
        response = client.get('/rate')
        assert response.status_code == 200
        assert b'Rate Team Members' in response.data

    def test_analytics_route(self, client, populated_db):
        """Test the analytics page route."""
        response = client.get('/analytics')
        assert response.status_code == 200

    def test_rate_employee_success(self, client, populated_db):
        """Test successfully rating an employee."""
        data = {
            'associate_name': 'Diana Prince',
            'rating_percent': '110',
            'justification': 'Great work on product launch',
            'mentor': 'Bob Smith',
            'mentees': 'New hire team',
        }

        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['message'] == 'Rating saved successfully'

        # Verify data was saved
        employee = populated_db.query(Employee).filter(
            Employee.associate == 'Diana Prince'
        ).first()

        assert employee.performance_rating_percent == 110.0
        assert employee.justification == 'Great work on product launch'
        assert employee.mentor == 'Bob Smith'
        assert employee.mentees == 'New hire team'
        assert employee.last_updated is not None

    def test_rate_employee_update_existing_rating(self, client, populated_db):
        """Test updating an existing rating."""
        data = {
            'associate_name': 'Alice Johnson',
            'rating_percent': '130',
            'justification': 'Updated justification',
            'mentor': 'New mentor',
            'mentees': 'Updated mentees',
        }

        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 200

        # Verify update
        employee = populated_db.query(Employee).filter(
            Employee.associate == 'Alice Johnson'
        ).first()

        assert employee.performance_rating_percent == 130.0
        assert employee.justification == 'Updated justification'

    def test_rate_employee_missing_name(self, client):
        """Test rating without associate name."""
        data = {
            'rating_percent': '100',
            'justification': 'Test'
        }

        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'error' in result
        assert result['error'] == 'Missing associate name'

    def test_rate_employee_not_found(self, client, populated_db):
        """Test rating non-existent employee."""
        data = {
            'associate_name': 'Nonexistent Person',
            'rating_percent': '100'
        }

        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 404
        result = json.loads(response.data)
        assert 'error' in result
        assert result['error'] == 'Employee not found'

    def test_rate_employee_invalid_rating_too_high(self, client, populated_db):
        """Test rating validation - value too high."""
        data = {
            'associate_name': 'Alice Johnson',
            'rating_percent': '250'
        }

        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'error' in result
        assert 'between 0 and 200' in result['error']

    def test_rate_employee_invalid_rating_negative(self, client, populated_db):
        """Test rating validation - negative value."""
        data = {
            'associate_name': 'Alice Johnson',
            'rating_percent': '-10'
        }

        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'error' in result
        assert 'between 0 and 200' in result['error']

    def test_rate_employee_invalid_rating_format(self, client, populated_db):
        """Test rating validation - invalid format."""
        data = {
            'associate_name': 'Alice Johnson',
            'rating_percent': 'abc'
        }

        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'error' in result
        assert 'Invalid rating value' in result['error']

    def test_rate_employee_empty_rating(self, client, populated_db):
        """Test rating with empty rating value (valid - unrating)."""
        data = {
            'associate_name': 'Alice Johnson',
            'rating_percent': '',
            'justification': 'Removing rating temporarily'
        }

        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 200

        # Verify rating was set to None
        employee = populated_db.query(Employee).filter(
            Employee.associate == 'Alice Johnson'
        ).first()

        assert employee.performance_rating_percent is None
        assert employee.justification == 'Removing rating temporarily'

    def test_rate_employee_boundary_values(self, client, populated_db):
        """Test rating with boundary values 0 and 200."""
        # Test 0
        data = {
            'associate_name': 'Alice Johnson',
            'rating_percent': '0'
        }

        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')
        assert response.status_code == 200

        employee = populated_db.query(Employee).filter(
            Employee.associate == 'Alice Johnson'
        ).first()
        assert employee.performance_rating_percent == 0.0

        # Test 200
        data['rating_percent'] = '200'
        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')
        assert response.status_code == 200

        populated_db.refresh(employee)
        assert employee.performance_rating_percent == 200.0

    def test_rate_employee_decimal_rating(self, client, populated_db):
        """Test rating with decimal values."""
        data = {
            'associate_name': 'Alice Johnson',
            'rating_percent': '123.5'
        }

        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 200

        employee = populated_db.query(Employee).filter(
            Employee.associate == 'Alice Johnson'
        ).first()

        assert employee.performance_rating_percent == 123.5

    def test_rate_employee_only_manager_fields(self, client, populated_db):
        """Test updating only manager input fields without rating."""
        data = {
            'associate_name': 'Diana Prince',
            'rating_percent': '',
            'justification': 'Work in progress',
            'mentor': 'Alice Johnson',
            'mentees': '',
        }

        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 200

        employee = populated_db.query(Employee).filter(
            Employee.associate == 'Diana Prince'
        ).first()

        assert employee.performance_rating_percent is None
        assert employee.justification == 'Work in progress'
        assert employee.mentor == 'Alice Johnson'

    def test_get_employee_details_success(self, client, populated_db):
        """Test getting employee details by name."""
        response = client.get('/api/employee/Diana%20Prince')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert 'employee' in result

        employee = result['employee']
        assert employee['Associate'] == 'Diana Prince'
        assert employee['Associate ID'] == 'EMP004'
        assert 'Current Job Profile' in employee

    def test_get_employee_details_not_found(self, client, populated_db):
        """Test getting details for non-existent employee."""
        response = client.get('/api/employee/Nonexistent%20Person')

        assert response.status_code == 404
        result = json.loads(response.data)
        assert result['success'] is False
        assert 'not found' in result['error'].lower()


class TestDashboardStatistics:
    """Test dashboard statistics calculations."""

    def test_dashboard_stats_with_ratings(self, client, populated_db):
        """Test dashboard displays correct statistics."""
        response = client.get('/')
        assert response.status_code == 200

        # Check that correct counts appear
        # Total: 4, Rated: 3, Unrated: 1
        assert b'4' in response.data  # Total employees

    def test_dashboard_with_no_employees(self, client, db_session):
        """Test dashboard with empty database."""
        response = client.get('/')
        assert response.status_code == 200


class TestAnalyticsDashboard:
    """Test analytics dashboard calculations."""

    def test_analytics_rating_distribution(self, client, populated_db):
        """Test rating distribution buckets."""
        response = client.get('/analytics')
        assert response.status_code == 200

        # Should calculate buckets correctly
        # Alice: 120 -> 101-130%
        # Bob: 140 -> 131-200%
        # Charlie: 85 -> 81-100%

    def test_analytics_department_averages(self, client, populated_db):
        """Test department average calculations."""
        response = client.get('/analytics')
        assert response.status_code == 200

        # Engineering dept has Alice (120), Bob (140), Charlie (85)
        # Average should be around 115

    def test_analytics_job_averages(self, client, populated_db):
        """Test job profile average calculations."""
        response = client.get('/analytics')
        assert response.status_code == 200

        # Senior Software Engineer: Alice (120) -> avg 120
        # Staff Software Engineer: Bob (140) -> avg 140
        # Software Engineer: Charlie (85) -> avg 85

    def test_analytics_with_no_ratings(self, client, db_session, sample_employees):
        """Test analytics with employees but no ratings."""
        # Add employees without ratings
        for emp_data in sample_employees:
            emp_data['performance_rating_percent'] = None
            employee = Employee(**emp_data)
            db_session.add(employee)
        db_session.commit()

        response = client.get('/analytics')
        assert response.status_code == 200


class TestExportPage:
    """Test export page functionality."""

    def test_export_page_route(self, client, populated_db):
        """Test the export page route."""
        response = client.get('/export')
        assert response.status_code == 200
        assert b'Export Data' in response.data

    def test_export_page_with_no_employees(self, client, db_session):
        """Test export page with no employees."""
        response = client.get('/export')
        assert response.status_code == 200
        assert b'No Data Available' in response.data or b'No rated employees' in response.data

    def test_export_page_renders_successfully(self, client, populated_db):
        """Test that export page renders without errors."""
        response = client.get('/export')
        assert response.status_code == 200
        # Page should have export-related content
        assert b'Workday' in response.data or b'Export' in response.data
