"""
Tests for the import API endpoints.
"""
import pytest
import os
import io
import tempfile
from openpyxl import Workbook
from models import Employee, Period, RatingSnapshot


def create_test_xlsx(employees_data, include_headers=True):
    """
    Create a test XLSX file with Workday format.

    Args:
        employees_data: List of dicts with employee data
        include_headers: Whether to include header rows

    Returns:
        BytesIO object containing the XLSX file
    """
    wb = Workbook()
    ws = wb.active

    # Row 1: Empty or label row (Workday format)
    ws.append(['Report Data'])

    # Row 2: Headers (matching Workday export)
    headers = [
        'Associate',
        'Supervisory Organization',
        'Current Job Profile',
        'Photo',
        'Errors',
        'Associate ID',
        'Current Base Pay - All Countries',
        'Current Base Pay - All Countries (USD)',
        'Currency',
        'Grade',
        'Annual Bonus Target %',
        'Last Bonus Allocation %',
        'Bonus Target - Local Currency',
        'Bonus Target - Local Currency (USD)',
        'Proposed Bonus Amount',
        'Proposed Bonus Amount (USD)',
        'Proposed % of Target Bonus',
        'Notes',
        'Zero Bonus Allocated'
    ]
    ws.append(headers)

    # Data rows
    for emp in employees_data:
        row = [
            emp.get('associate', ''),
            emp.get('supervisory_organization', ''),
            emp.get('current_job_profile', ''),
            emp.get('photo', ''),
            emp.get('errors', ''),
            emp.get('associate_id', ''),
            emp.get('current_base_pay_all_countries', ''),
            emp.get('current_base_pay_all_countries_usd', ''),
            emp.get('currency', ''),
            emp.get('grade', ''),
            emp.get('annual_bonus_target_percent', ''),
            emp.get('last_bonus_allocation_percent', ''),
            emp.get('bonus_target_local_currency', ''),
            emp.get('bonus_target_local_currency_usd', ''),
            emp.get('proposed_bonus_amount', ''),
            emp.get('proposed_bonus_amount_usd', ''),
            emp.get('proposed_percent_of_target_bonus', ''),
            emp.get('notes', ''),
            emp.get('zero_bonus_allocated', '')
        ]
        ws.append(row)

    # Save to BytesIO
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


class TestImportPage:
    """Tests for the import page route."""

    def test_import_page_loads(self, client, db_session):
        """Test that import page loads successfully."""
        response = client.get('/import')
        assert response.status_code == 200
        assert b'Import Workday Data' in response.data

    def test_import_page_has_upload_zone(self, client, db_session):
        """Test that import page has file upload zone."""
        response = client.get('/import')
        assert b'upload-zone' in response.data
        assert b'Drop your XLSX file here' in response.data


class TestImportAnalyze:
    """Tests for the /api/import/analyze endpoint."""

    def test_analyze_no_file(self, client, db_session):
        """Test analyze without file returns error."""
        response = client.post('/api/import/analyze')
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'No file' in data['error']

    def test_analyze_invalid_extension(self, client, db_session):
        """Test analyze with non-Excel file returns error."""
        data = {
            'file': (io.BytesIO(b'not an excel file'), 'test.txt')
        }
        response = client.post('/api/import/analyze', data=data, content_type='multipart/form-data')
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'Excel file' in data['error']

    def test_analyze_valid_xlsx(self, client, db_session):
        """Test analyze with valid XLSX returns metadata."""
        employees = [
            {
                'associate_id': 'EMP001',
                'associate': 'John Doe',
                'supervisory_organization': 'Engineering',
                'current_job_profile': 'Senior Engineer',
                'notes': 'Performance Rating: 125%\nJustification: Great work',
                'proposed_percent_of_target_bonus': 118.5
            },
            {
                'associate_id': 'EMP002',
                'associate': 'Jane Smith',
                'supervisory_organization': 'Product',
                'current_job_profile': 'Product Manager',
                'notes': '',
                'proposed_percent_of_target_bonus': 100.0
            }
        ]

        xlsx_file = create_test_xlsx(employees)

        data = {
            'file': (xlsx_file, 'test.xlsx'),
            'import_type': 'current'
        }
        response = client.post('/api/import/analyze', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert result['employee_count'] == 2
        assert result['has_bonus_column'] is True
        assert result['notes_count'] == 1  # Only John has notes

    def test_analyze_historical_period_exists(self, client, db_session):
        """Test analyze detects existing period for historical import."""
        # Create existing period
        period = Period(id='2024-H1', name='First Half 2024')
        db_session.add(period)
        db_session.commit()

        employees = [
            {
                'associate_id': 'EMP001',
                'associate': 'John Doe',
                'notes': 'Performance Rating: 125%'
            }
        ]

        xlsx_file = create_test_xlsx(employees)

        data = {
            'file': (xlsx_file, 'test.xlsx'),
            'import_type': 'historical',
            'period_id': '2024-H1'
        }
        response = client.post('/api/import/analyze', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert result['period_exists'] is True
        assert result['period_id'] == '2024-H1'


class TestImportCurrent:
    """Tests for the /api/import/current endpoint."""

    def test_import_current_no_file(self, client, db_session):
        """Test import current without file returns error."""
        response = client.post('/api/import/current')
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False

    def test_import_current_new_employees(self, client, db_session):
        """Test importing new employees."""
        employees = [
            {
                'associate_id': 'NEW001',
                'associate': 'New Person',
                'supervisory_organization': 'Engineering',
                'current_job_profile': 'Software Engineer',
                'currency': 'USD',
                'current_base_pay_all_countries_usd': 100000
            },
            {
                'associate_id': 'NEW002',
                'associate': 'Another Person',
                'supervisory_organization': 'Product',
                'current_job_profile': 'Product Manager',
                'currency': 'USD',
                'current_base_pay_all_countries_usd': 120000
            }
        ]

        xlsx_file = create_test_xlsx(employees)

        data = {
            'file': (xlsx_file, 'test.xlsx')
        }
        response = client.post('/api/import/current', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert result['imported'] == 2
        assert result['updated'] == 0

        # Verify in database
        emp1 = db_session.query(Employee).filter(Employee.associate_id == 'NEW001').first()
        assert emp1 is not None
        assert emp1.associate == 'New Person'
        assert emp1.performance_rating_percent is None  # Manager fields initialized empty

    def test_import_current_updates_existing(self, client, db_session):
        """Test importing updates existing employees but preserves ratings."""
        # Create existing employee with rating
        existing = Employee(
            associate_id='EMP001',
            associate='Old Name',
            supervisory_organization='Old Org',
            performance_rating_percent=125.0,
            justification='Previous rating'
        )
        db_session.add(existing)
        db_session.commit()

        # Import with updated info
        employees = [
            {
                'associate_id': 'EMP001',
                'associate': 'New Name',
                'supervisory_organization': 'New Org',
                'current_job_profile': 'New Job'
            }
        ]

        xlsx_file = create_test_xlsx(employees)

        data = {
            'file': (xlsx_file, 'test.xlsx')
        }
        response = client.post('/api/import/current', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert result['imported'] == 0
        assert result['updated'] == 1

        # Verify update
        emp = db_session.query(Employee).filter(Employee.associate_id == 'EMP001').first()
        assert emp.associate == 'New Name'
        assert emp.supervisory_organization == 'New Org'
        # Rating should be preserved
        assert emp.performance_rating_percent == 125.0
        assert emp.justification == 'Previous rating'

    def test_import_current_with_clear_existing(self, client, db_session):
        """Test importing with clear_existing removes old data."""
        # Create existing employees with ratings
        for i in range(3):
            emp = Employee(
                associate_id=f'OLD{i}',
                associate=f'Old Employee {i}',
                performance_rating_percent=100.0 + i * 10
            )
            db_session.add(emp)
        db_session.commit()

        assert db_session.query(Employee).count() == 3

        # Import new employees with clear_existing
        employees = [
            {
                'associate_id': 'NEW001',
                'associate': 'New Person',
                'supervisory_organization': 'Engineering'
            }
        ]

        xlsx_file = create_test_xlsx(employees)

        data = {
            'file': (xlsx_file, 'test.xlsx'),
            'clear_existing': 'true'
        }
        response = client.post('/api/import/current', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert result['cleared'] == 3
        assert result['imported'] == 1
        assert result['updated'] == 0

        # Verify old employees are gone
        assert db_session.query(Employee).count() == 1
        assert db_session.query(Employee).filter(Employee.associate_id == 'OLD0').first() is None

        # Verify new employee exists
        new_emp = db_session.query(Employee).filter(Employee.associate_id == 'NEW001').first()
        assert new_emp is not None
        assert new_emp.associate == 'New Person'


class TestImportHistorical:
    """Tests for the /api/import/historical endpoint."""

    def test_import_historical_no_file(self, client, db_session):
        """Test import historical without file returns error."""
        response = client.post('/api/import/historical')
        assert response.status_code == 400

    def test_import_historical_missing_period_id(self, client, db_session):
        """Test import historical without period_id returns error."""
        employees = [{'associate_id': 'EMP001', 'associate': 'John'}]
        xlsx_file = create_test_xlsx(employees)

        data = {
            'file': (xlsx_file, 'test.xlsx'),
            'period_name': 'First Half 2024'
        }
        response = client.post('/api/import/historical', data=data, content_type='multipart/form-data')

        assert response.status_code == 400
        result = response.get_json()
        assert 'Period ID' in result['error']

    def test_import_historical_creates_period_and_snapshots(self, client, db_session):
        """Test importing historical data creates period and snapshots."""
        employees = [
            {
                'associate_id': 'EMP001',
                'associate': 'John Doe',
                'supervisory_organization': 'Engineering',
                'current_job_profile': 'Senior Engineer',
                'bonus_target_local_currency_usd': 15000,
                'proposed_percent_of_target_bonus': 118.5,
                'notes': 'Performance Rating: 125%\nJustification: Excellent work\nMentor: Alice\nStrengths: Leadership'
            },
            {
                'associate_id': 'EMP002',
                'associate': 'Jane Smith',
                'supervisory_organization': 'Product',
                'current_job_profile': 'Product Manager',
                'bonus_target_local_currency_usd': 12000,
                'proposed_percent_of_target_bonus': 105.0,
                'notes': ''  # No notes - partial data
            }
        ]

        xlsx_file = create_test_xlsx(employees)

        data = {
            'file': (xlsx_file, 'test.xlsx'),
            'period_id': '2024-H1',
            'period_name': 'First Half 2024'
        }
        response = client.post('/api/import/historical', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert result['imported'] == 2
        assert result['updated'] == 0
        assert result['full_details'] == 1  # Only John has full details from notes

        # Verify period was created
        period = db_session.query(Period).filter(Period.id == '2024-H1').first()
        assert period is not None
        assert period.name == 'First Half 2024'
        assert period.archived_at is not None

        # Verify snapshots
        snapshots = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.period_id == '2024-H1'
        ).all()
        assert len(snapshots) == 2

        # Check John's snapshot (full details)
        john_snap = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.period_id == '2024-H1',
            RatingSnapshot.associate_id == 'EMP001'
        ).first()
        assert john_snap.performance_rating == 125.0
        assert john_snap.bonus_allocation == 118.5
        assert john_snap.justification == 'Excellent work'
        assert john_snap.mentors == 'Alice'
        assert john_snap.tenets_strengths == 'Leadership'
        assert john_snap.has_full_details is True
        assert john_snap.snapshot_name == 'John Doe'
        assert john_snap.snapshot_org == 'Engineering'

        # Check Jane's snapshot (partial)
        jane_snap = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.period_id == '2024-H1',
            RatingSnapshot.associate_id == 'EMP002'
        ).first()
        assert jane_snap.performance_rating is None  # No rating in notes
        assert jane_snap.bonus_allocation == 105.0  # From Workday column
        assert jane_snap.has_full_details is False

    def test_import_historical_updates_existing_snapshots(self, client, db_session):
        """Test re-importing historical data updates existing snapshots."""
        # Create existing period and snapshot
        period = Period(id='2024-H1', name='Old Name')
        db_session.add(period)

        snapshot = RatingSnapshot(
            period_id='2024-H1',
            associate_id='EMP001',
            performance_rating=100.0,
            bonus_allocation=100.0,
            snapshot_name='Old Name',
            has_full_details=False
        )
        db_session.add(snapshot)
        db_session.commit()

        # Re-import with updated data
        employees = [
            {
                'associate_id': 'EMP001',
                'associate': 'New Name',
                'supervisory_organization': 'New Org',
                'proposed_percent_of_target_bonus': 125.0,
                'notes': 'Performance Rating: 130%\nJustification: Updated review'
            }
        ]

        xlsx_file = create_test_xlsx(employees)

        data = {
            'file': (xlsx_file, 'test.xlsx'),
            'period_id': '2024-H1',
            'period_name': 'Updated Name'
        }
        response = client.post('/api/import/historical', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        result = response.get_json()
        assert result['success'] is True
        assert result['imported'] == 0
        assert result['updated'] == 1

        # Verify period was updated
        period = db_session.query(Period).filter(Period.id == '2024-H1').first()
        assert period.name == 'Updated Name'

        # Verify snapshot was updated
        snapshot = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.period_id == '2024-H1',
            RatingSnapshot.associate_id == 'EMP001'
        ).first()
        assert snapshot.performance_rating == 130.0
        assert snapshot.bonus_allocation == 125.0
        assert snapshot.justification == 'Updated review'
        assert snapshot.snapshot_name == 'New Name'
        assert snapshot.has_full_details is True


class TestXlsxUtils:
    """Tests for the xlsx_utils module."""

    def test_analyze_xlsx_counts_employees(self, db_session):
        """Test analyze_xlsx correctly counts employees."""
        from xlsx_utils import analyze_xlsx

        employees = [
            {'associate_id': f'EMP{i}', 'associate': f'Employee {i}'}
            for i in range(10)
        ]

        xlsx_file = create_test_xlsx(employees)

        # Save to temp file
        temp_dir = os.path.expanduser('~/tmp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, 'test_analyze.xlsx')

        with open(temp_path, 'wb') as f:
            f.write(xlsx_file.read())

        try:
            result = analyze_xlsx(temp_path)
            assert result['success'] is True
            assert result['employee_count'] == 10
        finally:
            os.remove(temp_path)

    def test_analyze_xlsx_detects_bonus_column(self, db_session):
        """Test analyze_xlsx detects bonus column presence."""
        from xlsx_utils import analyze_xlsx

        employees = [
            {
                'associate_id': 'EMP001',
                'associate': 'John',
                'proposed_percent_of_target_bonus': 115.0
            }
        ]

        xlsx_file = create_test_xlsx(employees)

        temp_dir = os.path.expanduser('~/tmp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, 'test_bonus.xlsx')

        with open(temp_path, 'wb') as f:
            f.write(xlsx_file.read())

        try:
            result = analyze_xlsx(temp_path)
            assert result['success'] is True
            assert result['has_bonus_column'] is True
        finally:
            os.remove(temp_path)

    def test_parse_xlsx_employees(self, db_session):
        """Test parse_xlsx_employees extracts all fields."""
        from xlsx_utils import parse_xlsx_employees

        employees = [
            {
                'associate_id': 'EMP001',
                'associate': 'John Doe',
                'supervisory_organization': 'Engineering',
                'current_job_profile': 'Senior Engineer',
                'currency': 'USD',
                'current_base_pay_all_countries_usd': 150000,
                'bonus_target_local_currency_usd': 22500,
                'proposed_percent_of_target_bonus': 118.5,
                'notes': 'Performance Rating: 125%'
            }
        ]

        xlsx_file = create_test_xlsx(employees)

        temp_dir = os.path.expanduser('~/tmp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, 'test_parse.xlsx')

        with open(temp_path, 'wb') as f:
            f.write(xlsx_file.read())

        try:
            success, parsed, error = parse_xlsx_employees(temp_path)

            assert success is True
            assert len(parsed) == 1

            emp = parsed[0]
            assert emp['associate_id'] == 'EMP001'
            assert emp['associate'] == 'John Doe'
            assert emp['supervisory_organization'] == 'Engineering'
            assert emp['current_job_profile'] == 'Senior Engineer'
            assert emp['currency'] == 'USD'
            assert emp['current_base_pay_all_countries_usd'] == 150000
            assert emp['bonus_target_local_currency_usd'] == 22500
            assert emp['proposed_percent_of_target_bonus'] == 118.5
            assert 'Performance Rating: 125%' in emp['notes']
        finally:
            os.remove(temp_path)
