"""
Regression tests for Tenets by Job Level charts in /analytics.

These tests guard against the bug where HTML containers and backend data
existed but the Chart.js rendering JavaScript was missing, causing the
"Tenets by Job Level" section to show headers without any charts.
"""
import json
import pytest
from models import Employee


@pytest.fixture
def employees_across_job_levels(app, test_db):
    """Create employees spanning all three job levels with tenets.

    Job level categorisation (services/analytics.py):
      - Manager:   management_level contains 'manager'/'director', or has
                   direct reports via supervisory_organization
      - Senior IC: job title contains 'senior', 'principal', 'staff', 'lead'
      - Others:    everyone else

    Uses fictitious names per project convention.
    """
    SessionLocal, db_path = test_db
    session = SessionLocal()

    employees = [
        # --- Manager (detected via management_level) ---
        Employee(
            associate_id='MGR001',
            associate='Della Gate',
            supervisory_organization='Engineering (Della Gate)',
            current_job_profile='Engineering Manager',
            management_level='Manager',
            performance_rating_percent=115.0,
            bonus_target_local_currency=25000.0,
            tenets_strengths=json.dumps(['delete_more', 'campfire_cleaner', 'ship_to_learn']),
            tenets_improvements=json.dumps(['yagni', 'fail_fast']),
        ),
        # --- Senior IC (title contains "Senior") ---
        Employee(
            associate_id='SIC001',
            associate='Paige Duty',
            supervisory_organization='Engineering (Della Gate)',
            current_job_profile='Senior Software Developer',
            performance_rating_percent=130.0,
            bonus_target_local_currency=22000.0,
            tenets_strengths=json.dumps(['tests_or_hallucination', 'campfire_cleaner', 'rubber_duck']),
            tenets_improvements=json.dumps(['ship_to_learn', 'yagni']),
        ),
        # --- Senior IC (title contains "Principal") ---
        Employee(
            associate_id='SIC002',
            associate='Justin Time',
            supervisory_organization='Engineering (Della Gate)',
            current_job_profile='Principal Engineer',
            performance_rating_percent=140.0,
            bonus_target_local_currency=28000.0,
            tenets_strengths=json.dumps(['delete_more', 'automate_job', 'sleep_feature']),
            tenets_improvements=json.dumps(['rubber_duck', 'blame_process']),
        ),
        # --- Others (no management level, no senior keywords) ---
        Employee(
            associate_id='IC001',
            associate='Earl E. Bird',
            supervisory_organization='Engineering (Della Gate)',
            current_job_profile='Software Developer',
            performance_rating_percent=100.0,
            bonus_target_local_currency=15000.0,
            tenets_strengths=json.dumps(['ship_to_learn', 'fail_fast', 'rubber_duck']),
            tenets_improvements=json.dumps(['delete_more', 'campfire_cleaner']),
        ),
        Employee(
            associate_id='IC002',
            associate='Ella Vator',
            supervisory_organization='Engineering (Della Gate)',
            current_job_profile='Software Developer',
            performance_rating_percent=95.0,
            bonus_target_local_currency=14000.0,
            tenets_strengths=json.dumps(['campfire_cleaner', 'yagni', 'cattle_not_pets']),
            tenets_improvements=json.dumps(['tests_or_hallucination', 'strong_opinions']),
        ),
    ]

    for emp in employees:
        session.add(emp)
    session.commit()
    session.close()

    return employees


@pytest.fixture
def single_level_employees(app, test_db):
    """Create employees that all fall into one job level (Others).

    Used to verify the section is hidden when only one level is present.
    """
    SessionLocal, db_path = test_db
    session = SessionLocal()

    employees = [
        Employee(
            associate_id='IC010',
            associate='Ty Po',
            supervisory_organization='Engineering',
            current_job_profile='Software Developer',
            performance_rating_percent=100.0,
            bonus_target_local_currency=15000.0,
            tenets_strengths=json.dumps(['delete_more', 'campfire_cleaner', 'ship_to_learn']),
            tenets_improvements=json.dumps(['yagni', 'fail_fast']),
        ),
        Employee(
            associate_id='IC011',
            associate='Sue Flay',
            supervisory_organization='Engineering',
            current_job_profile='QA Engineer',
            performance_rating_percent=110.0,
            bonus_target_local_currency=14000.0,
            tenets_strengths=json.dumps(['tests_or_hallucination', 'rubber_duck', 'automate_job']),
            tenets_improvements=json.dumps(['delete_more', 'strong_opinions']),
        ),
    ]

    for emp in employees:
        session.add(emp)
    session.commit()
    session.close()

    return employees


# ---------- Section visibility ----------

class TestJobLevelTenetsSectionVisibility:
    """Test that the section appears/hides based on data."""

    def test_section_appears_with_multiple_levels(
        self, client, employees_across_job_levels
    ):
        """Section shows when employees span 2+ job levels."""
        response = client.get('/analytics')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert 'Tenets by Job Level' in html

    def test_section_hidden_with_single_level(
        self, client, single_level_employees
    ):
        """Section hidden when all employees fall into one level."""
        response = client.get('/analytics')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert 'Tenets by Job Level' not in html

    def test_section_hidden_without_tenets(self, client, populated_db):
        """Section hidden when no employees have tenets at all."""
        response = client.get('/analytics')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert 'Tenets by Job Level' not in html


# ---------- Chart containers and JS rendering ----------

class TestJobLevelTenetsChartRendering:
    """Regression tests for the Chart.js rendering code.

    The original bug: HTML containers existed but the JavaScript to
    instantiate Chart.js butterfly charts was never written.
    """

    def test_chart_container_divs_present(
        self, client, employees_across_job_levels
    ):
        """Container divs with correct IDs exist for Chart.js to target."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        assert 'jobLevelTenetsChart-Manager' in html
        assert 'jobLevelTenetsChart-Senior-IC' in html
        assert 'jobLevelTenetsChart-Others' in html

    def test_js_data_variable_serialized(
        self, client, employees_across_job_levels
    ):
        """jobLevelTenetsData JS variable is present with JSON data."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        assert 'jobLevelTenetsData' in html

    def test_render_function_defined(
        self, client, employees_across_job_levels
    ):
        """renderButterflyChart function is defined in the page JS."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        assert 'function renderButterflyChart' in html

    def test_render_function_invoked_for_each_level(
        self, client, employees_across_job_levels
    ):
        """renderButterflyChart is called for Manager, Senior IC, Others."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # The JS iterates ['Manager', 'Senior IC', 'Others'] and calls
        # renderButterflyChart for each — check the iteration exists
        assert "['Manager', 'Senior IC', 'Others']" in html
        assert 'renderButterflyChart(' in html

    def test_chart_js_config_uses_butterfly_pattern(
        self, client, employees_across_job_levels
    ):
        """Charts use horizontal bars (indexAxis: 'y') like the main chart."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # The renderButterflyChart function should configure Chart.js
        # with indexAxis: 'y' for horizontal butterfly bars
        assert "indexAxis: 'y'" in html


# ---------- Employee counts and level labels ----------

class TestJobLevelTenetsContent:
    """Test that the right content is rendered per level."""

    def test_all_three_level_labels_shown(
        self, client, employees_across_job_levels
    ):
        """All three level headings appear when data spans all levels."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # Level headings inside the "Tenets by Job Level" section
        # Manager (1 employee), Senior IC (2 employees), Others (2 employees)
        assert 'Manager' in html
        assert 'Senior IC' in html
        assert 'Others' in html

    def test_employee_counts_per_level(
        self, client, employees_across_job_levels
    ):
        """Employee counts shown next to each level heading are correct."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # Template renders: (N employee/employees)
        # Manager = 1 (MGR001), Senior IC = 2 (SIC001 + SIC002),
        # Others = 2 (IC001 + IC002)
        assert '(1 employee)' in html
        assert '(2 employees)' in html

    def test_level_definitions_shown(
        self, client, employees_across_job_levels
    ):
        """Definition text explains each level's criteria."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        assert 'Has direct reports' in html
        assert 'Senior, Principal, Staff, or Lead' in html
        assert 'All other individual contributors' in html

    def test_tenet_data_includes_names(
        self, client, employees_across_job_levels, sample_tenets
    ):
        """Tenet names from config appear in serialized JSON data."""
        response = client.get('/analytics')
        html = response.data.decode('utf-8')

        # With sample_tenets loaded, tenet IDs get resolved to names
        assert 'Delete More Than You Add' in html
        assert 'Leave the Campfire Cleaner' in html


# ---------- Backend data computation ----------

class TestJobLevelTenetsBackend:
    """Unit-test the analytics computation for job-level tenets."""

    def test_categorize_job_level_manager(self):
        """Employees with management_level='Manager' are Managers."""
        from services.analytics import categorize_job_level

        emp = {
            'Associate ID': 'MGR001',
            'Current Job Profile': 'Engineering Manager',
            'management_level': 'Manager',
        }
        assert categorize_job_level(emp, [emp]) == 'Manager'

    def test_categorize_job_level_director(self):
        """Employees with management_level='Director' are Managers."""
        from services.analytics import categorize_job_level

        emp = {
            'Associate ID': 'DIR001',
            'Current Job Profile': 'Director of Engineering',
            'management_level': 'Director',
        }
        assert categorize_job_level(emp, [emp]) == 'Manager'

    def test_categorize_job_level_senior_ic(self):
        """Title containing 'Senior' maps to Senior IC."""
        from services.analytics import categorize_job_level

        emp = {
            'Associate ID': 'SIC001',
            'Current Job Profile': 'Senior Software Developer',
        }
        assert categorize_job_level(emp, [emp]) == 'Senior IC'

    def test_categorize_job_level_principal(self):
        """Title containing 'Principal' maps to Senior IC."""
        from services.analytics import categorize_job_level

        emp = {
            'Associate ID': 'SIC002',
            'Current Job Profile': 'Principal Engineer',
        }
        assert categorize_job_level(emp, [emp]) == 'Senior IC'

    def test_categorize_job_level_staff(self):
        """Title containing 'Staff' maps to Senior IC."""
        from services.analytics import categorize_job_level

        emp = {
            'Associate ID': 'SIC003',
            'Current Job Profile': 'Staff Engineer',
        }
        assert categorize_job_level(emp, [emp]) == 'Senior IC'

    def test_categorize_job_level_lead(self):
        """Title containing 'Lead' maps to Senior IC."""
        from services.analytics import categorize_job_level

        emp = {
            'Associate ID': 'SIC004',
            'Current Job Profile': 'Lead Developer',
        }
        assert categorize_job_level(emp, [emp]) == 'Senior IC'

    def test_categorize_job_level_others(self):
        """Plain title with no management level maps to Others."""
        from services.analytics import categorize_job_level

        emp = {
            'Associate ID': 'IC001',
            'Current Job Profile': 'Software Developer',
        }
        assert categorize_job_level(emp, [emp]) == 'Others'

    def test_job_level_summary_structure(self):
        """calculate_tenets_analytics returns well-formed job_level data."""
        from services.analytics import calculate_tenets_analytics

        team_data = [
            {
                'Associate ID': 'MGR001',
                'Current Job Profile': 'Engineering Manager',
                'management_level': 'Manager',
                'tenets_strengths': json.dumps(['delete_more', 'ship_to_learn']),
                'tenets_improvements': json.dumps(['yagni']),
                'talent_tenets_strengths': None,
                'talent_tenets_improvements': None,
                'Supervisory Organization': 'Engineering',
            },
            {
                'Associate ID': 'IC001',
                'Current Job Profile': 'Software Developer',
                'tenets_strengths': json.dumps(['fail_fast']),
                'tenets_improvements': json.dumps(['delete_more', 'rubber_duck']),
                'talent_tenets_strengths': None,
                'talent_tenets_improvements': None,
                'Supervisory Organization': 'Engineering',
            },
        ]

        tenets_map = {
            'delete_more': {'name': 'Delete More', 'category': 'Craft'},
            'ship_to_learn': {'name': 'Ship It', 'category': 'Velocity'},
            'yagni': {'name': 'YAGNI', 'category': 'Velocity'},
            'fail_fast': {'name': 'Fail Fast', 'category': 'Velocity'},
            'rubber_duck': {'name': 'Rubber Duck', 'category': 'Collab'},
        }

        _, _, _, job_level_summary = calculate_tenets_analytics(
            team_data, tenets_map
        )

        # Should have two levels (Manager + Others)
        assert 'Manager' in job_level_summary
        assert 'Others' in job_level_summary
        assert len(job_level_summary) == 2

        # Each level has 'tenets' list and 'employees_with_tenets' count
        mgr = job_level_summary['Manager']
        assert mgr['employees_with_tenets'] == 1
        assert isinstance(mgr['tenets'], list)
        assert len(mgr['tenets']) > 0

        # Each tenet entry has required keys
        tenet_entry = mgr['tenets'][0]
        for key in ('id', 'name', 'category', 'strength_count',
                     'improvement_count', 'total_mentions'):
            assert key in tenet_entry, f"Missing key: {key}"

    def test_weighted_counts_sum_to_three(self):
        """Each employee contributes exactly 3.0 to strengths total."""
        from services.analytics import calculate_tenets_analytics

        team_data = [
            {
                'Associate ID': 'IC001',
                'Current Job Profile': 'Software Developer',
                'tenets_strengths': json.dumps(['t1', 't2', 't3']),
                'tenets_improvements': json.dumps(['t4', 't5']),
                'talent_tenets_strengths': None,
                'talent_tenets_improvements': None,
                'Supervisory Organization': 'Eng',
            },
        ]
        tenets_map = {
            't1': {'name': 'T1', 'category': 'C'},
            't2': {'name': 'T2', 'category': 'C'},
            't3': {'name': 'T3', 'category': 'C'},
            't4': {'name': 'T4', 'category': 'C'},
            't5': {'name': 'T5', 'category': 'C'},
        }

        _, _, _, job_level_summary = calculate_tenets_analytics(
            team_data, tenets_map
        )

        others = job_level_summary['Others']
        strength_total = sum(
            t['strength_count'] for t in others['tenets']
        )
        improvement_total = sum(
            t['improvement_count'] for t in others['tenets']
        )

        assert abs(strength_total - 3.0) < 0.001
        assert abs(improvement_total - 3.0) < 0.001
