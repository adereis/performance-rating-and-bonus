"""
Tests for Excel import functionality.
"""
import pytest
import os
import tempfile
import openpyxl
from models import Employee, init_db, get_db
from convert_xlsx import convert_xlsx_to_db


class TestExcelImport:
    """Test Excel import from Workday export."""

    @pytest.fixture
    def sample_excel_file(self):
        """Create a sample Excel file for testing."""
        # Create temporary Excel file
        fd, path = tempfile.mkstemp(suffix='.xlsx')
        os.close(fd)

        wb = openpyxl.Workbook()
        sheet = wb.active

        # Row 0: metadata (will be skipped)
        sheet.append(['Workday Export', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''])

        # Row 1: headers (actual column names)
        headers = [
            'Associate',
            'Supervisory Organization',
            'Current Job Profile',
            'Photo',
            'Errors',
            'Associate ID',
            'Current Base Pay All Countries',
            'Current Base Pay All Countries (USD)',
            'Currency',
            'Grade',
            'Annual Bonus Target Percent',
            'Last Bonus Allocation Percent',
            'Bonus Target - Local Currency',
            'Bonus Target - Local Currency (USD)',
            'Proposed Bonus Amount',
            'Proposed Bonus Amount (USD)',
            'Proposed Percent of Target Bonus',
            'Notes',
            'Zero Bonus Allocated'
        ]
        sheet.append(headers)

        # Row 2+: data rows
        sheet.append([
            'Alice Johnson',
            'Engineering - AI Team',
            'Senior Software Engineer',
            'photo_url',
            '',
            'WD001',
            130000,
            130000,
            'USD',
            'P4',
            15.0,
            110.0,
            19500,
            19500,
            21450,
            21450,
            110.0,
            'Previous notes here',
            ''
        ])

        sheet.append([
            'Bob Smith',
            'Engineering - Platform',
            'Staff Software Engineer',
            'photo_url2',
            '',
            'WD002',
            160000,
            160000,
            'USD',
            'P5',
            20.0,
            120.0,
            32000,
            32000,
            38400,
            38400,
            120.0,
            '',
            ''
        ])

        wb.save(path)
        yield path

        # Cleanup
        os.unlink(path)

    def test_import_excel_file(self, sample_excel_file, test_db):
        """Test importing a valid Excel file."""
        SessionLocal, db_path = test_db

        # Override DATABASE_URL temporarily
        import models
        original_url = models.DATABASE_URL
        models.DATABASE_URL = f'sqlite:///{db_path}'

        # Recreate engine with test database
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        test_engine = create_engine(f'sqlite:///{db_path}', echo=False)
        models.Base.metadata.create_all(bind=test_engine)
        models.engine = test_engine
        models.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

        try:
            # Import the file
            result = convert_xlsx_to_db(sample_excel_file)
            assert result is True

            # Verify data was imported
            db = SessionLocal()
            try:
                employees = db.query(Employee).all()
                assert len(employees) == 2

                # Check first employee
                alice = db.query(Employee).filter(Employee.associate_id == 'WD001').first()
                assert alice is not None
                assert alice.associate == 'Alice Johnson'
                assert alice.supervisory_organization == 'Engineering - AI Team'
                assert alice.current_job_profile == 'Senior Software Engineer'
                assert alice.current_base_pay_all_countries_usd == 130000.0
                assert alice.annual_bonus_target_percent == 15.0
                assert alice.notes == 'Previous notes here'

                # Check second employee
                bob = db.query(Employee).filter(Employee.associate_id == 'WD002').first()
                assert bob is not None
                assert bob.associate == 'Bob Smith'
                assert bob.current_job_profile == 'Staff Software Engineer'
                assert bob.current_base_pay_all_countries_usd == 160000.0
            finally:
                db.close()
        finally:
            # Restore original
            models.DATABASE_URL = original_url

    def test_import_nonexistent_file(self, test_db):
        """Test importing a file that doesn't exist."""
        SessionLocal, db_path = test_db

        import models
        original_url = models.DATABASE_URL
        models.DATABASE_URL = f'sqlite:///{db_path}'

        try:
            result = convert_xlsx_to_db('nonexistent_file.xlsx')
            assert result is False
        finally:
            models.DATABASE_URL = original_url

    def test_import_updates_existing_employees(self, sample_excel_file, test_db):
        """Test that re-importing updates existing employees."""
        SessionLocal, db_path = test_db

        import models
        original_url = models.DATABASE_URL
        models.DATABASE_URL = f'sqlite:///{db_path}'

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        test_engine = create_engine(f'sqlite:///{db_path}', echo=False)
        models.Base.metadata.create_all(bind=test_engine)
        models.engine = test_engine
        models.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

        try:
            # First import
            result = convert_xlsx_to_db(sample_excel_file)
            assert result is True

            # Add a rating to one employee
            db = SessionLocal()
            try:
                alice = db.query(Employee).filter(Employee.associate_id == 'WD001').first()
                alice.performance_rating_percent = 125.0
                alice.justification = 'Great work'
                db.commit()
            finally:
                db.close()

            # Re-import the same file
            result = convert_xlsx_to_db(sample_excel_file)
            assert result is True

            # Verify rating was preserved
            db = SessionLocal()
            try:
                alice = db.query(Employee).filter(Employee.associate_id == 'WD001').first()
                assert alice.performance_rating_percent == 125.0
                assert alice.justification == 'Great work'

                # But Workday fields should be updated
                assert alice.associate == 'Alice Johnson'
                assert alice.current_job_profile == 'Senior Software Engineer'
            finally:
                db.close()
        finally:
            models.DATABASE_URL = original_url

    def test_import_preserves_manager_inputs(self, sample_excel_file, test_db):
        """Test that manager inputs are preserved on re-import."""
        SessionLocal, db_path = test_db

        import models
        original_url = models.DATABASE_URL
        models.DATABASE_URL = f'sqlite:///{db_path}'

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from datetime import datetime

        test_engine = create_engine(f'sqlite:///{db_path}', echo=False)
        models.Base.metadata.create_all(bind=test_engine)
        models.engine = test_engine
        models.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

        try:
            # First import
            convert_xlsx_to_db(sample_excel_file)

            # Add all manager inputs
            db = SessionLocal()
            try:
                alice = db.query(Employee).filter(Employee.associate_id == 'WD001').first()
                alice.performance_rating_percent = 135.0
                alice.justification = 'Outstanding performance'
                alice.mentor = 'Senior Manager'
                alice.mentees = 'Junior Dev 1, Junior Dev 2'
                alice.last_updated = datetime.now()
                db.commit()
            finally:
                db.close()

            # Re-import
            convert_xlsx_to_db(sample_excel_file)

            # Verify all manager inputs preserved
            db = SessionLocal()
            try:
                alice = db.query(Employee).filter(Employee.associate_id == 'WD001').first()
                assert alice.performance_rating_percent == 135.0
                assert alice.justification == 'Outstanding performance'
                assert alice.mentor == 'Senior Manager'
                assert alice.mentees == 'Junior Dev 1, Junior Dev 2'
                assert alice.last_updated is not None
            finally:
                db.close()
        finally:
            models.DATABASE_URL = original_url

    def test_import_handles_empty_cells(self, test_db):
        """Test importing Excel with empty cells."""
        SessionLocal, db_path = test_db

        # Create Excel with some empty cells
        fd, path = tempfile.mkstemp(suffix='.xlsx')
        os.close(fd)

        wb = openpyxl.Workbook()
        sheet = wb.active

        # Headers
        sheet.append(['Metadata row'])
        sheet.append([
            'Associate',
            'Supervisory Organization',
            'Current Job Profile',
            'Photo',
            'Errors',
            'Associate ID',
            'Current Base Pay All Countries',
            'Current Base Pay All Countries (USD)',
            'Currency',
            'Grade',
            'Annual Bonus Target Percent',
            'Last Bonus Allocation Percent',
            'Bonus Target - Local Currency',
            'Bonus Target - Local Currency (USD)',
            'Proposed Bonus Amount',
            'Proposed Bonus Amount (USD)',
            'Proposed Percent of Target Bonus',
            'Notes',
            'Zero Bonus Allocated'
        ])

        # Data row with some empty cells
        sheet.append([
            'Test User',
            '',  # Empty supervisory org
            'Engineer',
            '',
            '',
            'TEST001',
            None,  # Empty base pay
            100000,
            'USD',
            'P3',
            None,  # Empty bonus target
            None,
            None,
            None,
            None,
            None,
            None,
            '',
            ''
        ])

        wb.save(path)

        import models
        original_url = models.DATABASE_URL
        models.DATABASE_URL = f'sqlite:///{db_path}'

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        test_engine = create_engine(f'sqlite:///{db_path}', echo=False)
        models.Base.metadata.create_all(bind=test_engine)
        models.engine = test_engine
        models.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

        try:
            result = convert_xlsx_to_db(path)
            assert result is True

            db = SessionLocal()
            try:
                user = db.query(Employee).filter(Employee.associate_id == 'TEST001').first()
                assert user is not None
                assert user.associate == 'Test User'
                assert user.supervisory_organization == ''
                assert user.current_base_pay_all_countries is None
            finally:
                db.close()
        finally:
            models.DATABASE_URL = original_url
            os.unlink(path)

    def test_import_initializes_manager_fields_for_new_employees(self, sample_excel_file, test_db):
        """Test that new employees have manager fields initialized."""
        SessionLocal, db_path = test_db

        import models
        original_url = models.DATABASE_URL
        models.DATABASE_URL = f'sqlite:///{db_path}'

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        test_engine = create_engine(f'sqlite:///{db_path}', echo=False)
        models.Base.metadata.create_all(bind=test_engine)
        models.engine = test_engine
        models.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

        try:
            convert_xlsx_to_db(sample_excel_file)

            db = SessionLocal()
            try:
                alice = db.query(Employee).filter(Employee.associate_id == 'WD001').first()

                # New employees should have empty/None manager fields
                assert alice.performance_rating_percent is None
                assert alice.justification == ''
                assert alice.mentor == ''
                assert alice.mentees == ''
                assert alice.last_updated is None
            finally:
                db.close()
        finally:
            models.DATABASE_URL = original_url
