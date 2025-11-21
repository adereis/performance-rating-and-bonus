"""
Tests for the Employee model and database operations.
"""
import pytest
from datetime import datetime
from models import Employee


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
