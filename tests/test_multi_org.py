"""
Tests for multi-organization scenarios.

Tests the system's ability to handle multiple managers with different teams,
different supervisory organizations, and proper segmentation in analytics.
"""
import pytest
from models import Employee


@pytest.fixture
def multi_org_employees():
    """
    Sample data representing multiple managers/organizations.
    Simulates a realistic Workday export with 5 different organizations.
    """
    return [
        # Engineering - Platform Team (Manager 1)
        {
            'associate_id': 'EMP101',
            'associate': 'Alice Anderson',
            'supervisory_organization': 'Engineering - Platform',
            'current_job_profile': 'Staff Engineer',
            'current_base_pay_all_countries': 180000.0,
            'current_base_pay_all_countries_usd': 180000.0,
            'currency': 'USD',
            'grade': 'IC4',
            'annual_bonus_target_percent': 15.0,
            'bonus_target_local_currency': 27000.0,
            'bonus_target_local_currency_usd': None,
            'performance_rating_percent': 130.0,
            'justification': 'Exceptional technical leadership'
        },
        {
            'associate_id': 'EMP102',
            'associate': 'Bob Baker',
            'supervisory_organization': 'Engineering - Platform',
            'current_job_profile': 'Senior Software Engineer',
            'current_base_pay_all_countries': 150000.0,
            'current_base_pay_all_countries_usd': 150000.0,
            'currency': 'USD',
            'grade': 'IC3',
            'annual_bonus_target_percent': 12.0,
            'bonus_target_local_currency': 18000.0,
            'bonus_target_local_currency_usd': None,
            'performance_rating_percent': 110.0,
            'justification': 'Solid performance'
        },
        {
            'associate_id': 'EMP103',
            'associate': 'Carol Chen',
            'supervisory_organization': 'Engineering - Platform',
            'current_job_profile': 'Software Engineer',
            'current_base_pay_all_countries': 120000.0,
            'current_base_pay_all_countries_usd': 120000.0,
            'currency': 'USD',
            'grade': 'IC2',
            'annual_bonus_target_percent': 10.0,
            'bonus_target_local_currency': 12000.0,
            'bonus_target_local_currency_usd': None,
            'performance_rating_percent': 95.0,
            'justification': 'Good work, needs more experience'
        },

        # Engineering - Frontend Team (Manager 2)
        {
            'associate_id': 'EMP201',
            'associate': 'David Davis',
            'supervisory_organization': 'Engineering - Frontend',
            'current_job_profile': 'Principal Engineer',
            'current_base_pay_all_countries': 220000.0,
            'current_base_pay_all_countries_usd': 220000.0,
            'currency': 'USD',
            'grade': 'IC5',
            'annual_bonus_target_percent': 20.0,
            'bonus_target_local_currency': 44000.0,
            'bonus_target_local_currency_usd': None,
            'performance_rating_percent': 140.0,
            'justification': 'Outstanding leadership and innovation'
        },
        {
            'associate_id': 'EMP202',
            'associate': 'Emma Evans',
            'supervisory_organization': 'Engineering - Frontend',
            'current_job_profile': 'Senior Software Engineer',
            'current_base_pay_all_countries': 145000.0,
            'current_base_pay_all_countries_usd': 145000.0,
            'currency': 'USD',
            'grade': 'IC3',
            'annual_bonus_target_percent': 12.0,
            'bonus_target_local_currency': 17400.0,
            'bonus_target_local_currency_usd': None,
            'performance_rating_percent': 100.0,
            'justification': 'Met all expectations'
        },

        # Product Management (Manager 3)
        {
            'associate_id': 'EMP301',
            'associate': 'Frank Foster',
            'supervisory_organization': 'Product Management',
            'current_job_profile': 'Senior Product Manager',
            'current_base_pay_all_countries': 165000.0,
            'current_base_pay_all_countries_usd': 165000.0,
            'currency': 'USD',
            'grade': 'IC4',
            'annual_bonus_target_percent': 15.0,
            'bonus_target_local_currency': 24750.0,
            'bonus_target_local_currency_usd': None,
            'performance_rating_percent': 120.0,
            'justification': 'Great product leadership'
        },
        {
            'associate_id': 'EMP302',
            'associate': 'Grace Green',
            'supervisory_organization': 'Product Management',
            'current_job_profile': 'Product Manager',
            'current_base_pay_all_countries': 130000.0,
            'current_base_pay_all_countries_usd': 130000.0,
            'currency': 'USD',
            'grade': 'IC3',
            'annual_bonus_target_percent': 12.0,
            'bonus_target_local_currency': 15600.0,
            'bonus_target_local_currency_usd': None,
            'performance_rating_percent': 105.0,
            'justification': 'Strong execution'
        },
        {
            'associate_id': 'EMP303',
            'associate': 'Henry Hill',
            'supervisory_organization': 'Product Management',
            'current_job_profile': 'Product Manager',
            'current_base_pay_all_countries': 125000.0,
            'current_base_pay_all_countries_usd': 125000.0,
            'currency': 'USD',
            'grade': 'IC3',
            'annual_bonus_target_percent': 12.0,
            'bonus_target_local_currency': 15000.0,
            'bonus_target_local_currency_usd': None,
            'performance_rating_percent': 85.0,
            'justification': 'Needs improvement in stakeholder management'
        },

        # Engineering - Data Team (Manager 4) - International team
        {
            'associate_id': 'EMP401',
            'associate': 'Iris Ibrahim',
            'supervisory_organization': 'Engineering - Data',
            'current_job_profile': 'Senior Data Engineer',
            'current_base_pay_all_countries': 105000.0,  # GBP
            'current_base_pay_all_countries_usd': 132911.0,  # Converted
            'currency': 'GBP',
            'grade': 'IC3',
            'annual_bonus_target_percent': 12.0,
            'bonus_target_local_currency': 12600.0,  # GBP
            'bonus_target_local_currency_usd': 15949.0,  # Converted
            'performance_rating_percent': 115.0,
            'justification': 'Excellent data pipeline work'
        },
        {
            'associate_id': 'EMP402',
            'associate': 'Jack Jones',
            'supervisory_organization': 'Engineering - Data',
            'current_job_profile': 'Data Engineer',
            'current_base_pay_all_countries': 78000.0,  # GBP
            'current_base_pay_all_countries_usd': 98734.0,  # Converted
            'currency': 'GBP',
            'grade': 'IC2',
            'annual_bonus_target_percent': 10.0,
            'bonus_target_local_currency': 7800.0,  # GBP
            'bonus_target_local_currency_usd': 9873.0,  # Converted
            'performance_rating_percent': 90.0,
            'justification': 'Good progress, needs more initiative'
        },

        # Engineering - Security Team (Manager 5)
        {
            'associate_id': 'EMP501',
            'associate': 'Kelly Kim',
            'supervisory_organization': 'Engineering - Security',
            'current_job_profile': 'Staff Security Engineer',
            'current_base_pay_all_countries': 190000.0,
            'current_base_pay_all_countries_usd': 190000.0,
            'currency': 'USD',
            'grade': 'IC4',
            'annual_bonus_target_percent': 15.0,
            'bonus_target_local_currency': 28500.0,
            'bonus_target_local_currency_usd': None,
            'performance_rating_percent': 135.0,
            'justification': 'Critical security improvements delivered'
        },
        {
            'associate_id': 'EMP502',
            'associate': 'Liam Lee',
            'supervisory_organization': 'Engineering - Security',
            'current_job_profile': 'Security Engineer',
            'current_base_pay_all_countries': 140000.0,
            'current_base_pay_all_countries_usd': 140000.0,
            'currency': 'USD',
            'grade': 'IC3',
            'annual_bonus_target_percent': 12.0,
            'bonus_target_local_currency': 16800.0,
            'bonus_target_local_currency_usd': None,
            'performance_rating_percent': 108.0,
            'justification': 'Solid security work'
        },
        {
            'associate_id': 'EMP503',
            'associate': 'Maya Martinez',
            'supervisory_organization': 'Engineering - Security',
            'current_job_profile': 'Security Engineer',
            'current_base_pay_all_countries': 135000.0,
            'current_base_pay_all_countries_usd': 135000.0,
            'currency': 'USD',
            'grade': 'IC3',
            'annual_bonus_target_percent': 12.0,
            'bonus_target_local_currency': 16200.0,
            'bonus_target_local_currency_usd': None,
            'performance_rating_percent': 75.0,
            'justification': 'Performance concerns, needs improvement plan'
        }
    ]


@pytest.fixture
def populated_multi_org_db(db_session, multi_org_employees):
    """Database populated with multi-organization employee data."""
    for emp_data in multi_org_employees:
        employee = Employee(**emp_data)
        db_session.add(employee)

    db_session.commit()
    return db_session


class TestMultiOrganization:
    """Test suite for multi-organization scenarios."""

    def test_all_organizations_loaded(self, populated_multi_org_db):
        """Test that all employees from multiple organizations are loaded."""
        employees = populated_multi_org_db.query(Employee).all()
        assert len(employees) == 13  # Total count from fixture

        # Verify all 5 organizations are present
        orgs = set(emp.supervisory_organization for emp in employees)
        assert len(orgs) == 5
        assert 'Engineering - Platform' in orgs
        assert 'Engineering - Frontend' in orgs
        assert 'Product Management' in orgs
        assert 'Engineering - Data' in orgs
        assert 'Engineering - Security' in orgs

    def test_organization_counts(self, populated_multi_org_db):
        """Test employee counts per organization."""
        employees = populated_multi_org_db.query(Employee).all()

        org_counts = {}
        for emp in employees:
            org = emp.supervisory_organization
            org_counts[org] = org_counts.get(org, 0) + 1

        assert org_counts['Engineering - Platform'] == 3
        assert org_counts['Engineering - Frontend'] == 2
        assert org_counts['Product Management'] == 3
        assert org_counts['Engineering - Data'] == 2
        assert org_counts['Engineering - Security'] == 3

    def test_all_employees_have_ratings(self, populated_multi_org_db):
        """Test that all employees across all orgs have performance ratings."""
        employees = populated_multi_org_db.query(Employee).all()

        rated = [emp for emp in employees if emp.performance_rating_percent is not None]
        assert len(rated) == 13  # All employees should be rated

    def test_analytics_with_multiple_orgs(self, client, db_session, multi_org_employees):
        """Test analytics page correctly handles multiple organizations."""
        # Populate database
        for emp_data in multi_org_employees:
            employee = Employee(**emp_data)
            db_session.add(employee)
        db_session.commit()

        response = client.get('/analytics')
        assert response.status_code == 200

        # Verify response contains data (actual verification would need HTML parsing)
        assert b'Engineering - Platform' in response.data
        assert b'Engineering - Frontend' in response.data
        assert b'Product Management' in response.data
        assert b'Engineering - Data' in response.data
        assert b'Engineering - Security' in response.data

    def test_department_averages_across_orgs(self, populated_multi_org_db):
        """Test that department averages are calculated correctly for each org."""
        employees = populated_multi_org_db.query(Employee).all()

        # Calculate averages per organization
        org_ratings = {}
        for emp in employees:
            org = emp.supervisory_organization
            if org not in org_ratings:
                org_ratings[org] = []
            if emp.performance_rating_percent:
                org_ratings[org].append(emp.performance_rating_percent)

        # Engineering - Platform: 130, 110, 95 -> avg 111.67
        platform_avg = sum(org_ratings['Engineering - Platform']) / len(org_ratings['Engineering - Platform'])
        assert 111.0 <= platform_avg <= 112.0

        # Engineering - Frontend: 140, 100 -> avg 120
        frontend_avg = sum(org_ratings['Engineering - Frontend']) / len(org_ratings['Engineering - Frontend'])
        assert frontend_avg == 120.0

        # Product Management: 120, 105, 85 -> avg 103.33
        product_avg = sum(org_ratings['Product Management']) / len(org_ratings['Product Management'])
        assert 103.0 <= product_avg <= 104.0

        # Engineering - Data: 115, 90 -> avg 102.5
        data_avg = sum(org_ratings['Engineering - Data']) / len(org_ratings['Engineering - Data'])
        assert data_avg == 102.5

        # Engineering - Security: 135, 108, 75 -> avg 106
        security_avg = sum(org_ratings['Engineering - Security']) / len(org_ratings['Engineering - Security'])
        assert security_avg == 106.0

    def test_bonus_calculation_across_orgs(self, client, db_session, multi_org_employees):
        """Test that bonus calculation works correctly across multiple organizations."""
        # Populate database
        for emp_data in multi_org_employees:
            employee = Employee(**emp_data)
            db_session.add(employee)
        db_session.commit()

        response = client.get('/bonus-calculation')
        assert response.status_code == 200

        # Should show all 14 employees
        assert b'Rated Employees' in response.data
        # Verify some employee names from different orgs appear
        assert b'Alice Anderson' in response.data  # Platform
        assert b'David Davis' in response.data     # Frontend
        assert b'Frank Foster' in response.data    # Product
        assert b'Iris Ibrahim' in response.data    # Data
        assert b'Kelly Kim' in response.data       # Security

    def test_bonus_pool_calculation_multi_org(self, populated_multi_org_db):
        """Test that total bonus pool is correctly calculated across all orgs."""
        employees = populated_multi_org_db.query(Employee).all()

        # Calculate total pool
        total_pool = 0
        for emp in employees:
            # Use USD version if available, otherwise local (which is USD for US employees)
            bonus_target = emp.bonus_target_local_currency_usd or emp.bonus_target_local_currency
            if bonus_target:
                total_pool += bonus_target

        # Expected total (sum of all bonus targets in USD)
        expected = (27000 + 18000 + 12000 +  # Platform
                   44000 + 17400 +            # Frontend
                   24750 + 15600 + 15000 +    # Product
                   15949 + 9873 +             # Data (converted from GBP)
                   28500 + 16800 + 16200)     # Security

        assert abs(total_pool - expected) < 1.0  # Allow for small rounding differences

    def test_international_employees_in_multi_org(self, populated_multi_org_db):
        """Test that international employees are properly handled in multi-org setup."""
        employees = populated_multi_org_db.query(Employee).all()

        # Find international employees (non-USD)
        international = [emp for emp in employees if emp.currency != 'USD']
        assert len(international) == 2  # Iris and Jack from Data team

        # Verify they have both local and USD amounts
        for emp in international:
            assert emp.currency == 'GBP'
            assert emp.bonus_target_local_currency is not None
            assert emp.bonus_target_local_currency_usd is not None
            assert emp.current_base_pay_all_countries is not None
            assert emp.current_base_pay_all_countries_usd is not None

    def test_rating_distribution_across_orgs(self, populated_multi_org_db):
        """Test rating distribution when employees span multiple organizations."""
        employees = populated_multi_org_db.query(Employee).all()

        # Categorize ratings
        high = [e for e in employees if e.performance_rating_percent and e.performance_rating_percent > 120]
        solid = [e for e in employees if e.performance_rating_percent and 90 <= e.performance_rating_percent <= 120]
        needs_improvement = [e for e in employees if e.performance_rating_percent and e.performance_rating_percent < 90]

        # High performers (>120): 130, 140, 135 = 3
        assert len(high) == 3

        # Solid performers (90-120): 110, 95, 100, 120, 115, 90, 105, 108 = 8
        assert len(solid) == 8

        # Needs improvement (<90): 85, 75 = 2
        assert len(needs_improvement) == 2

    def test_calibration_with_multi_org(self, client, db_session, multi_org_employees):
        """Test that calibration guidance works with multi-org data."""
        # Populate database
        for emp_data in multi_org_employees:
            employee = Employee(**emp_data)
            db_session.add(employee)
        db_session.commit()

        response = client.get('/analytics')
        assert response.status_code == 200

        # Should show calibration section (check for text that appears in the section)
        assert b'Calibration' in response.data or b'calibration' in response.data
        assert b'Performance' in response.data

    def test_job_profile_distribution_across_orgs(self, populated_multi_org_db):
        """Test that different job profiles exist across organizations."""
        employees = populated_multi_org_db.query(Employee).all()

        job_profiles = set(emp.current_job_profile for emp in employees)

        # Should have multiple different job profiles
        assert len(job_profiles) >= 8
        assert 'Staff Engineer' in job_profiles
        assert 'Principal Engineer' in job_profiles
        assert 'Senior Product Manager' in job_profiles
        assert 'Product Manager' in job_profiles
        assert 'Senior Data Engineer' in job_profiles
        assert 'Staff Security Engineer' in job_profiles

    def test_grade_distribution_across_orgs(self, populated_multi_org_db):
        """Test that multiple grade levels exist across organizations."""
        employees = populated_multi_org_db.query(Employee).all()

        grades = set(emp.grade for emp in employees if emp.grade)

        # Should have IC2 through IC5
        assert 'IC2' in grades
        assert 'IC3' in grades
        assert 'IC4' in grades
        assert 'IC5' in grades

    def test_export_includes_all_orgs(self, client, db_session, multi_org_employees):
        """Test that CSV export includes employees from all organizations."""
        # Populate database
        for emp_data in multi_org_employees:
            employee = Employee(**emp_data)
            db_session.add(employee)
        db_session.commit()

        response = client.get('/export')
        assert response.status_code == 200

        # Verify response indicates success
        json_data = response.get_json()
        assert json_data['success'] is True
        assert 'filename' in json_data


class TestMultiOrgEdgeCases:
    """Test edge cases specific to multi-organization scenarios."""

    def test_empty_organization(self, db_session):
        """Test handling when one organization has no rated employees."""
        employees = [
            {
                'associate_id': 'EMP001',
                'associate': 'Alice',
                'supervisory_organization': 'Org A',
                'current_job_profile': 'Engineer',
                'performance_rating_percent': 100.0,
                'bonus_target_local_currency': 10000.0
            },
            {
                'associate_id': 'EMP002',
                'associate': 'Bob',
                'supervisory_organization': 'Org B',
                'current_job_profile': 'Engineer',
                'performance_rating_percent': None,  # Not rated
                'bonus_target_local_currency': 10000.0
            }
        ]

        for emp_data in employees:
            employee = Employee(**emp_data)
            db_session.add(employee)
        db_session.commit()

        all_employees = db_session.query(Employee).all()
        assert len(all_employees) == 2

        rated = [e for e in all_employees if e.performance_rating_percent is not None]
        assert len(rated) == 1

    def test_single_employee_organization(self, db_session):
        """Test organization with only one employee."""
        employee = Employee(
            associate_id='EMP001',
            associate='Solo Employee',
            supervisory_organization='Small Team',
            current_job_profile='Engineer',
            performance_rating_percent=100.0,
            bonus_target_local_currency=15000.0
        )
        db_session.add(employee)
        db_session.commit()

        employees = db_session.query(Employee).all()
        assert len(employees) == 1
        assert employees[0].supervisory_organization == 'Small Team'

    def test_organization_name_variations(self, db_session):
        """Test handling of organization names with special characters."""
        orgs = [
            'Engineering - AI/ML',
            'Product & Design',
            'Sales (West)',
            'Customer Success - Enterprise'
        ]

        for i, org in enumerate(orgs):
            employee = Employee(
                associate_id=f'EMP00{i+1}',
                associate=f'Employee {i+1}',
                supervisory_organization=org,
                current_job_profile='Engineer',
                performance_rating_percent=100.0,
                bonus_target_local_currency=10000.0
            )
            db_session.add(employee)

        db_session.commit()

        employees = db_session.query(Employee).all()
        assert len(employees) == 4

        retrieved_orgs = set(emp.supervisory_organization for emp in employees)
        assert len(retrieved_orgs) == 4
        assert 'Engineering - AI/ML' in retrieved_orgs
        assert 'Product & Design' in retrieved_orgs
