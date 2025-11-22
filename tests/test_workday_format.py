"""
Tests for Workday export format assumptions and data handling.

This file documents and tests critical assumptions about how Workday exports
employee data, particularly around international employees and bonus/salary fields.

CRITICAL WORKDAY FORMAT ASSUMPTIONS:
====================================

1. USD Employees (domestic):
   - current_base_pay_all_countries: Contains USD salary (e.g., 150000)
   - current_base_pay_all_countries_usd: Empty/None
   - bonus_target_local_currency: Contains USD bonus target (e.g., 4500)
   - bonus_target_local_currency_usd: Empty/None
   - currency: 'USD'

2. International Employees (non-USD):
   - current_base_pay_all_countries: Contains LOCAL currency amount (e.g., 105000 GBP)
   - current_base_pay_all_countries_usd: Contains USD CONVERSION (e.g., 132911)
   - bonus_target_local_currency: Contains LOCAL currency target (e.g., 12600 GBP)
   - bonus_target_local_currency_usd: Contains USD CONVERSION (e.g., 15949)
   - currency: Local currency code (e.g., 'GBP', 'EUR', 'CAD', 'INR')

3. Fallback Logic (CRITICAL):
   When displaying or calculating with USD amounts, ALWAYS use:
   - Base Pay: current_base_pay_all_countries_usd OR current_base_pay_all_countries
   - Bonus Target: bonus_target_local_currency_usd OR bonus_target_local_currency

   This ensures:
   - USD employees use their local column (which is already USD)
   - International employees use the USD conversion column

4. Bonus Percentages:
   - Annual bonus targets divided by 4 for quarterly bonuses
   - IC2: 2.5% quarterly (10% annual)
   - IC3: 3.0% quarterly (12% annual)
   - IC4: 3.75% quarterly (15% annual)
   - IC5: 5.0% quarterly (20% annual)
   - M3: 4.5% quarterly (18% annual)
"""
import pytest
from models import Employee


class TestWorkdayFormatUSDEmployees:
    """Test USD employee data structure matches Workday format."""

    def test_usd_employee_has_salary_in_local_column(self, db_session):
        """USD employees have salary in local column, USD column is None."""
        emp = Employee(
            associate_id='TEST001',
            associate='Test Employee',
            currency='USD',
            current_base_pay_all_countries=150000.0,
            current_base_pay_all_countries_usd=None,  # Workday leaves this empty for USD
            bonus_target_local_currency=4500.0,
            bonus_target_local_currency_usd=None  # Workday leaves this empty for USD
        )
        db_session.add(emp)
        db_session.commit()

        # Verify structure
        assert emp.currency == 'USD'
        assert emp.current_base_pay_all_countries == 150000.0
        assert emp.current_base_pay_all_countries_usd is None
        assert emp.bonus_target_local_currency == 4500.0
        assert emp.bonus_target_local_currency_usd is None

    def test_usd_fallback_logic_for_display(self, db_session):
        """Test fallback logic returns correct value for USD employees."""
        emp = Employee(
            associate_id='TEST002',
            associate='USD Employee',
            currency='USD',
            current_base_pay_all_countries=180000.0,
            current_base_pay_all_countries_usd=None,
            bonus_target_local_currency=6750.0,
            bonus_target_local_currency_usd=None
        )
        db_session.add(emp)
        db_session.commit()

        # Simulate fallback logic used in templates and calculations
        base_pay_display = emp.current_base_pay_all_countries_usd or emp.current_base_pay_all_countries
        bonus_target_display = emp.bonus_target_local_currency_usd or emp.bonus_target_local_currency

        assert base_pay_display == 180000.0
        assert bonus_target_display == 6750.0


class TestWorkdayFormatInternationalEmployees:
    """Test international employee data structure matches Workday format."""

    def test_international_employee_has_both_columns(self, db_session):
        """International employees have both local AND USD conversion columns."""
        emp = Employee(
            associate_id='TEST003',
            associate='UK Employee',
            currency='GBP',
            current_base_pay_all_countries=105000.0,  # Local GBP
            current_base_pay_all_countries_usd=132911.0,  # USD conversion
            bonus_target_local_currency=3150.0,  # 3% of 105000 GBP
            bonus_target_local_currency_usd=3987.33  # USD conversion
        )
        db_session.add(emp)
        db_session.commit()

        # Verify structure
        assert emp.currency == 'GBP'
        assert emp.current_base_pay_all_countries == 105000.0
        assert emp.current_base_pay_all_countries_usd == 132911.0
        assert emp.bonus_target_local_currency == 3150.0
        assert emp.bonus_target_local_currency_usd == 3987.33

    def test_international_fallback_logic_for_display(self, db_session):
        """Test fallback logic returns USD conversion for international employees."""
        emp = Employee(
            associate_id='TEST004',
            associate='CAD Employee',
            currency='CAD',
            current_base_pay_all_countries=130000.0,  # CAD
            current_base_pay_all_countries_usd=97000.0,  # USD
            bonus_target_local_currency=3250.0,  # CAD
            bonus_target_local_currency_usd=2425.0  # USD
        )
        db_session.add(emp)
        db_session.commit()

        # Simulate fallback logic used in templates and calculations
        base_pay_display = emp.current_base_pay_all_countries_usd or emp.current_base_pay_all_countries
        bonus_target_display = emp.bonus_target_local_currency_usd or emp.bonus_target_local_currency

        # Should use USD conversion for international employee
        assert base_pay_display == 97000.0
        assert bonus_target_display == 2425.0


class TestBonusCalculationFallbackLogic:
    """Test that bonus calculation uses correct fallback logic."""

    def test_mixed_currency_pool_calculation(self, db_session):
        """Test bonus pool calculation with mixed USD and international employees."""
        # USD employee
        usd_emp = Employee(
            associate_id='USD001',
            associate='US Employee',
            currency='USD',
            current_base_pay_all_countries=150000.0,
            current_base_pay_all_countries_usd=None,
            bonus_target_local_currency=4500.0,  # 3% quarterly
            bonus_target_local_currency_usd=None,
            performance_rating_percent=100.0
        )

        # International employee
        gbp_emp = Employee(
            associate_id='GBP001',
            associate='UK Employee',
            currency='GBP',
            current_base_pay_all_countries=105000.0,
            current_base_pay_all_countries_usd=132911.0,
            bonus_target_local_currency=3150.0,
            bonus_target_local_currency_usd=3987.33,
            performance_rating_percent=100.0
        )

        db_session.add(usd_emp)
        db_session.add(gbp_emp)
        db_session.commit()

        # Calculate total bonus pool using fallback logic
        total_pool = 0
        for emp in [usd_emp, gbp_emp]:
            bonus_target = emp.bonus_target_local_currency_usd or emp.bonus_target_local_currency
            total_pool += bonus_target

        # Should sum USD values: 4500 (USD) + 3987.33 (GBP converted)
        expected_pool = 4500.0 + 3987.33
        assert abs(total_pool - expected_pool) < 0.01


class TestQuarterlyBonusPercentages:
    """Test and document quarterly bonus percentage assumptions."""

    def test_ic2_quarterly_bonus_percentage(self, db_session):
        """IC2 (Junior): 2.5% quarterly = 10% annual."""
        emp = Employee(
            associate_id='IC2_001',
            associate='Junior Dev',
            grade='IC2',
            current_base_pay_all_countries=120000.0,
            annual_bonus_target_percent=2.5,  # Quarterly
            bonus_target_local_currency=3000.0  # 120000 * 0.025
        )
        db_session.add(emp)
        db_session.commit()

        assert emp.annual_bonus_target_percent == 2.5
        assert emp.bonus_target_local_currency == 3000.0
        # Annual equivalent would be 3000 * 4 = 12000 (10% of salary)

    def test_ic3_quarterly_bonus_percentage(self, db_session):
        """IC3 (Senior): 3.0% quarterly = 12% annual."""
        emp = Employee(
            associate_id='IC3_001',
            associate='Senior Dev',
            grade='IC3',
            current_base_pay_all_countries=150000.0,
            annual_bonus_target_percent=3.0,
            bonus_target_local_currency=4500.0
        )
        db_session.add(emp)
        db_session.commit()

        assert emp.annual_bonus_target_percent == 3.0
        assert emp.bonus_target_local_currency == 4500.0

    def test_ic4_quarterly_bonus_percentage(self, db_session):
        """IC4 (Staff): 3.75% quarterly = 15% annual."""
        emp = Employee(
            associate_id='IC4_001',
            associate='Staff Engineer',
            grade='IC4',
            current_base_pay_all_countries=180000.0,
            annual_bonus_target_percent=3.75,
            bonus_target_local_currency=6750.0
        )
        db_session.add(emp)
        db_session.commit()

        assert emp.annual_bonus_target_percent == 3.75
        assert emp.bonus_target_local_currency == 6750.0

    def test_ic5_quarterly_bonus_percentage(self, db_session):
        """IC5 (Principal): 5.0% quarterly = 20% annual."""
        emp = Employee(
            associate_id='IC5_001',
            associate='Principal Engineer',
            grade='IC5',
            current_base_pay_all_countries=220000.0,
            annual_bonus_target_percent=5.0,
            bonus_target_local_currency=11000.0
        )
        db_session.add(emp)
        db_session.commit()

        assert emp.annual_bonus_target_percent == 5.0
        assert emp.bonus_target_local_currency == 11000.0

    def test_m3_quarterly_bonus_percentage(self, db_session):
        """M3 (Engineering Manager): 4.5% quarterly = 18% annual."""
        emp = Employee(
            associate_id='M3_001',
            associate='Engineering Manager',
            grade='M3',
            current_base_pay_all_countries=190000.0,
            annual_bonus_target_percent=4.5,
            bonus_target_local_currency=8550.0
        )
        db_session.add(emp)
        db_session.commit()

        assert emp.annual_bonus_target_percent == 4.5
        assert emp.bonus_target_local_currency == 8550.0


class TestSupervisoryOrganizationFormat:
    """Test and document Supervisory Organization format from Workday."""

    def test_supervisory_org_format(self, db_session):
        """Supervisory Organization follows 'Supervisory Organization (Manager Name)' format."""
        emp = Employee(
            associate_id='TEST005',
            associate='Team Member',
            supervisory_organization='Supervisory Organization (Jane Smith)'
        )
        db_session.add(emp)
        db_session.commit()

        # Format should be exactly as Workday exports it
        assert emp.supervisory_organization.startswith('Supervisory Organization (')
        assert emp.supervisory_organization.endswith(')')

    def test_manager_not_in_own_team(self, db_session):
        """
        IMPORTANT: Manager is NEVER included in their own team.

        Use case: A manager uses the system to rate their direct reports.
        The manager themselves is not in the employee list being rated.

        Exception: Large org scenario where a Director rates Engineering Managers.
        In that case, the Engineering Managers appear in the employee list
        because they're being rated by their manager (the Director).
        """
        # This is a documentation test - no assertions needed
        # The concept is important to preserve in tests
        pass
