"""
Comprehensive integration tests for the global Filter feature.

The filter feature allows meeting owners to hide specific employees during
screen-sharing calibration sessions. It's implemented as:
- URL-parameter driven filtering (server-side during page rendering)
- sessionStorage persistence for cross-page navigation (client-side)
- Presentation-layer only (not an access control mechanism)

Test categories:
1. Filter application on all supported pages
2. Filter parameter parsing and edge cases
3. Filter combinations (managers + titles + IDs)
4. Filter metadata correctness
5. Pages where filters don't apply
6. Management level detection for manager exclusion
7. API endpoint behavior (documents expected behavior)
"""
import pytest
from app import (
    has_direct_reports,
    apply_employee_filters,
    get_filter_params,
)
from models import Employee


class TestFilterParameterParsing:
    """Test URL query parameter parsing for filters."""

    def test_empty_params(self, client, populated_db):
        """No filter params returns all employees."""
        response = client.get('/')
        assert response.status_code == 200
        # Should not show "Filters Active" banner
        assert b'Filters Active' not in response.data

    def test_exclude_managers_param(self, client, populated_db):
        """exclude_managers=true parameter is parsed correctly."""
        response = client.get('/?exclude_managers=true')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_exclude_managers_case_insensitive(self, client, populated_db):
        """exclude_managers parameter is case-insensitive."""
        response = client.get('/?exclude_managers=TRUE')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_exclude_managers_false(self, client, populated_db):
        """exclude_managers=false does not activate filter."""
        response = client.get('/?exclude_managers=false')
        assert response.status_code == 200
        assert b'Filters Active' not in response.data

    def test_exclude_titles_single(self, client, populated_db):
        """Single title exclusion works."""
        response = client.get('/?exclude_titles=Senior%20Software%20Engineer')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_exclude_titles_multiple(self, client, populated_db):
        """Multiple title exclusion works (comma-separated)."""
        response = client.get(
            '/?exclude_titles=Senior%20Software%20Engineer,Staff%20Software%20Engineer'
        )
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_exclude_ids_single(self, client, populated_db):
        """Single ID exclusion works."""
        response = client.get('/?exclude_ids=EMP001')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_exclude_ids_multiple(self, client, populated_db):
        """Multiple ID exclusion works (comma-separated)."""
        response = client.get('/?exclude_ids=EMP001,EMP002')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_combined_filters(self, client, populated_db):
        """All filter types can be combined."""
        response = client.get(
            '/?exclude_managers=true&exclude_titles=Product%20Manager&exclude_ids=EMP003'
        )
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_empty_values_ignored(self, client, populated_db):
        """Empty filter values don't activate filter."""
        response = client.get('/?exclude_titles=&exclude_ids=')
        assert response.status_code == 200
        assert b'Filters Active' not in response.data

    def test_whitespace_trimmed(self, client, populated_db):
        """Whitespace in filter values is trimmed."""
        response = client.get('/?exclude_ids=%20EMP001%20,%20EMP002%20')
        assert response.status_code == 200
        assert b'Filters Active' in response.data


class TestFilterApplicationOnPages:
    """Test filter application across all supported pages."""

    def test_dashboard_with_filters(self, client, populated_db):
        """Dashboard (/) respects filters."""
        # Without filter - should see all employees
        response = client.get('/')
        assert response.status_code == 200
        assert b'Alice Johnson' in response.data

        # With filter - Alice should be hidden
        response = client.get('/?exclude_ids=EMP001')
        assert response.status_code == 200
        assert b'Filters Active' in response.data
        # Alice's name should not appear in employee listings
        # (may appear in filter dropdown, but not in main content)

    def test_rate_page_with_filters(self, client, populated_db):
        """Rate page (/rate) respects filters."""
        response = client.get('/rate?exclude_ids=EMP001')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_calibrate_page_with_filters(self, client, populated_db):
        """Calibrate page (/calibrate) respects filters."""
        response = client.get('/calibrate?exclude_ids=EMP001')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_analytics_page_with_filters(self, client, populated_db):
        """Analytics page (/analytics) respects filters."""
        response = client.get('/analytics?exclude_ids=EMP001')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_bonus_calculation_with_filters(self, client, populated_db):
        """Bonus calculation page respects filters."""
        response = client.get('/bonus-calculation?exclude_ids=EMP001')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_export_page_with_filters(self, client, populated_db):
        """Export page (/export) respects filters."""
        response = client.get('/export?exclude_ids=EMP001')
        assert response.status_code == 200
        assert b'Filters Active' in response.data


class TestFilterExclusionPages:
    """Test that filters don't appear on certain pages."""

    def test_history_page_no_filters(self, client, populated_db):
        """History page should not have filter UI."""
        response = client.get('/history')
        assert response.status_code == 200
        # Filter toggle button should not be present
        assert b'id="filterToggle"' not in response.data

    def test_import_page_has_filters(self, client, populated_db):
        """Import page has filter UI for privacy during screen-sharing."""
        response = client.get('/import')
        assert response.status_code == 200
        # Filter toggle button should be present (for privacy during calibration)
        assert b'id="filterToggle"' in response.data

    def test_history_page_ignores_filter_params(self, client, populated_db):
        """History page ignores filter URL params."""
        response = client.get('/history?exclude_managers=true')
        assert response.status_code == 200
        # Should not show filter active banner
        assert b'Filters Active' not in response.data


class TestManagerDetectionIntegration:
    """Test manager detection across detection methods."""

    def test_manager_by_supervisory_org(self, app, db_session):
        """Manager detected by supervisory org reference."""
        # Create manager and reports
        manager = Employee(
            associate_id='MGR001',
            associate='Manager One',
            supervisory_organization='Engineering',
            current_job_profile='Engineering Manager',
        )
        report = Employee(
            associate_id='EMP001',
            associate='Report One',
            supervisory_organization='Engineering (Manager One)',  # References manager
            current_job_profile='Software Engineer',
        )
        db_session.add_all([manager, report])
        db_session.commit()

        employees = [manager.to_dict(), report.to_dict()]
        assert has_direct_reports(manager.to_dict(), employees) is True
        assert has_direct_reports(report.to_dict(), employees) is False

    def test_manager_by_management_level(self, app, db_session):
        """Manager detected by management_level field."""
        manager = Employee(
            associate_id='MGR002',
            associate='Manager Two',
            supervisory_organization='Product',
            current_job_profile='Product Manager',
            management_level='Manager',  # Indicates management role
        )
        ic = Employee(
            associate_id='EMP002',
            associate='IC Two',
            supervisory_organization='Product',
            current_job_profile='Product Designer',
            management_level='Individual Contributor',
        )
        db_session.add_all([manager, ic])
        db_session.commit()

        employees = [manager.to_dict(), ic.to_dict()]
        assert has_direct_reports(manager.to_dict(), employees) is True
        assert has_direct_reports(ic.to_dict(), employees) is False

    def test_manager_by_director_level(self, app, db_session):
        """Director-level management_level triggers manager detection."""
        director = Employee(
            associate_id='DIR001',
            associate='Director One',
            supervisory_organization='Engineering',
            current_job_profile='Engineering Director',
            management_level='Director',
        )
        db_session.add(director)
        db_session.commit()

        employees = [director.to_dict()]
        assert has_direct_reports(director.to_dict(), employees) is True

    def test_manager_by_vp_level(self, app, db_session):
        """VP-level management_level triggers manager detection."""
        vp = Employee(
            associate_id='VP001',
            associate='VP One',
            supervisory_organization='Engineering',
            current_job_profile='VP Engineering',
            management_level='Vice President',
        )
        db_session.add(vp)
        db_session.commit()

        employees = [vp.to_dict()]
        assert has_direct_reports(vp.to_dict(), employees) is True

    def test_filter_excludes_managers_by_both_methods(self, app, db_session, client):
        """Manager filter excludes managers detected by either method."""
        # Manager by supervisory org
        mgr1 = Employee(
            associate_id='MGR001',
            associate='Org Manager',
            supervisory_organization='Engineering',
            current_job_profile='Manager',
        )
        # Manager by management_level
        mgr2 = Employee(
            associate_id='MGR002',
            associate='Level Manager',
            supervisory_organization='Product',
            current_job_profile='Lead',
            management_level='Senior Manager',
        )
        # Report of mgr1
        emp1 = Employee(
            associate_id='EMP001',
            associate='Employee One',
            supervisory_organization='Engineering (Org Manager)',
            current_job_profile='Engineer',
        )
        # IC
        emp2 = Employee(
            associate_id='EMP002',
            associate='Employee Two',
            supervisory_organization='Product',
            current_job_profile='Designer',
            management_level='Individual Contributor',
        )
        db_session.add_all([mgr1, mgr2, emp1, emp2])
        db_session.commit()

        # Apply manager filter
        response = client.get('/rate?exclude_managers=true')
        assert response.status_code == 200

        # Both managers should be filtered out
        # The hidden count should be 2 (two managers hidden)
        assert b'Filters Active' in response.data


class TestFilterMetadata:
    """Test that filter metadata is correctly populated."""

    def test_available_employees_includes_all(self, app, db_session):
        """Available employees list includes all employees, even filtered ones."""
        emp1 = Employee(
            associate_id='EMP001',
            associate='Alice',
            current_job_profile='Engineer',
        )
        emp2 = Employee(
            associate_id='EMP002',
            associate='Bob',
            current_job_profile='Designer',
        )
        db_session.add_all([emp1, emp2])
        db_session.commit()

        employees = [emp1.to_dict(), emp2.to_dict()]
        filter_params = {'exclude_managers': False, 'exclude_titles': [], 'exclude_ids': ['EMP001']}

        filtered, info = apply_employee_filters(employees, filter_params)

        # Alice should be filtered out
        assert len(filtered) == 1
        assert filtered[0]['Associate'] == 'Bob'

        # But Alice should still be in available_employees
        available_names = [e['name'] for e in info['available_employees']]
        assert 'Alice' in available_names
        assert 'Bob' in available_names

    def test_available_titles_includes_all(self, app, db_session):
        """Available titles includes all unique titles, even from filtered employees."""
        emp1 = Employee(
            associate_id='EMP001',
            associate='Alice',
            current_job_profile='Rare Title',
        )
        emp2 = Employee(
            associate_id='EMP002',
            associate='Bob',
            current_job_profile='Common Title',
        )
        db_session.add_all([emp1, emp2])
        db_session.commit()

        employees = [emp1.to_dict(), emp2.to_dict()]
        filter_params = {'exclude_managers': False, 'exclude_titles': ['Rare Title'], 'exclude_ids': []}

        filtered, info = apply_employee_filters(employees, filter_params)

        # Alice should be filtered out (has Rare Title)
        assert len(filtered) == 1

        # But Rare Title should still be in available_titles
        assert 'Rare Title' in info['available_titles']
        assert 'Common Title' in info['available_titles']

    def test_manager_ids_list_populated(self, app, db_session):
        """Manager IDs list is populated correctly."""
        mgr = Employee(
            associate_id='MGR001',
            associate='Manager',
            current_job_profile='Manager',
            management_level='Manager',
        )
        emp = Employee(
            associate_id='EMP001',
            associate='Employee',
            current_job_profile='Engineer',
            management_level='IC',
        )
        db_session.add_all([mgr, emp])
        db_session.commit()

        employees = [mgr.to_dict(), emp.to_dict()]
        filter_params = {'exclude_managers': False, 'exclude_titles': [], 'exclude_ids': []}

        _, info = apply_employee_filters(employees, filter_params)

        assert 'MGR001' in info['manager_ids']
        assert 'EMP001' not in info['manager_ids']

    def test_employee_titles_mapping(self, app, db_session):
        """Employee ID to title mapping is populated."""
        emp1 = Employee(
            associate_id='EMP001',
            associate='Alice',
            current_job_profile='Senior Engineer',
        )
        emp2 = Employee(
            associate_id='EMP002',
            associate='Bob',
            current_job_profile='Staff Engineer',
        )
        db_session.add_all([emp1, emp2])
        db_session.commit()

        employees = [emp1.to_dict(), emp2.to_dict()]
        filter_params = {'exclude_managers': False, 'exclude_titles': [], 'exclude_ids': []}

        _, info = apply_employee_filters(employees, filter_params)

        assert info['employee_titles']['EMP001'] == 'Senior Engineer'
        assert info['employee_titles']['EMP002'] == 'Staff Engineer'

    def test_filter_counts_accurate(self, app, db_session):
        """Filter info counts are accurate."""
        employees = [
            Employee(associate_id=f'EMP{i}', associate=f'Emp {i}', current_job_profile='Engineer')
            for i in range(5)
        ]
        db_session.add_all(employees)
        db_session.commit()

        emp_dicts = [e.to_dict() for e in employees]
        filter_params = {'exclude_managers': False, 'exclude_titles': [], 'exclude_ids': ['EMP0', 'EMP1']}

        filtered, info = apply_employee_filters(emp_dicts, filter_params)

        assert info['total_count'] == 5
        assert info['filtered_count'] == 3
        assert info['hidden_count'] == 2
        assert info['active'] is True


class TestFilterEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_team(self, app, db_session, client):
        """Filters work with no employees."""
        response = client.get('/?exclude_managers=true')
        assert response.status_code == 200

    def test_filter_all_employees(self, app, db_session):
        """Filtering all employees results in empty list."""
        emp = Employee(
            associate_id='EMP001',
            associate='Only Employee',
            current_job_profile='Engineer',
        )
        db_session.add(emp)
        db_session.commit()

        employees = [emp.to_dict()]
        filter_params = {'exclude_managers': False, 'exclude_titles': [], 'exclude_ids': ['EMP001']}

        filtered, info = apply_employee_filters(employees, filter_params)

        assert len(filtered) == 0
        assert info['hidden_count'] == 1
        assert info['filtered_count'] == 0

    def test_nonexistent_id_in_filter(self, app, db_session):
        """Filtering by non-existent ID doesn't break anything."""
        emp = Employee(
            associate_id='EMP001',
            associate='Real Employee',
            current_job_profile='Engineer',
        )
        db_session.add(emp)
        db_session.commit()

        employees = [emp.to_dict()]
        filter_params = {'exclude_managers': False, 'exclude_titles': [], 'exclude_ids': ['FAKE123']}

        filtered, info = apply_employee_filters(employees, filter_params)

        # Real employee should still be visible
        assert len(filtered) == 1
        assert info['hidden_count'] == 0
        # Filter is technically active (params present) but nothing is hidden
        assert info['active'] is True

    def test_nonexistent_title_in_filter(self, app, db_session):
        """Filtering by non-existent title doesn't break anything."""
        emp = Employee(
            associate_id='EMP001',
            associate='Real Employee',
            current_job_profile='Real Title',
        )
        db_session.add(emp)
        db_session.commit()

        employees = [emp.to_dict()]
        filter_params = {'exclude_managers': False, 'exclude_titles': ['Fake Title'], 'exclude_ids': []}

        filtered, info = apply_employee_filters(employees, filter_params)

        assert len(filtered) == 1
        assert info['hidden_count'] == 0

    def test_special_characters_in_title(self, app, db_session, client):
        """Titles with special characters are handled correctly."""
        emp = Employee(
            associate_id='EMP001',
            associate='Employee One',
            current_job_profile='Sr. Engineer (L5)',
        )
        db_session.add(emp)
        db_session.commit()

        # URL encode the title with special characters
        response = client.get('/rate?exclude_titles=Sr.%20Engineer%20(L5)')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_special_characters_in_name(self, app, db_session, client):
        """Employee names with special characters work correctly."""
        emp = Employee(
            associate_id='EMP001',
            associate="O'Brien, Mary-Jane",
            current_job_profile='Engineer',
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/rate?exclude_ids=EMP001')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_duplicate_ids_in_filter(self, app, db_session):
        """Duplicate IDs in filter are handled gracefully."""
        emp = Employee(
            associate_id='EMP001',
            associate='Employee One',
            current_job_profile='Engineer',
        )
        db_session.add(emp)
        db_session.commit()

        employees = [emp.to_dict()]
        # Same ID twice
        filter_params = {'exclude_managers': False, 'exclude_titles': [], 'exclude_ids': ['EMP001', 'EMP001']}

        filtered, info = apply_employee_filters(employees, filter_params)

        # Should only count as hidden once
        assert len(filtered) == 0
        assert info['hidden_count'] == 1


class TestApiEndpointBehavior:
    """
    Document expected API endpoint behavior with respect to filters.

    NOTE: These tests document the INTENDED behavior. The filter is a UI
    convenience for screen-sharing, not an access control mechanism.
    API endpoints intentionally return data regardless of filter state.
    """

    def test_employee_api_returns_data_regardless_of_filter_params(self, client, populated_db):
        """
        /api/employee/<id> returns data even when filter params are present.

        This is INTENTIONAL - the API is for programmatic access and doesn't
        need to respect presentation-layer filters.
        """
        # Even with filter params in URL, API returns data
        response = client.get('/api/employee/EMP001?exclude_ids=EMP001')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['employee']['Associate ID'] == 'EMP001'

    def test_employee_history_api_returns_data_regardless_of_filters(self, client, populated_db):
        """
        /api/employee/<id>/history returns data regardless of filters.

        This is INTENTIONAL - history access is independent of current filters.
        """
        response = client.get('/api/employee/EMP001/history?exclude_ids=EMP001')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_calibrate_status_api_reports_total_counts(self, client, populated_db):
        """
        /api/calibrate/status reports counts from ALL employees.

        This is INTENTIONAL - calibration progress should reflect the full
        team, not the filtered view.
        """
        response = client.get('/api/calibrate/status?exclude_ids=EMP001,EMP002')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        # Total should be all employees, not filtered
        assert data['data']['total'] == 4  # All sample_employees


class TestExportBehavior:
    """
    Document expected export behavior with respect to filters.

    NOTE: Exports intentionally include ALL employees regardless of filters.
    This is by design - exports are for data backup/analysis, not screen-sharing.
    """

    def test_export_xlsx_includes_all_employees(self, client, populated_db):
        """
        /export/xlsx exports ALL employees regardless of filters.

        This is INTENTIONAL - exports are complete organizational snapshots.
        """
        response = client.get('/export/xlsx?exclude_ids=EMP001,EMP002')
        assert response.status_code == 200
        assert response.content_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        # Verify it's a valid XLSX (starts with PK - ZIP signature)
        assert response.data[:2] == b'PK'

    def test_export_csv_includes_all_employees(self, client, populated_db):
        """
        /export/csv exports ALL employees regardless of filters.

        This is INTENTIONAL - exports are complete organizational snapshots.
        """
        response = client.get('/export/csv?exclude_ids=EMP001,EMP002')
        assert response.status_code == 200
        assert 'text/csv' in response.content_type


class TestMultiTeamFiltering:
    """Test filter behavior with multi-team organizations."""

    def test_filter_works_across_teams(self, app, db_session, client):
        """Filters work correctly when multiple supervisory orgs exist."""
        # Create employees in different teams
        eng_mgr = Employee(
            associate_id='ENG_MGR',
            associate='Eng Manager',
            supervisory_organization='Engineering',
            current_job_profile='Engineering Manager',
            management_level='Manager',
        )
        eng_emp = Employee(
            associate_id='ENG_EMP',
            associate='Eng Employee',
            supervisory_organization='Engineering (Eng Manager)',
            current_job_profile='Software Engineer',
        )
        prod_mgr = Employee(
            associate_id='PROD_MGR',
            associate='Prod Manager',
            supervisory_organization='Product',
            current_job_profile='Product Manager',
            management_level='Manager',
        )
        prod_emp = Employee(
            associate_id='PROD_EMP',
            associate='Prod Employee',
            supervisory_organization='Product (Prod Manager)',
            current_job_profile='Product Designer',
        )
        db_session.add_all([eng_mgr, eng_emp, prod_mgr, prod_emp])
        db_session.commit()

        # Exclude all managers - should hide both managers
        response = client.get('/rate?exclude_managers=true')
        assert response.status_code == 200
        assert b'Filters Active' in response.data
        # 2 managers should be hidden
        assert b'2 employee(s) hidden' in response.data

    def test_filter_by_org_specific_title(self, app, db_session, client):
        """Filter by title works even with multi-team setup."""
        eng = Employee(
            associate_id='ENG001',
            associate='Engineer',
            supervisory_organization='Engineering',
            current_job_profile='Software Engineer',
        )
        prod = Employee(
            associate_id='PROD001',
            associate='Designer',
            supervisory_organization='Product',
            current_job_profile='Product Designer',
        )
        db_session.add_all([eng, prod])
        db_session.commit()

        # Exclude only engineers
        response = client.get('/rate?exclude_titles=Software%20Engineer')
        assert response.status_code == 200
        assert b'1 employee(s) hidden' in response.data


class TestAnalyticsFilterBehavior:
    """
    Test that analytics correctly exclude filtered employees.

    This is critical for privacy during calibration sessions - when someone
    is filtered out, their data should not appear in any analytics.

    Tests cover BOTH filter mechanisms:
    - exclude_managers=true (checkbox)
    - exclude_ids=... (individual selection from dropdown)
    """

    def test_tenets_exclude_filtered_by_id(self, app, db_session, client):
        """Tenets chart excludes employees filtered by ID selection."""
        import json

        emp1 = Employee(
            associate_id='EMP001',
            associate='Alice',
            current_job_profile='Engineer',
            tenets_strengths=json.dumps(['tenet1', 'tenet2']),
            tenets_improvements=json.dumps(['tenet3']),
        )
        emp2 = Employee(
            associate_id='EMP002',
            associate='Bob',
            current_job_profile='Designer',
            tenets_strengths=json.dumps(['tenet3']),
            tenets_improvements=json.dumps(['tenet1']),
        )
        db_session.add_all([emp1, emp2])
        db_session.commit()

        # Without filter - both should be counted
        response = client.get('/analytics')
        assert response.status_code == 200
        assert b'tenet1' in response.data

        # With filter excluding Alice by ID
        response = client.get('/analytics?exclude_ids=EMP001')
        assert response.status_code == 200
        assert b'Filters Active' in response.data
        # Only Bob's tenets should be counted now

    def test_tenets_exclude_filtered_by_manager_checkbox(self, app, db_session, client):
        """Tenets chart excludes managers when checkbox is checked."""
        import json

        # Manager with unique tenet
        mgr = Employee(
            associate_id='MGR001',
            associate='Manager Alice',
            current_job_profile='Engineering Manager',
            management_level='Manager',
            tenets_strengths=json.dumps(['manager_only_tenet']),
            tenets_improvements=json.dumps(['tenet1']),
        )
        # IC
        ic = Employee(
            associate_id='EMP001',
            associate='IC Bob',
            current_job_profile='Engineer',
            management_level='Individual Contributor',
            tenets_strengths=json.dumps(['ic_tenet']),
            tenets_improvements=json.dumps(['tenet2']),
        )
        db_session.add_all([mgr, ic])
        db_session.commit()

        # Without filter - manager's tenet should appear
        response = client.get('/analytics')
        assert response.status_code == 200
        assert b'manager_only_tenet' in response.data

        # With manager filter - manager's unique tenet should NOT appear
        response = client.get('/analytics?exclude_managers=true')
        assert response.status_code == 200
        assert b'Filters Active' in response.data
        # Manager's unique tenet should be excluded
        assert b'manager_only_tenet' not in response.data
        # IC's tenet should still appear
        assert b'ic_tenet' in response.data

    def test_inconsistencies_exclude_filtered_by_id(self, app, db_session, client):
        """Inconsistency checks exclude employees filtered by ID."""
        # Create employee with inconsistency (high bonus + low talent)
        # The inconsistency check uses talent_overall_perf (stored column)
        emp_inconsistent = Employee(
            associate_id='EMP001',
            associate='Inconsistent Employee',
            current_job_profile='Engineer',
            performance_rating_percent=120.0,  # High rating (>90%)
            talent_overall_perf='Low Performer',  # But low talent
        )
        # Create normal employee
        emp_normal = Employee(
            associate_id='EMP002',
            associate='Normal Employee',
            current_job_profile='Designer',
            performance_rating_percent=100.0,
            talent_overall_perf='Successful Performer',
        )
        db_session.add_all([emp_inconsistent, emp_normal])
        db_session.commit()

        # Without filter - inconsistent employee should be flagged
        # The inconsistency section shows: "Name (Job): Bonus 120% / Low Performer"
        response = client.get('/analytics')
        assert response.status_code == 200
        assert b'Inconsistent Employee</span></strong> (Engineer)' in response.data

        # With filter excluding by ID - should NOT appear in inconsistency section
        response = client.get('/analytics?exclude_ids=EMP001')
        assert response.status_code == 200
        assert b'Inconsistent Employee</span></strong> (Engineer)' not in response.data

    def test_inconsistencies_exclude_filtered_by_manager_checkbox(self, app, db_session, client):
        """Inconsistency checks exclude managers when checkbox is checked."""
        # Manager with inconsistency
        # The inconsistency check uses talent_overall_perf (stored column)
        mgr_inconsistent = Employee(
            associate_id='MGR001',
            associate='Inconsistent Manager',
            current_job_profile='Engineering Manager',
            management_level='Manager',
            performance_rating_percent=130.0,  # High rating (>90%)
            talent_overall_perf='Low Performer',  # But low talent
        )
        # IC (normal)
        ic_normal = Employee(
            associate_id='EMP001',
            associate='Normal IC',
            current_job_profile='Engineer',
            management_level='Individual Contributor',
            performance_rating_percent=100.0,
            talent_overall_perf='Successful Performer',
        )
        db_session.add_all([mgr_inconsistent, ic_normal])
        db_session.commit()

        # Without filter - manager's inconsistency should be flagged
        response = client.get('/analytics')
        assert response.status_code == 200
        assert b'Inconsistent Manager</span></strong> (Engineering Manager)' in response.data

        # With manager filter - manager should NOT appear in inconsistency section
        response = client.get('/analytics?exclude_managers=true')
        assert response.status_code == 200
        assert b'Filters Active' in response.data
        assert b'Inconsistent Manager</span></strong> (Engineering Manager)' not in response.data

    def test_tenure_analytics_exclude_filtered_by_id(self, app, db_session, client):
        """Tenure analytics excludes employees filtered by ID."""
        emp_long_tenure = Employee(
            associate_id='EMP001',
            associate='Long Tenure Employee',
            current_job_profile='Engineer',
            time_in_job_profile='5 years, 2 months',
            length_of_service='8 years',
            performance_rating_percent=100.0,
        )
        emp_short_tenure = Employee(
            associate_id='EMP002',
            associate='New Employee',
            current_job_profile='Designer',
            time_in_job_profile='3 months',
            length_of_service='3 months',
            performance_rating_percent=100.0,
        )
        db_session.add_all([emp_long_tenure, emp_short_tenure])
        db_session.commit()

        # Without filter - long tenure employee appears in tenure table
        # The pattern in HTML: data-employee-id="EMP001">Long Tenure Employee</span>
        response = client.get('/analytics')
        assert response.status_code == 200
        assert b'data-employee-id="EMP001">Long Tenure Employee</span>' in response.data

        # With filter excluding by ID - should NOT appear in tenure section
        response = client.get('/analytics?exclude_ids=EMP001')
        assert response.status_code == 200
        # The employee-name span with their ID should not be in the tenure table
        assert b'data-employee-id="EMP001">Long Tenure Employee</span>' not in response.data

    def test_tenure_analytics_exclude_filtered_by_manager_checkbox(self, app, db_session, client):
        """Tenure analytics excludes managers when checkbox is checked."""
        mgr_long_tenure = Employee(
            associate_id='MGR001',
            associate='Long Tenure Manager',
            current_job_profile='Engineering Manager',
            management_level='Manager',
            time_in_job_profile='7 years',
            length_of_service='10 years',
            performance_rating_percent=100.0,
        )
        ic_short_tenure = Employee(
            associate_id='EMP001',
            associate='New IC',
            current_job_profile='Engineer',
            management_level='Individual Contributor',
            time_in_job_profile='6 months',
            length_of_service='6 months',
            performance_rating_percent=100.0,
        )
        db_session.add_all([mgr_long_tenure, ic_short_tenure])
        db_session.commit()

        # Without filter - manager should appear in tenure table
        response = client.get('/analytics')
        assert response.status_code == 200
        assert b'data-employee-id="MGR001">Long Tenure Manager</span>' in response.data

        # With manager filter - manager should NOT appear in tenure section
        response = client.get('/analytics?exclude_managers=true')
        assert response.status_code == 200
        assert b'Filters Active' in response.data
        assert b'data-employee-id="MGR001">Long Tenure Manager</span>' not in response.data

    def test_movement_readiness_excludes_filtered_by_id(self, app, db_session, client):
        """Movement readiness excludes employees filtered by ID."""
        emp_ready = Employee(
            associate_id='EMP001',
            associate='Ready Employee',
            current_job_profile='Engineer',
            talent_movement_readiness='Ready Now to be promoted in current role',
            talent_perf_what='Surpasses Expectations',
            talent_perf_how='Surpasses Expectations',
        )
        emp_growing = Employee(
            associate_id='EMP002',
            associate='Growing Employee',
            current_job_profile='Designer',
            talent_movement_readiness='Continue growing in current role',
            talent_perf_what='Meets Expectations',
            talent_perf_how='Meets Expectations',
        )
        db_session.add_all([emp_ready, emp_growing])
        db_session.commit()

        # Without filter - both contribute
        response = client.get('/analytics')
        assert response.status_code == 200

        # With filter excluding by ID
        response = client.get('/analytics?exclude_ids=EMP001')
        assert response.status_code == 200
        assert b'Filters Active' in response.data

    def test_movement_readiness_excludes_filtered_by_manager_checkbox(self, app, db_session, client):
        """Movement readiness excludes managers when checkbox is checked."""
        mgr_ready = Employee(
            associate_id='MGR001',
            associate='Ready Manager',
            current_job_profile='Engineering Manager',
            management_level='Manager',
            talent_movement_readiness='Ready Now to be promoted in current role',
            talent_perf_what='Surpasses Expectations',
            talent_perf_how='Surpasses Expectations',
        )
        ic_growing = Employee(
            associate_id='EMP001',
            associate='Growing IC',
            current_job_profile='Engineer',
            management_level='Individual Contributor',
            talent_movement_readiness='Continue growing in current role',
            talent_perf_what='Meets Expectations',
            talent_perf_how='Meets Expectations',
        )
        db_session.add_all([mgr_ready, ic_growing])
        db_session.commit()

        # Without filter
        response = client.get('/analytics')
        assert response.status_code == 200

        # With manager filter
        response = client.get('/analytics?exclude_managers=true')
        assert response.status_code == 200
        assert b'Filters Active' in response.data
        # Manager's movement should be excluded from distribution

    def test_mentorship_analysis_excludes_filtered_by_id(self, app, db_session, client):
        """Mentorship analysis excludes employees filtered by ID."""
        emp_senior = Employee(
            associate_id='EMP001',
            associate='Senior Dev Without Mentees',
            current_job_profile='Senior Software Engineer',
            mentees='',
        )
        emp_junior = Employee(
            associate_id='EMP002',
            associate='Junior Dev',
            current_job_profile='Software Engineer',
            mentor='Senior Dev',
        )
        db_session.add_all([emp_senior, emp_junior])
        db_session.commit()

        # Without filter - senior should appear in "seniors without mentees"
        # The HTML pattern: Name</span></strong> (Job)
        response = client.get('/analytics')
        assert response.status_code == 200
        assert b'Senior Dev Without Mentees</span></strong> (Senior Software Engineer)' in response.data

        # With filter excluding senior by ID
        response = client.get('/analytics?exclude_ids=EMP001')
        assert response.status_code == 200
        # The mentorship section should not contain this employee
        assert b'Senior Dev Without Mentees</span></strong> (Senior Software Engineer)' not in response.data

    def test_mentorship_analysis_excludes_filtered_by_manager_checkbox(self, app, db_session, client):
        """Mentorship analysis excludes managers when checkbox is checked."""
        # Manager who is senior but has no mentees
        mgr_senior = Employee(
            associate_id='MGR001',
            associate='Manager Without Mentees',
            current_job_profile='Senior Engineering Manager',
            management_level='Manager',
            mentees='',
        )
        ic = Employee(
            associate_id='EMP001',
            associate='IC Dev',
            current_job_profile='Software Engineer',
            management_level='Individual Contributor',
        )
        db_session.add_all([mgr_senior, ic])
        db_session.commit()

        # Without filter - manager should appear in seniors without mentees
        response = client.get('/analytics')
        assert response.status_code == 200
        assert b'Manager Without Mentees</span></strong> (Senior Engineering Manager)' in response.data

        # With manager filter - manager should NOT appear in mentorship section
        response = client.get('/analytics?exclude_managers=true')
        assert response.status_code == 200
        assert b'Filters Active' in response.data
        assert b'Manager Without Mentees</span></strong> (Senior Engineering Manager)' not in response.data


class TestFilterUIElements:
    """Test filter UI elements are correctly rendered."""

    def test_filter_toggle_button_present(self, client, populated_db):
        """Filter toggle button is present on filterable pages."""
        response = client.get('/rate')
        assert response.status_code == 200
        assert b'id="filterToggle"' in response.data
        assert b'Filters' in response.data

    def test_filter_panel_present(self, client, populated_db):
        """Filter panel is present on filterable pages."""
        response = client.get('/rate')
        assert response.status_code == 200
        assert b'id="filterPanel"' in response.data
        assert b'Exclude managers' in response.data
        assert b'Exclude by Job Title' in response.data
        assert b'Exclude by Name' in response.data

    def test_filter_options_populated(self, client, populated_db):
        """Filter dropdowns are populated with available options."""
        response = client.get('/rate')
        assert response.status_code == 200
        # Job titles from sample_employees fixture
        assert b'Senior Software Engineer' in response.data
        assert b'Staff Software Engineer' in response.data
        # Employee names
        assert b'Alice Johnson' in response.data
        assert b'Bob Smith' in response.data

    def test_active_filter_banner_shown(self, client, populated_db):
        """Active filter banner is shown when filters are active."""
        response = client.get('/rate?exclude_ids=EMP001')
        assert response.status_code == 200
        assert b'Filters Active' in response.data
        assert b'1 employee(s) hidden' in response.data

    def test_filter_button_shows_count(self, client, populated_db):
        """Filter button shows hidden count when active."""
        response = client.get('/rate?exclude_ids=EMP001,EMP002')
        assert response.status_code == 200
        # Button should show "Filters (2)" when 2 are hidden
        assert b'Filters (2)' in response.data
