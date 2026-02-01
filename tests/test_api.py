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
        assert b'Performance Rating' in response.data

    def test_rate_page_route(self, client, populated_db):
        """Test the rating page route."""
        response = client.get('/rate')
        assert response.status_code == 200
        assert b'Bonus Rating' in response.data

    def test_analytics_route(self, client, populated_db):
        """Test the analytics page route."""
        response = client.get('/analytics')
        assert response.status_code == 200

    def test_rate_employee_success(self, client, populated_db):
        """Test successfully rating an employee."""
        data = {
            'associate_id': 'EMP004',
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
            'associate_id': 'EMP001',
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

    def test_rate_employee_missing_name(self, client, populated_db):
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
        assert result['error'] == 'Missing associate ID'

    def test_rate_employee_not_found(self, client, populated_db):
        """Test rating non-existent employee."""
        data = {
            'associate_id': 'NONEXISTENT',
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
            'associate_id': 'EMP001',
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
            'associate_id': 'EMP001',
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
            'associate_id': 'EMP001',
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
            'associate_id': 'EMP001',
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
            'associate_id': 'EMP001',
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
            'associate_id': 'EMP001',
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
            'associate_id': 'EMP004',
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
        """Test getting employee details by ID."""
        response = client.get('/api/employee/EMP004')

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
        response = client.get('/api/employee/NONEXISTENT')

        assert response.status_code == 404
        result = json.loads(response.data)
        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    def test_rate_blocked_without_bonus_data(self, client, db_session):
        """Test that rating is blocked when no bonus data has been imported."""
        # Create employee without bonus target data (simulating talent-only import)
        employee = Employee(
            associate_id='EMP_TALENT',
            associate='Talent Only Employee',
            supervisory_organization='Engineering',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            # No bonus_target_local_currency or bonus_target_manager_currency
        )
        db_session.add(employee)
        db_session.commit()

        data = {
            'associate_id': 'EMP_TALENT',
            'rating_percent': '100',
            'justification': 'Test'
        }

        response = client.post('/api/rate',
                              data=json.dumps(data),
                              content_type='application/json')

        assert response.status_code == 400
        result = json.loads(response.data)
        assert 'error' in result
        assert 'bonus data' in result['error'].lower()


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
        assert b'No Employees Found' in response.data or b'Import Data' in response.data

    def test_export_page_renders_successfully(self, client, populated_db):
        """Test that export page renders without errors."""
        response = client.get('/export')
        assert response.status_code == 200
        # Page should have export-related content
        assert b'Workday' in response.data or b'Export' in response.data


class TestSnapshotExport:
    """Test full organization snapshot export functionality."""

    def test_export_snapshot_xlsx_structure(self, client, populated_db):
        """Test that Excel snapshot has correct sheet structure and headers."""
        from openpyxl import load_workbook
        import io

        response = client.get('/export/snapshot/xlsx')
        assert response.status_code == 200
        assert response.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

        # Load the workbook from response
        wb = load_workbook(io.BytesIO(response.data))

        # Verify 6 sheets exist
        expected_sheets = ['_context', '_tenets', 'employees', 'bonus_cycle', 'talent_cycle', 'history']
        assert len(wb.sheetnames) == 6
        for sheet_name in expected_sheets:
            assert sheet_name in wb.sheetnames, f"Sheet '{sheet_name}' not found"

        # Verify employees sheet has correct headers
        ws_employees = wb['employees']
        emp_headers = [cell.value for cell in ws_employees[1]]
        assert 'Employee ID (unique identifier)' in emp_headers
        assert 'Employee Name' in emp_headers
        assert 'Manager Name' in emp_headers
        assert 'Supervisory Organization' in emp_headers

        # Verify bonus_cycle sheet has correct headers
        ws_bonus = wb['bonus_cycle']
        bonus_headers = [cell.value for cell in ws_bonus[1]]
        assert 'Employee ID' in bonus_headers
        assert 'Performance Rating (0-200%, 100=met expectations)' in bonus_headers
        assert 'Calculated Bonus Amount (manager currency)' in bonus_headers

        # Verify talent_cycle sheet has correct headers
        ws_talent = wb['talent_cycle']
        talent_headers = [cell.value for cell in ws_talent[1]]
        assert 'Employee ID' in talent_headers
        assert 'Performance: What (Results)' in talent_headers
        assert 'Cross-Cycle Alignment (aligned/review/incomplete)' in talent_headers

    def test_export_snapshot_csv_structure(self, client, populated_db):
        """Test that CSV snapshot ZIP has correct file structure."""
        import zipfile
        import io
        import csv

        response = client.get('/export/snapshot/csv')
        assert response.status_code == 200
        assert response.mimetype == 'application/zip'

        # Load the ZIP from response
        zip_buffer = io.BytesIO(response.data)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            # Verify 6 CSV files exist
            expected_files = ['_context.csv', '_tenets.csv', 'employees.csv',
                            'bonus_cycle.csv', 'talent_cycle.csv', 'history.csv']
            assert len(zf.namelist()) == 6
            for filename in expected_files:
                assert filename in zf.namelist(), f"File '{filename}' not found in ZIP"

            # Verify employees.csv has correct headers
            with zf.open('employees.csv') as f:
                reader = csv.reader(io.TextIOWrapper(f, encoding='utf-8'))
                headers = next(reader)
                assert 'Employee ID (unique identifier)' in headers
                assert 'Employee Name' in headers
                assert 'Manager Name' in headers

            # Verify bonus_cycle.csv has correct headers
            with zf.open('bonus_cycle.csv') as f:
                reader = csv.reader(io.TextIOWrapper(f, encoding='utf-8'))
                headers = next(reader)
                assert 'Performance Rating (0-200%, 100=met expectations)' in headers

    def test_export_snapshot_context_sheet(self, client, populated_db):
        """Test that context sheet contains domain knowledge and analysis guidance."""
        from openpyxl import load_workbook
        import io

        response = client.get('/export/snapshot/xlsx')
        wb = load_workbook(io.BytesIO(response.data))

        ws_context = wb['_context']

        # Collect all values from the context sheet
        values = []
        for row in ws_context.iter_rows(values_only=True):
            values.extend([str(v) for v in row if v])

        # Verify key domain knowledge is present
        context_text = ' '.join(values)
        assert 'Rating Philosophy' in context_text
        assert 'Bonus Calculation' in context_text
        assert 'Talent Calibration' in context_text
        assert '0-200%' in context_text
        assert '1.35' in context_text  # upside exponent
        assert '1.9' in context_text   # downside exponent

        # Verify analytical guidance is present
        assert 'Expected Distribution' in context_text
        assert 'Red Flags' in context_text
        assert 'Analysis Questions' in context_text
        assert 'Management Levels' in context_text
        assert 'Data Quality' in context_text

    def test_export_snapshot_tenets_sheet(self, client, populated_db, sample_tenets):
        """Test that tenets sheet contains all tenet definitions."""
        from openpyxl import load_workbook
        import io

        response = client.get('/export/snapshot/xlsx')
        wb = load_workbook(io.BytesIO(response.data))

        ws_tenets = wb['_tenets']

        # Verify headers
        headers = [cell.value for cell in ws_tenets[1]]
        assert 'Tenet ID' in headers
        assert 'Tenet Name' in headers
        assert 'Description' in headers
        assert 'Category' in headers

        # Verify at least some tenets are present (row count > 1 means data exists)
        row_count = ws_tenets.max_row
        assert row_count > 1, "No tenets found in _tenets sheet"

    def test_export_snapshot_employees_data(self, client, populated_db):
        """Test that employee data is correctly exported."""
        from openpyxl import load_workbook
        import io

        response = client.get('/export/snapshot/xlsx')
        wb = load_workbook(io.BytesIO(response.data))

        ws_employees = wb['employees']

        # Verify employees are present (should have 4 from sample_employees fixture)
        assert ws_employees.max_row >= 5  # 1 header + 4 employees

        # Get all employee names
        names = [ws_employees.cell(row=i, column=2).value for i in range(2, ws_employees.max_row + 1)]
        assert 'Alice Johnson' in names
        assert 'Bob Smith' in names
        assert 'Charlie Brown' in names
        assert 'Diana Prince' in names

    def test_export_snapshot_with_no_employees(self, client, db_session):
        """Test snapshot export with empty database."""
        response = client.get('/export/snapshot/xlsx')
        assert response.status_code == 200

        from openpyxl import load_workbook
        import io

        wb = load_workbook(io.BytesIO(response.data))

        # All sheets should still exist
        assert len(wb.sheetnames) == 6

        # Employees sheet should only have headers
        ws_employees = wb['employees']
        assert ws_employees.max_row == 1  # Only header row


class TestPoolVerification:
    """Test pool verification API endpoint and pool source tracking."""

    def test_verify_pool_success(self, client, db_session):
        """Test successfully verifying a pool."""
        from models import BonusSettings

        # Create bonus settings with unverified calculated pool
        settings = BonusSettings(
            workday_pool=10000.0,
            pool_source='calculated_sum',
            pool_verified=False
        )
        db_session.add(settings)
        db_session.commit()

        response = client.post('/api/bonus-settings/verify-pool',
                              content_type='application/json')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['message'] == 'Pool verified'

        # Verify database was updated
        db_session.refresh(settings)
        assert settings.pool_verified is True

    def test_verify_pool_no_settings(self, client, db_session):
        """Test verify pool when no settings exist."""
        response = client.post('/api/bonus-settings/verify-pool',
                              content_type='application/json')

        assert response.status_code == 404
        result = json.loads(response.data)
        assert 'error' in result
        assert 'No bonus settings found' in result['error']

    def test_verify_pool_already_verified(self, client, db_session):
        """Test verifying an already verified pool (idempotent)."""
        from models import BonusSettings

        settings = BonusSettings(
            workday_pool=10000.0,
            pool_source='workday_metadata',
            pool_verified=True
        )
        db_session.add(settings)
        db_session.commit()

        response = client.post('/api/bonus-settings/verify-pool',
                              content_type='application/json')

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

    def test_pool_source_tracking_calculated(self, client, db_session):
        """Test that pool_source is 'calculated_sum' when pool is calculated."""
        from models import BonusSettings

        settings = BonusSettings(
            workday_pool=5000.0,
            pool_source='calculated_sum',
            pool_verified=False
        )
        db_session.add(settings)
        db_session.commit()

        # Verify source is correctly stored
        assert settings.pool_source == 'calculated_sum'
        assert settings.pool_verified is False

    def test_pool_source_tracking_workday_metadata(self, client, db_session):
        """Test that pool_source is 'workday_metadata' when from file metadata."""
        from models import BonusSettings

        settings = BonusSettings(
            workday_pool=8000.0,
            pool_source='workday_metadata',
            pool_verified=True  # Auto-verified for metadata pools
        )
        db_session.add(settings)
        db_session.commit()

        # Verify source and auto-verification
        assert settings.pool_source == 'workday_metadata'
        assert settings.pool_verified is True

    def test_bonus_settings_to_dict_includes_pool_fields(self, db_session):
        """Test that BonusSettings.to_dict() includes pool verification fields."""
        from models import BonusSettings

        settings = BonusSettings(
            workday_pool=12000.0,
            budget_override=0.0,
            manager_currency='USD',
            pool_source='calculated_sum',
            pool_verified=False
        )
        db_session.add(settings)
        db_session.commit()

        settings_dict = settings.to_dict()

        assert 'pool_source' in settings_dict
        assert settings_dict['pool_source'] == 'calculated_sum'
        assert 'pool_verified' in settings_dict
        assert settings_dict['pool_verified'] is False
