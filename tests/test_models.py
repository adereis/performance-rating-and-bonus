"""
Tests for the Employee, Period, and RatingSnapshot models and database operations.
"""
import pytest
from datetime import datetime
from models import Employee, Period, RatingSnapshot


class TestEmployeeModel:
    """Test Employee model CRUD operations."""

    def test_create_employee(self, db_session, sample_employee_data):
        """Test creating a new employee."""
        employee = Employee(**sample_employee_data)
        db_session.add(employee)
        db_session.commit()

        # Verify employee was created
        assert employee.associate_id == 'EMP001'
        assert employee.associate == 'John Doe'
        assert employee.supervisory_organization == 'Engineering'
        assert employee.current_job_profile == 'Senior Software Engineer'
        assert employee.current_base_pay_all_countries_usd == 120000.0

    def test_read_employee(self, db_session, sample_employee_data):
        """Test reading an employee from database."""
        # Create employee
        employee = Employee(**sample_employee_data)
        db_session.add(employee)
        db_session.commit()

        # Read employee
        retrieved = db_session.query(Employee).filter(
            Employee.associate_id == 'EMP001'
        ).first()

        assert retrieved is not None
        assert retrieved.associate == 'John Doe'
        assert retrieved.current_job_profile == 'Senior Software Engineer'

    def test_update_employee(self, db_session, sample_employee_data):
        """Test updating employee fields."""
        # Create employee
        employee = Employee(**sample_employee_data)
        db_session.add(employee)
        db_session.commit()

        # Update employee
        employee.performance_rating_percent = 125.0
        employee.justification = 'Exceeded expectations'
        employee.mentor = 'Jane Smith'
        employee.last_updated = datetime.now()
        db_session.commit()

        # Verify update
        retrieved = db_session.query(Employee).filter(
            Employee.associate_id == 'EMP001'
        ).first()

        assert retrieved.performance_rating_percent == 125.0
        assert retrieved.justification == 'Exceeded expectations'
        assert retrieved.mentor == 'Jane Smith'
        assert retrieved.last_updated is not None

    def test_delete_employee(self, db_session, sample_employee_data):
        """Test deleting an employee."""
        # Create employee
        employee = Employee(**sample_employee_data)
        db_session.add(employee)
        db_session.commit()

        # Delete employee
        db_session.delete(employee)
        db_session.commit()

        # Verify deletion
        retrieved = db_session.query(Employee).filter(
            Employee.associate_id == 'EMP001'
        ).first()

        assert retrieved is None

    def test_query_by_associate_name(self, db_session, sample_employees):
        """Test querying employee by associate name."""
        # Add multiple employees
        for emp_data in sample_employees:
            employee = Employee(**emp_data)
            db_session.add(employee)
        db_session.commit()

        # Query by name
        alice = db_session.query(Employee).filter(
            Employee.associate == 'Alice Johnson'
        ).first()

        assert alice is not None
        assert alice.associate_id == 'EMP001'
        assert alice.current_job_profile == 'Senior Software Engineer'

    def test_query_by_job_profile(self, db_session, sample_employees):
        """Test querying employees by job profile."""
        # Add multiple employees
        for emp_data in sample_employees:
            employee = Employee(**emp_data)
            db_session.add(employee)
        db_session.commit()

        # Query Senior Software Engineer employees
        senior_engineers = db_session.query(Employee).filter(
            Employee.current_job_profile == 'Senior Software Engineer'
        ).all()

        assert len(senior_engineers) == 1  # Alice
        assert senior_engineers[0].associate == 'Alice Johnson'

    def test_to_dict_conversion(self, db_session, sample_employee_data):
        """Test converting employee to dictionary."""
        employee = Employee(**sample_employee_data)
        employee.last_updated = datetime(2025, 1, 15, 10, 30, 0)
        db_session.add(employee)
        db_session.commit()

        # Convert to dict
        emp_dict = employee.to_dict()

        assert emp_dict['Associate ID'] == 'EMP001'
        assert emp_dict['Associate'] == 'John Doe'
        assert emp_dict['Supervisory Organization'] == 'Engineering'
        assert emp_dict['Current Job Profile'] == 'Senior Software Engineer'
        assert emp_dict['Current Base Pay All Countries (USD)'] == 120000.0
        assert emp_dict['last_updated'] == '2025-01-15 10:30:00'

    def test_to_dict_with_no_timestamp(self, db_session, sample_employee_data):
        """Test to_dict with no last_updated timestamp."""
        employee = Employee(**sample_employee_data)
        db_session.add(employee)
        db_session.commit()

        emp_dict = employee.to_dict()
        assert emp_dict['last_updated'] == ''

    def test_nullable_fields(self, db_session):
        """Test that optional fields can be null."""
        employee = Employee(
            associate_id='EMP999',
            associate='Test User'
        )
        db_session.add(employee)
        db_session.commit()

        retrieved = db_session.query(Employee).filter(
            Employee.associate_id == 'EMP999'
        ).first()

        assert retrieved.supervisory_organization is None
        assert retrieved.performance_rating_percent is None
        assert retrieved.justification is None

    def test_float_precision(self, db_session):
        """Test that float values maintain precision."""
        employee = Employee(
            associate_id='EMP888',
            associate='Test User',
            current_base_pay_all_countries_usd=123456.78,
            performance_rating_percent=123.45
        )
        db_session.add(employee)
        db_session.commit()

        retrieved = db_session.query(Employee).filter(
            Employee.associate_id == 'EMP888'
        ).first()

        assert retrieved.current_base_pay_all_countries_usd == 123456.78
        assert retrieved.performance_rating_percent == 123.45

    def test_query_all_employees(self, db_session, sample_employees):
        """Test querying all employees."""
        # Add multiple employees
        for emp_data in sample_employees:
            employee = Employee(**emp_data)
            db_session.add(employee)
        db_session.commit()

        # Query all
        all_employees = db_session.query(Employee).all()

        assert len(all_employees) == 4
        assert all_employees[0].associate_id == 'EMP001'

    def test_filter_rated_employees(self, db_session, sample_employees):
        """Test filtering employees with ratings."""
        # Add multiple employees
        for emp_data in sample_employees:
            employee = Employee(**emp_data)
            db_session.add(employee)
        db_session.commit()

        # Query employees with ratings
        rated = db_session.query(Employee).filter(
            Employee.performance_rating_percent.isnot(None)
        ).all()

        assert len(rated) == 3  # Alice, Bob, Charlie have ratings

    def test_filter_unrated_employees(self, db_session, sample_employees):
        """Test filtering employees without ratings."""
        # Add multiple employees
        for emp_data in sample_employees:
            employee = Employee(**emp_data)
            db_session.add(employee)
        db_session.commit()

        # Query employees without ratings
        unrated = db_session.query(Employee).filter(
            Employee.performance_rating_percent.is_(None)
        ).all()

        assert len(unrated) == 1  # Diana has no rating
        assert unrated[0].associate == 'Diana Prince'

    def test_order_by_rating(self, db_session, sample_employees):
        """Test ordering employees by performance rating."""
        # Add multiple employees
        for emp_data in sample_employees:
            employee = Employee(**emp_data)
            db_session.add(employee)
        db_session.commit()

        # Query ordered by rating descending
        ordered = db_session.query(Employee).filter(
            Employee.performance_rating_percent.isnot(None)
        ).order_by(Employee.performance_rating_percent.desc()).all()

        assert len(ordered) == 3
        assert ordered[0].associate == 'Bob Smith'  # 140
        assert ordered[1].associate == 'Alice Johnson'  # 120
        assert ordered[2].associate == 'Charlie Brown'  # 85


class TestPeriodModel:
    """Test Period model CRUD operations."""

    def test_create_period(self, db_session):
        """Test creating a new period."""
        period = Period(
            id='2024-H1',
            name='First Half 2024',
            archived_at=datetime.now(),
            notes='Initial rating period'
        )
        db_session.add(period)
        db_session.commit()

        assert period.id == '2024-H1'
        assert period.name == 'First Half 2024'
        assert period.archived_at is not None
        assert period.notes == 'Initial rating period'

    def test_period_to_dict(self, db_session):
        """Test converting period to dictionary."""
        archived_time = datetime(2024, 6, 30, 12, 0, 0)
        period = Period(
            id='2024-H1',
            name='First Half 2024',
            archived_at=archived_time,
            notes='Test notes'
        )
        db_session.add(period)
        db_session.commit()

        period_dict = period.to_dict()

        assert period_dict['id'] == '2024-H1'
        assert period_dict['name'] == 'First Half 2024'
        assert period_dict['archived_at'] == '2024-06-30 12:00:00'
        assert period_dict['notes'] == 'Test notes'

    def test_period_without_notes(self, db_session):
        """Test period with optional fields null."""
        period = Period(
            id='2024-Q4',
            name='Q4 2024'
        )
        db_session.add(period)
        db_session.commit()

        assert period.archived_at is None
        assert period.notes is None

    def test_query_periods(self, db_session):
        """Test querying multiple periods."""
        periods_data = [
            {'id': '2024-H1', 'name': 'First Half 2024'},
            {'id': '2024-H2', 'name': 'Second Half 2024'},
            {'id': '2025-H1', 'name': 'First Half 2025'},
        ]
        for data in periods_data:
            db_session.add(Period(**data))
        db_session.commit()

        all_periods = db_session.query(Period).order_by(Period.id).all()

        assert len(all_periods) == 3
        assert all_periods[0].id == '2024-H1'
        assert all_periods[2].id == '2025-H1'


class TestRatingSnapshotModel:
    """Test RatingSnapshot model CRUD operations."""

    def test_create_snapshot(self, db_session):
        """Test creating a new rating snapshot."""
        snapshot = RatingSnapshot(
            period_id='2024-H1',
            associate_id='EMP001',
            performance_rating=125.0,
            bonus_allocation=118.5,
            justification='Excellent performance',
            tenets_strengths='Leadership, Innovation',
            tenets_improvements='Communication',
            mentors='Alice Chen',
            mentees='Bob Jones',
            snapshot_name='John Doe',
            snapshot_org='Engineering',
            snapshot_job_profile='Senior Engineer',
            snapshot_bonus_target_usd=20000.0,
            archived_at=datetime.now(),
            has_full_details=True
        )
        db_session.add(snapshot)
        db_session.commit()

        assert snapshot.id is not None
        assert snapshot.period_id == '2024-H1'
        assert snapshot.associate_id == 'EMP001'
        assert snapshot.performance_rating == 125.0
        assert snapshot.bonus_allocation == 118.5

    def test_snapshot_to_dict(self, db_session):
        """Test converting snapshot to dictionary."""
        archived_time = datetime(2024, 6, 30, 12, 0, 0)
        snapshot = RatingSnapshot(
            period_id='2024-H1',
            associate_id='EMP001',
            performance_rating=130.0,
            bonus_allocation=125.0,
            justification='Great work',
            snapshot_name='John Doe',
            archived_at=archived_time,
            has_full_details=True
        )
        db_session.add(snapshot)
        db_session.commit()

        snapshot_dict = snapshot.to_dict()

        assert snapshot_dict['period_id'] == '2024-H1'
        assert snapshot_dict['associate_id'] == 'EMP001'
        assert snapshot_dict['performance_rating'] == 130.0
        assert snapshot_dict['bonus_allocation'] == 125.0
        assert snapshot_dict['archived_at'] == '2024-06-30 12:00:00'
        assert snapshot_dict['has_full_details'] is True

    def test_partial_snapshot(self, db_session):
        """Test snapshot with only bonus allocation (no rating from Notes)."""
        snapshot = RatingSnapshot(
            period_id='2023-H2',
            associate_id='EMP002',
            performance_rating=None,  # Not available
            bonus_allocation=105.0,   # From Workday column
            snapshot_name='Jane Smith',
            has_full_details=False
        )
        db_session.add(snapshot)
        db_session.commit()

        assert snapshot.performance_rating is None
        assert snapshot.bonus_allocation == 105.0
        assert snapshot.has_full_details is False

    def test_unique_constraint(self, db_session):
        """Test that period_id + associate_id is unique."""
        snapshot1 = RatingSnapshot(
            period_id='2024-H1',
            associate_id='EMP001',
            bonus_allocation=100.0,
            snapshot_name='John Doe'
        )
        db_session.add(snapshot1)
        db_session.commit()

        # Attempting to add duplicate should raise error
        snapshot2 = RatingSnapshot(
            period_id='2024-H1',
            associate_id='EMP001',
            bonus_allocation=110.0,
            snapshot_name='John Doe'
        )
        db_session.add(snapshot2)

        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()

    def test_query_by_period(self, db_session):
        """Test querying snapshots by period."""
        # Create snapshots for different periods
        snapshots_data = [
            {'period_id': '2024-H1', 'associate_id': 'EMP001', 'bonus_allocation': 100.0, 'snapshot_name': 'A'},
            {'period_id': '2024-H1', 'associate_id': 'EMP002', 'bonus_allocation': 110.0, 'snapshot_name': 'B'},
            {'period_id': '2024-H2', 'associate_id': 'EMP001', 'bonus_allocation': 120.0, 'snapshot_name': 'A'},
        ]
        for data in snapshots_data:
            db_session.add(RatingSnapshot(**data))
        db_session.commit()

        h1_snapshots = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.period_id == '2024-H1'
        ).all()

        assert len(h1_snapshots) == 2

    def test_query_by_employee(self, db_session):
        """Test querying snapshots by employee across periods."""
        snapshots_data = [
            {'period_id': '2024-H1', 'associate_id': 'EMP001', 'performance_rating': 100.0, 'bonus_allocation': 98.0, 'snapshot_name': 'A'},
            {'period_id': '2024-H2', 'associate_id': 'EMP001', 'performance_rating': 120.0, 'bonus_allocation': 115.0, 'snapshot_name': 'A'},
            {'period_id': '2025-H1', 'associate_id': 'EMP001', 'performance_rating': 130.0, 'bonus_allocation': 125.0, 'snapshot_name': 'A'},
        ]
        for data in snapshots_data:
            db_session.add(RatingSnapshot(**data))
        db_session.commit()

        emp_history = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.associate_id == 'EMP001'
        ).order_by(RatingSnapshot.period_id).all()

        assert len(emp_history) == 3
        assert emp_history[0].performance_rating == 100.0
        assert emp_history[1].performance_rating == 120.0
        assert emp_history[2].performance_rating == 130.0

    def test_upsert_snapshot(self, db_session):
        """Test updating an existing snapshot (re-import scenario)."""
        # Create initial snapshot
        snapshot = RatingSnapshot(
            period_id='2024-H1',
            associate_id='EMP001',
            bonus_allocation=100.0,
            snapshot_name='John Doe',
            has_full_details=False
        )
        db_session.add(snapshot)
        db_session.commit()

        # Simulate re-import with more data
        existing = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.period_id == '2024-H1',
            RatingSnapshot.associate_id == 'EMP001'
        ).first()

        existing.performance_rating = 125.0
        existing.justification = 'Great work'
        existing.has_full_details = True
        db_session.commit()

        # Verify update
        updated = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.period_id == '2024-H1',
            RatingSnapshot.associate_id == 'EMP001'
        ).first()

        assert updated.performance_rating == 125.0
        assert updated.justification == 'Great work'
        assert updated.has_full_details is True
