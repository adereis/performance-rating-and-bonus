"""
Tests for employee filtering functionality.
"""
import pytest
from app import has_direct_reports, apply_employee_filters


class TestManagerDetection:
    """Test manager detection logic."""

    def test_has_direct_reports_true(self):
        """Test detecting employee with direct reports."""
        manager = {'Associate ID': 'M001', 'Associate': 'Alice Manager'}
        employees = [
            manager,
            {'Associate ID': 'E001', 'Associate': 'Bob', 'Supervisory Organization': 'Engineering - Alice Manager'},
            {'Associate ID': 'E002', 'Associate': 'Charlie', 'Supervisory Organization': 'Engineering - Alice Manager'},
        ]

        assert has_direct_reports(manager, employees) is True

    def test_has_direct_reports_false(self):
        """Test detecting employee without direct reports."""
        ic = {'Associate ID': 'E001', 'Associate': 'Bob IC'}
        employees = [
            ic,
            {'Associate ID': 'M001', 'Associate': 'Alice Manager', 'Supervisory Organization': 'Engineering'},
            {'Associate ID': 'E002', 'Associate': 'Charlie', 'Supervisory Organization': 'Engineering - Alice Manager'},
        ]

        assert has_direct_reports(ic, employees) is False

    def test_has_direct_reports_partial_name_match(self):
        """Test that partial name matches count (e.g., 'John' appears in 'John Smith' supervisory org)."""
        manager = {'Associate ID': 'M001', 'Associate': 'John Smith'}
        employees = [
            manager,
            {'Associate ID': 'E001', 'Associate': 'Bob', 'Supervisory Organization': 'Engineering - John Smith'},
        ]

        assert has_direct_reports(manager, employees) is True

    def test_has_direct_reports_no_name(self):
        """Test employee with no name."""
        emp = {'Associate ID': 'E001', 'Associate': ''}
        employees = [emp]

        assert has_direct_reports(emp, employees) is False


class TestFilterApplication:
    """Test employee filter application."""

    def test_no_filters_applied(self):
        """Test that no filters returns all employees."""
        employees = [
            {'Associate ID': 'E001', 'Associate': 'Alice', 'Current Job Profile': 'Engineer'},
            {'Associate ID': 'E002', 'Associate': 'Bob', 'Current Job Profile': 'Manager'},
        ]

        filter_params = {
            'exclude_managers': False,
            'exclude_titles': [],
            'exclude_ids': []
        }

        filtered, info = apply_employee_filters(employees, filter_params)

        assert len(filtered) == 2
        assert info['active'] is False
        assert info['hidden_count'] == 0
        assert info['filtered_count'] == 2

    def test_exclude_managers(self):
        """Test excluding employees with direct reports."""
        employees = [
            {'Associate ID': 'M001', 'Associate': 'Alice Manager', 'Current Job Profile': 'Engineering Manager'},
            {'Associate ID': 'E001', 'Associate': 'Bob IC', 'Supervisory Organization': 'Engineering - Alice Manager'},
            {'Associate ID': 'E002', 'Associate': 'Charlie IC', 'Supervisory Organization': 'Engineering - Alice Manager'},
        ]

        filter_params = {
            'exclude_managers': True,
            'exclude_titles': [],
            'exclude_ids': []
        }

        filtered, info = apply_employee_filters(employees, filter_params)

        assert len(filtered) == 2  # Only Bob and Charlie
        assert info['active'] is True
        assert info['hidden_count'] == 1  # Alice hidden
        assert info['filtered_count'] == 2
        assert all(emp['Associate'] in ['Bob IC', 'Charlie IC'] for emp in filtered)

    def test_exclude_by_title(self):
        """Test excluding employees by job title."""
        employees = [
            {'Associate ID': 'E001', 'Associate': 'Alice', 'Current Job Profile': 'Senior Engineer'},
            {'Associate ID': 'E002', 'Associate': 'Bob', 'Current Job Profile': 'Principal Engineer'},
            {'Associate ID': 'E003', 'Associate': 'Charlie', 'Current Job Profile': 'Senior Engineer'},
        ]

        filter_params = {
            'exclude_managers': False,
            'exclude_titles': ['Senior Engineer'],
            'exclude_ids': []
        }

        filtered, info = apply_employee_filters(employees, filter_params)

        assert len(filtered) == 1  # Only Bob
        assert filtered[0]['Associate'] == 'Bob'
        assert info['active'] is True
        assert info['hidden_count'] == 2

    def test_exclude_by_name(self):
        """Test excluding employees by name."""
        employees = [
            {'Associate ID': 'E001', 'Associate': 'Alice'},
            {'Associate ID': 'E002', 'Associate': 'Bob'},
            {'Associate ID': 'E003', 'Associate': 'Charlie'},
        ]

        filter_params = {
            'exclude_managers': False,
            'exclude_titles': [],
            'exclude_ids': ['E001', 'E003']  # Alice and Charlie IDs
        }

        filtered, info = apply_employee_filters(employees, filter_params)

        assert len(filtered) == 1  # Only Bob
        assert filtered[0]['Associate'] == 'Bob'
        assert info['active'] is True
        assert info['hidden_count'] == 2

    def test_combined_filters(self):
        """Test multiple filters combined (additive/OR logic)."""
        employees = [
            {'Associate ID': 'M001', 'Associate': 'Alice Manager', 'Current Job Profile': 'Engineering Manager'},
            {'Associate ID': 'E001', 'Associate': 'Bob IC', 'Current Job Profile': 'Senior Engineer', 'Supervisory Organization': 'Alice Manager'},
            {'Associate ID': 'E002', 'Associate': 'Charlie IC', 'Current Job Profile': 'Principal Engineer', 'Supervisory Organization': 'Alice Manager'},
            {'Associate ID': 'E003', 'Associate': 'Diana IC', 'Current Job Profile': 'Senior Engineer', 'Supervisory Organization': 'Alice Manager'},
        ]

        filter_params = {
            'exclude_managers': True,      # Excludes Alice
            'exclude_titles': ['Principal Engineer'],  # Excludes Charlie
            'exclude_ids': ['E003']  # Excludes Diana IC
        }

        filtered, info = apply_employee_filters(employees, filter_params)

        # Only Bob should remain (Alice is manager, Charlie is Principal, Diana excluded by name)
        assert len(filtered) == 1
        assert filtered[0]['Associate'] == 'Bob IC'
        assert info['active'] is True
        assert info['hidden_count'] == 3

    def test_available_options_from_all_employees(self):
        """Test that available options come from ALL employees, not filtered."""
        employees = [
            {'Associate ID': 'E001', 'Associate': 'Alice', 'Current Job Profile': 'Engineer'},
            {'Associate ID': 'E002', 'Associate': 'Bob', 'Current Job Profile': 'Manager'},
            {'Associate ID': 'E003', 'Associate': 'Charlie', 'Current Job Profile': 'Designer'},
        ]

        filter_params = {
            'exclude_managers': False,
            'exclude_titles': [],
            'exclude_ids': ['E001']  # Filter out Alice
        }

        filtered, info = apply_employee_filters(employees, filter_params)

        # Alice should be filtered out
        assert len(filtered) == 2

        # But Alice should still appear in available_employees
        employee_names = [emp['name'] for emp in info['available_employees']]
        assert 'Alice' in employee_names
        assert 'Bob' in employee_names
        assert 'Charlie' in employee_names

        # All titles should be available
        assert 'Engineer' in info['available_titles']
        assert 'Manager' in info['available_titles']
        assert 'Designer' in info['available_titles']

    def test_filter_info_structure(self):
        """Test that filter_info has correct structure."""
        employees = [
            {'Associate ID': 'E001', 'Associate': 'Alice', 'Current Job Profile': 'Engineer'},
        ]

        filter_params = {
            'exclude_managers': False,
            'exclude_titles': [],
            'exclude_ids': []
        }

        filtered, info = apply_employee_filters(employees, filter_params)

        # Check all required keys are present
        assert 'active' in info
        assert 'total_count' in info
        assert 'filtered_count' in info
        assert 'hidden_count' in info
        assert 'params' in info
        assert 'available_titles' in info
        assert 'available_employees' in info

        # Check types
        assert isinstance(info['active'], bool)
        assert isinstance(info['total_count'], int)
        assert isinstance(info['filtered_count'], int)
        assert isinstance(info['hidden_count'], int)
        assert isinstance(info['params'], dict)
        assert isinstance(info['available_titles'], list)
        assert isinstance(info['available_employees'], list)


class TestFilterIntegration:
    """Test filtering integration with routes."""

    def test_rate_page_with_filters(self, client, populated_db):
        """Test rate page with filter parameters."""
        # Test with manager exclusion
        response = client.get('/rate?exclude_managers=true')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_analytics_with_filters(self, client, populated_db):
        """Test analytics page with filter parameters."""
        response = client.get('/analytics?exclude_managers=true')
        assert response.status_code == 200

    def test_index_with_filters(self, client, populated_db):
        """Test index page with filter parameters."""
        response = client.get('/?exclude_managers=true')
        assert response.status_code == 200
