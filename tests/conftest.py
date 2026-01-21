"""
Pytest configuration and fixtures for testing.
"""
import pytest
import os
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Employee
from app import app as flask_app


@pytest.fixture(scope='function')
def test_db():
    """Create a temporary test database for each test."""
    # Create a temporary database file
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    db_url = f'sqlite:///{db_path}'

    # Create engine and tables
    engine = create_engine(db_url, echo=False)
    Base.metadata.create_all(bind=engine)

    # Create session factory
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    yield TestSessionLocal, db_path

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture(scope='function')
def db_session(test_db):
    """Provide a database session for a test."""
    SessionLocal, db_path = test_db
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture(scope='function')
def sample_employee_data():
    """Sample employee data for testing."""
    return {
        'associate_id': 'EMP001',
        'associate': 'John Doe',
        'supervisory_organization': 'Engineering',
        'current_job_profile': 'Senior Software Engineer',
        'current_base_pay_manager_currency': 120000.0,
        'currency': 'USD',
        'annual_bonus_target_percent': 15.0,
        'performance_rating_percent': None,
        'justification': '',
        'mentor': '',
        'mentees': '',
    }


@pytest.fixture(scope='function')
def sample_employees():
    """Multiple sample employees for testing."""
    return [
        {
            'associate_id': 'EMP001',
            'associate': 'Alice Johnson',
            'supervisory_organization': 'Engineering',
            'current_job_profile': 'Senior Software Engineer',
            'current_base_pay_manager_currency': 130000.0,
            'currency': 'USD',
            'performance_rating_percent': 120.0,
            'justification': 'Excellent performance',
            'mentor': 'Bob Smith',
            'mentees': 'Charlie Brown',
        },
        {
            'associate_id': 'EMP002',
            'associate': 'Bob Smith',
            'supervisory_organization': 'Engineering',
            'current_job_profile': 'Staff Software Engineer',
            'current_base_pay_manager_currency': 160000.0,
            'currency': 'USD',
            'performance_rating_percent': 140.0,
            'justification': 'Outstanding contributions',
            'mentor': '',
            'mentees': 'Alice Johnson, Charlie Brown',
        },
        {
            'associate_id': 'EMP003',
            'associate': 'Charlie Brown',
            'supervisory_organization': 'Engineering',
            'current_job_profile': 'Software Engineer',
            'current_base_pay_manager_currency': 95000.0,
            'currency': 'USD',
            'performance_rating_percent': 85.0,
            'justification': 'Good progress, needs more experience',
            'mentor': 'Alice Johnson',
            'mentees': '',
        },
        {
            'associate_id': 'EMP004',
            'associate': 'Diana Prince',
            'supervisory_organization': 'Product',
            'current_job_profile': 'Product Manager',
            'current_base_pay_manager_currency': 125000.0,
            'currency': 'USD',
            'performance_rating_percent': None,
            'justification': '',
            'mentor': '',
            'mentees': '',
            }
    ]


@pytest.fixture(scope='function')
def app(test_db):
    """Create Flask app configured for testing."""
    SessionLocal, db_path = test_db

    # Configure app for testing
    flask_app.config['TESTING'] = True
    flask_app.config['DATABASE_URL'] = f'sqlite:///{db_path}'

    # Override the get_db function to use test database
    import models
    original_get_db = models.get_db

    def test_get_db():
        return SessionLocal()

    models.get_db = test_get_db

    # Also patch in app module
    import app as app_module
    app_module.get_db = test_get_db

    yield flask_app

    # Restore original
    models.get_db = original_get_db
    app_module.get_db = original_get_db


@pytest.fixture(scope='function')
def client(app):
    """Create Flask test client."""
    return app.test_client()


@pytest.fixture(scope='function')
def populated_db(db_session, sample_employees):
    """Database session populated with sample employees."""
    for emp_data in sample_employees:
        employee = Employee(**emp_data)
        db_session.add(employee)

    db_session.commit()

    return db_session


@pytest.fixture(scope='function')
def sample_tenets(app, monkeypatch):
    """
    Configure app to use sample tenets for testing.

    This fixture monkeypatches load_tenets_config to return sample tenets,
    keeping test fixtures out of production code.
    """
    import json
    sample_file = 'samples/tenets-sample.json'
    with open(sample_file, 'r') as f:
        sample_config = json.load(f)
    sample_map = {t['id']: t['name'] for t in sample_config.get('tenets', [])}

    import app as app_module
    monkeypatch.setattr(app_module, 'load_tenets_config',
                        lambda: (sample_config, sample_map))
    return sample_config


@pytest.fixture(scope='function')
def talent_xlsx_file():
    """Create a temporary talent calibration XLSX file for testing."""
    from openpyxl import Workbook

    # Create workbook with talent headers (matching real Workday export structure)
    wb = Workbook()
    ws = wb.active
    ws.title = "Talent Calibration"

    # Talent files have metadata rows before headers (like real Workday exports)
    # Headers at row 5 with 'Worker' instead of 'Associate'
    ws['A1'] = 'Talent Calibration Report'
    ws['A2'] = 'Generated: 2025-01-15'
    ws['A3'] = ''
    ws['A4'] = ''

    # Headers at row 5
    headers = [
        'Associate ID', 'Worker', 'Supervisory Organization',
        'Current Job Profile', 'Performance: What', 'Performance: How',
        'Future Talent: Growth Agility', 'Future Talent: Change Agility',
        'Movement Readiness'
    ]
    for col, header in enumerate(headers, 1):
        ws.cell(row=5, column=col, value=header)

    # Sample data rows
    data = [
        ['T001', 'Test Employee One', 'Engineering (Manager One)', 'Senior Engineer',
         'Surpasses Expectations', 'Meets Expectations',
         'Always/Most of the Time', 'Always/Most of the Time', 'Ready Now'],
        ['T002', 'Test Employee Two', 'Engineering (Manager One)', 'Engineer',
         'Meets Expectations', 'Meets Expectations',
         'Sometimes', 'Always/Most of the Time', 'Ready in 1-2 Years'],
    ]

    for row_idx, row_data in enumerate(data, 6):
        for col_idx, value in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    # Save to temporary file
    fd, path = tempfile.mkstemp(suffix='.xlsx')
    os.close(fd)
    wb.save(path)

    yield path

    # Cleanup
    os.unlink(path)
