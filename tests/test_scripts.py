"""
Tests for sample data generation scripts.

These tests verify that the scripts in scripts/ can be imported and run
correctly, including proper handling of imports from the parent directory.
"""
import json
import pytest
import os
import sys
import tempfile
import importlib.util

# Path to demo templates (generated at Docker build time, not in source repo)
DEMO_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'demo-templates')
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')


def load_script(script_name):
    """
    Load a script as a module using importlib.

    This allows loading scripts with kebab-case names that can't be
    imported normally.
    """
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    # Create a valid module name from the script name
    module_name = script_name.replace('-', '_').replace('.py', '')

    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class TestGenerateSampleXlsx:
    """Tests for scripts/generate-sample-xlsx.py"""

    def test_script_can_be_imported(self):
        """Test that the script can be imported without errors"""
        module = load_script('generate-sample-xlsx.py')
        assert hasattr(module, 'create_bonus_headers')
        assert hasattr(module, 'create_bonus_xlsx')

    def test_creates_xlsx_file(self):
        """Test that generate-sample-xlsx generates a valid XLSX file"""
        import openpyxl
        module = load_script('generate-sample-xlsx.py')

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, 'test-sample.xlsx')

            wb = openpyxl.Workbook()
            sheet = wb.active
            module.create_bonus_headers(sheet)

            # Verify headers were created
            # Row 8 has column headers in new Workday format (2025+)
            headers = [cell.value for cell in sheet[8]]
            assert 'Associate' in headers
            assert 'Direct Manager' in headers
            assert 'Job Title' in headers

            # Verify metadata rows exist (new format structure)
            assert 'RH Compensation Review Process' in str(sheet[1][0].value)
            assert 'Compensation Review' in str(sheet[3][1].value)

            wb.save(output_file)
            assert os.path.exists(output_file)

    def test_small_team_data(self):
        """Test that small team data function returns properly structured data"""
        module = load_script('generate-sample-xlsx.py')

        assert hasattr(module, 'get_small_team_data')
        small_team = module.get_small_team_data()

        assert len(small_team) > 0

        for emp in small_team:
            assert 'associate' in emp
            assert 'job_profile' in emp
            assert 'salary' in emp


class TestPopulateSampleDb:
    """Tests for scripts/populate-sample-db.py"""

    def test_script_can_be_imported(self):
        """Test that the script can be imported without errors"""
        module = load_script('populate-sample-db.py')
        assert hasattr(module, 'SMALL_TEAM_RATINGS')
        assert hasattr(module, 'LARGE_ORG_RATINGS')

    def test_small_team_ratings_defined(self):
        """Test that small team ratings data is properly structured"""
        module = load_script('populate-sample-db.py')
        ratings = module.SMALL_TEAM_RATINGS

        assert len(ratings) > 0

        for name, data in ratings.items():
            assert isinstance(data, tuple)
            assert len(data) == 2
            rating, justification = data
            assert isinstance(rating, int)
            assert 0 <= rating <= 200
            assert justification is None or isinstance(justification, str)

    def test_large_org_ratings_defined(self):
        """Test that large org ratings data is properly structured"""
        module = load_script('populate-sample-db.py')
        ratings = module.LARGE_ORG_RATINGS
        small_ratings = module.SMALL_TEAM_RATINGS

        assert len(ratings) > 0
        assert len(ratings) >= len(small_ratings)


class TestScriptImportPaths:
    """Test that scripts handle import paths correctly for standalone execution"""

    def test_generate_sample_xlsx_path_handling(self):
        """Test that generate-sample-xlsx.py adds parent to sys.path"""
        script_path = os.path.join(SCRIPTS_DIR, 'generate-sample-xlsx.py')

        with open(script_path, 'r') as f:
            content = f.read()

        assert 'sys.path.insert' in content
        assert 'os.path.dirname' in content

    def test_populate_sample_db_path_handling(self):
        """Test that populate-sample-db.py adds parent to sys.path"""
        script_path = os.path.join(SCRIPTS_DIR, 'populate-sample-db.py')

        with open(script_path, 'r') as f:
            content = f.read()

        assert 'sys.path.insert' in content
        assert 'os.path.dirname' in content


class TestScriptHelpSupport:
    """Test that scripts have proper --help support via argparse"""

    def test_generate_sample_xlsx_has_main_function(self):
        """Test that generate-sample-xlsx.py has a main() function with argparse"""
        module = load_script('generate-sample-xlsx.py')
        assert hasattr(module, 'main')

        script_path = os.path.join(SCRIPTS_DIR, 'generate-sample-xlsx.py')
        with open(script_path, 'r') as f:
            content = f.read()
        assert 'argparse' in content
        assert 'ArgumentParser' in content

    def test_populate_sample_db_has_main_function(self):
        """Test that populate-sample-db.py has a main() function with argparse"""
        module = load_script('populate-sample-db.py')
        assert hasattr(module, 'main')

        script_path = os.path.join(SCRIPTS_DIR, 'populate-sample-db.py')
        with open(script_path, 'r') as f:
            content = f.read()
        assert 'argparse' in content
        assert 'ArgumentParser' in content


class TestGenerateDemoTemplates:
    """Tests for scripts/generate-demo-templates.py"""

    def test_script_can_be_imported(self):
        """Test that the script can be imported without errors"""
        module = load_script('generate-demo-templates.py')
        assert hasattr(module, 'get_small_team_employees')
        assert hasattr(module, 'get_large_team_employees')
        assert hasattr(module, 'create_template_database')

    def test_small_team_structure(self):
        """Test that small team data has correct structure and no manager as employee"""
        module = load_script('generate-demo-templates.py')
        employees = module.get_small_team_employees()

        assert len(employees) == 12, f"Expected 12 employees, got {len(employees)}"

        required_fields = [
            'associate_id', 'associate', 'supervisory_organization',
            'current_job_profile', 'performance_rating_percent', 'justification'
        ]
        for emp in employees:
            for field in required_fields:
                assert field in emp, f"Missing field {field} in employee {emp.get('associate', 'unknown')}"

        employee_names = [emp['associate'] for emp in employees]
        assert 'Della Gate' not in employee_names, \
            "Della Gate should not be an employee - she is the manager using the system"

        for emp in employees:
            assert 'Della Gate' in emp['supervisory_organization'], \
                f"Employee {emp['associate']} should be under Della Gate's organization"

    def test_large_team_structure(self):
        """Test that large team data includes managers as employees"""
        module = load_script('generate-demo-templates.py')
        employees = module.get_large_team_employees()

        assert len(employees) == 55, f"Expected 55 employees, got {len(employees)}"

        employee_names = [emp['associate'] for emp in employees]
        expected_managers = ['Della Gate', 'Rhoda Map', 'Kay P. Eye', 'Agie Enda', 'Mai Stone']
        for manager in expected_managers:
            assert manager in employee_names, \
                f"Manager {manager} should be an employee in the large org (director rates them)"

        for emp in employees:
            if emp['associate'] in expected_managers:
                assert 'Manager' in emp['current_job_profile'], \
                    f"{emp['associate']} should have a manager job title"

    def test_large_team_managers_in_own_teams(self):
        """Test that each manager is an employee in their own team"""
        module = load_script('generate-demo-templates.py')
        employees = module.get_large_team_employees()

        manager_team_map = {
            'Della Gate': 'Della Gate',
            'Rhoda Map': 'Rhoda Map',
            'Kay P. Eye': 'Kay P. Eye',
            'Agie Enda': 'Agie Enda',
            'Mai Stone': 'Mai Stone',
        }

        for emp in employees:
            if emp['associate'] in manager_team_map:
                expected_in_org = manager_team_map[emp['associate']]
                assert expected_in_org in emp['supervisory_organization'], \
                    f"Manager {emp['associate']} should be in their own team"

    def test_rating_distribution_expressive(self):
        """Test that ratings span the full bonus curve range"""
        module = load_script('generate-demo-templates.py')

        small_employees = module.get_small_team_employees()
        small_ratings = [emp['performance_rating_percent'] for emp in small_employees]

        assert any(r < 70 for r in small_ratings), \
            "Small team should have at least one low performer (< 70%)"

        assert any(r > 125 for r in small_ratings), \
            "Small team should have at least one exceptional performer (> 125%)"

        large_employees = module.get_large_team_employees()
        large_ratings = [emp['performance_rating_percent'] for emp in large_employees]

        assert min(large_ratings) < 70, \
            f"Large team should have low performers, min is {min(large_ratings)}"
        assert max(large_ratings) > 130, \
            f"Large team should have exceptional performers, max is {max(large_ratings)}"

    def test_all_employees_have_ratings(self):
        """Test that all demo employees have performance ratings assigned"""
        module = load_script('generate-demo-templates.py')

        for get_func, name in [
            (module.get_small_team_employees, 'small team'),
            (module.get_large_team_employees, 'large team'),
        ]:
            employees = get_func()
            for emp in employees:
                assert emp.get('performance_rating_percent') is not None, \
                    f"{emp['associate']} in {name} has no rating"
                assert emp.get('justification'), \
                    f"{emp['associate']} in {name} has no justification"


@pytest.mark.skipif(
    not os.path.exists(DEMO_TEMPLATES_DIR),
    reason="Demo templates not generated (run scripts/generate-demo-templates.py)"
)
class TestDemoTemplateSchemaValidation:
    """Verify demo template databases match the current model schema.

    This prevents deployment failures when model columns change but
    demo templates aren't regenerated.
    """

    def test_demo_templates_have_all_employee_columns(self):
        """Ensure demo template databases have all Employee model columns."""
        import sqlite3
        from models import Employee

        expected_columns = {col.name for col in Employee.__table__.columns}

        template_files = ['small-team.db', 'large-team.db']

        for template_file in template_files:
            db_path = os.path.join(DEMO_TEMPLATES_DIR, template_file)
            assert os.path.exists(db_path), f"Demo template not found: {template_file}"

            conn = sqlite3.connect(db_path)
            cursor = conn.execute("PRAGMA table_info(employees)")
            actual_columns = {row[1] for row in cursor.fetchall()}
            conn.close()

            missing = expected_columns - actual_columns
            assert not missing, (
                f"Demo template '{template_file}' is missing columns: {missing}. "
                f"Run 'python3 scripts/generate-demo-templates.py' to regenerate."
            )


class TestDemoTemplateCompleteness:
    """Verify generated demo employees are fully rated and calibrated."""

    @pytest.fixture(autouse=True)
    def load_module(self):
        self.module = load_script('generate-demo-templates.py')
        self.all_tenet_ids = set(self.module.ALL_TENET_IDS)

    def _all_employees(self):
        return self.module.get_small_team_employees() + self.module.get_large_team_employees()

    def test_all_employees_have_bonus_tenets(self):
        """Each employee should have 3 strengths + 3 improvements, non-overlapping, valid IDs."""
        for emp in self._all_employees():
            name = emp['associate']
            strengths = json.loads(emp['tenets_strengths'])
            improvements = json.loads(emp['tenets_improvements'])

            assert len(strengths) == 3, f"{name}: expected 3 strengths, got {len(strengths)}"
            assert len(improvements) == 3, f"{name}: expected 3 improvements, got {len(improvements)}"

            # No overlap between strengths and improvements
            overlap = set(strengths) & set(improvements)
            assert not overlap, f"{name}: tenets overlap: {overlap}"

            # All IDs are valid
            for tid in strengths + improvements:
                assert tid in self.all_tenet_ids, f"{name}: invalid tenet ID '{tid}'"

    def test_all_employees_are_fully_rated(self):
        """is_employee_rated() should return True for every generated employee."""
        from services.employee_utils import is_employee_rated

        for emp in self._all_employees():
            assert is_employee_rated(emp), \
                f"{emp['associate']} is not fully rated: " \
                f"rating={emp.get('performance_rating_percent')}, " \
                f"justification={bool(emp.get('justification'))}, " \
                f"tenets_s={emp.get('tenets_strengths')}, " \
                f"tenets_i={emp.get('tenets_improvements')}"

    def test_all_employees_are_fully_calibrated(self):
        """is_employee_calibrated() should return True for every generated employee."""
        from services.employee_utils import is_employee_calibrated

        for emp in self._all_employees():
            assert is_employee_calibrated(emp), \
                f"{emp['associate']} is not fully calibrated: " \
                f"what={emp.get('talent_perf_what')}, " \
                f"how={emp.get('talent_perf_how')}, " \
                f"actions={bool(emp.get('talent_proposed_actions'))}, " \
                f"tenets_s={emp.get('talent_tenets_strengths')}, " \
                f"tenets_i={emp.get('talent_tenets_improvements')}"

    def test_all_employees_have_original_fields(self):
        """_original fields should match current values (freshly imported state)."""
        bonus_pairs = [
            ('performance_rating_percent', 'performance_rating_percent_original'),
            ('justification', 'justification_original'),
            ('mentor', 'mentor_original'),
            ('mentees', 'mentees_original'),
            ('tenets_strengths', 'tenets_strengths_original'),
            ('tenets_improvements', 'tenets_improvements_original'),
        ]
        talent_pairs = [
            ('talent_perf_what', 'talent_perf_what_original'),
            ('talent_perf_how', 'talent_perf_how_original'),
            ('talent_growth_agility', 'talent_growth_agility_original'),
            ('talent_change_agility', 'talent_change_agility_original'),
            ('talent_movement_readiness', 'talent_movement_readiness_original'),
            ('talent_proposed_actions', 'talent_proposed_actions_original'),
            ('talent_tenets_strengths', 'talent_tenets_strengths_original'),
            ('talent_tenets_improvements', 'talent_tenets_improvements_original'),
        ]

        for emp in self._all_employees():
            name = emp['associate']
            for current, original in bonus_pairs:
                cur_val = emp.get(current)
                orig_val = emp.get(original)
                # Float comparison for rating
                if isinstance(cur_val, int):
                    cur_val = float(cur_val)
                assert cur_val == orig_val, \
                    f"{name}: {current}={cur_val!r} != {original}={orig_val!r}"

            for current, original in talent_pairs:
                assert emp.get(current) == emp.get(original), \
                    f"{name}: {current}={emp.get(current)!r} != {original}={emp.get(original)!r}"

    def test_talent_proposed_actions_set(self):
        """All employees should have non-empty talent_proposed_actions."""
        for emp in self._all_employees():
            assert emp.get('talent_proposed_actions'), \
                f"{emp['associate']} has no talent_proposed_actions"

    def test_clear_ratings_clears_all_fields(self):
        """_clear_ratings_in_db() should null tenets, originals, and talent fields."""
        from demo_mode import _clear_ratings_in_db

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            employees = self.module.get_small_team_employees()
            self.module.create_template_database(db_path, employees)

            _clear_ratings_in_db(db_path)

            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM employees').fetchall()

            cleared_fields = [
                # Bonus fields
                'performance_rating_percent', 'justification', 'mentor', 'mentees',
                'tenets_strengths', 'tenets_improvements',
                # Bonus _original
                'performance_rating_percent_original', 'justification_original',
                'mentor_original', 'mentees_original',
                'tenets_strengths_original', 'tenets_improvements_original',
                # Talent fields
                'talent_perf_what', 'talent_perf_how', 'talent_overall_perf',
                'talent_growth_agility', 'talent_change_agility',
                'talent_identified_future', 'talent_movement_readiness',
                'talent_proposed_actions', 'talent_tenets_strengths',
                'talent_tenets_improvements',
                # Talent _original
                'talent_perf_what_original', 'talent_perf_how_original',
                'talent_growth_agility_original', 'talent_change_agility_original',
                'talent_movement_readiness_original', 'talent_proposed_actions_original',
                'talent_mentor_original', 'talent_mentees_original',
                'talent_promo_job_profile_original', 'talent_promo_business_need_original',
                'talent_promo_role_scope_original', 'talent_promo_readiness_original',
                'talent_tenets_strengths_original', 'talent_tenets_improvements_original',
            ]

            for row in rows:
                name = row['associate']
                for field in cleared_fields:
                    assert row[field] is None, \
                        f"{name}: {field} should be NULL after clear, got {row[field]!r}"

            conn.close()
