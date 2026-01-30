"""
Tests for sample data generation scripts.

These tests verify that the scripts in scripts/ can be imported and run
correctly, including proper handling of imports from the parent directory.
"""
import pytest
import os
import sys
import tempfile

DEMO_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'demo-templates')


class TestCreateSampleData:
    """Tests for scripts/create_sample_data.py"""

    def test_script_can_be_imported(self):
        """Test that the script can be imported without errors"""
        # Add scripts directory to path
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            # Import should not raise any errors
            import create_sample_data
            assert hasattr(create_sample_data, 'create_headers')
            assert hasattr(create_sample_data, 'create_sample_xlsx')
        finally:
            sys.path.remove(scripts_dir)

    def test_creates_xlsx_file(self):
        """Test that create_sample_data generates a valid XLSX file"""
        import openpyxl
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import create_sample_data

            with tempfile.TemporaryDirectory() as tmpdir:
                output_file = os.path.join(tmpdir, 'test-sample.xlsx')

                # Call the function to create sample data
                wb = openpyxl.Workbook()
                sheet = wb.active
                create_sample_data.create_headers(sheet)

                # Verify headers were created
                # Row 2 (index 1) should have headers
                headers = [cell.value for cell in sheet[2]]
                assert 'Associate' in headers
                assert 'Supervisory Organization' in headers
                assert 'Current Job Profile' in headers

                wb.save(output_file)
                assert os.path.exists(output_file)
        finally:
            sys.path.remove(scripts_dir)

    def test_small_team_data(self):
        """Test that small team data function returns properly structured data"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import create_sample_data

            # Verify get_small_team_data returns expected structure
            assert hasattr(create_sample_data, 'get_small_team_data')
            small_team = create_sample_data.get_small_team_data()

            # Should have employees
            assert len(small_team) > 0

            # Each employee should have required fields (matching Workday column names)
            for emp in small_team:
                assert 'associate' in emp
                assert 'job_profile' in emp
                assert 'salary' in emp
        finally:
            sys.path.remove(scripts_dir)


class TestPopulateSampleRatings:
    """Tests for scripts/populate_sample_ratings.py"""

    def test_script_can_be_imported(self):
        """Test that the script can be imported without errors"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import populate_sample_ratings
            assert hasattr(populate_sample_ratings, 'SMALL_TEAM_RATINGS')
            assert hasattr(populate_sample_ratings, 'LARGE_ORG_RATINGS')
        finally:
            sys.path.remove(scripts_dir)

    def test_small_team_ratings_defined(self):
        """Test that small team ratings data is properly structured"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import populate_sample_ratings

            ratings = populate_sample_ratings.SMALL_TEAM_RATINGS

            # Should have ratings for multiple employees
            assert len(ratings) > 0

            # Each entry should be (rating, justification)
            for name, data in ratings.items():
                assert isinstance(data, tuple)
                assert len(data) == 2
                rating, justification = data
                assert isinstance(rating, int)
                assert 0 <= rating <= 200  # Valid rating range
                assert isinstance(justification, str)
        finally:
            sys.path.remove(scripts_dir)

    def test_large_org_ratings_defined(self):
        """Test that large org ratings data is properly structured"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import populate_sample_ratings

            ratings = populate_sample_ratings.LARGE_ORG_RATINGS

            # Should have ratings for multiple employees
            assert len(ratings) > 0

            # Large org should have more ratings than small team
            small_ratings = populate_sample_ratings.SMALL_TEAM_RATINGS
            assert len(ratings) >= len(small_ratings)
        finally:
            sys.path.remove(scripts_dir)


class TestScriptImportPaths:
    """Test that scripts handle import paths correctly for standalone execution"""

    def test_create_sample_data_path_handling(self):
        """Test that create_sample_data.py adds parent to sys.path"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        script_path = os.path.join(scripts_dir, 'create_sample_data.py')

        with open(script_path, 'r') as f:
            content = f.read()

        # Should have the path manipulation for standalone execution
        assert 'sys.path.insert' in content
        assert 'os.path.dirname' in content

    def test_populate_sample_ratings_path_handling(self):
        """Test that populate_sample_ratings.py adds parent to sys.path"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        script_path = os.path.join(scripts_dir, 'populate_sample_ratings.py')

        with open(script_path, 'r') as f:
            content = f.read()

        # Should have the path manipulation for standalone execution
        assert 'sys.path.insert' in content
        assert 'os.path.dirname' in content


class TestScriptHelpSupport:
    """Test that scripts have proper --help support via argparse"""

    def test_create_sample_data_has_main_function(self):
        """Test that create_sample_data.py has a main() function with argparse"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import create_sample_data
            assert hasattr(create_sample_data, 'main')

            # Check that argparse is used
            script_path = os.path.join(scripts_dir, 'create_sample_data.py')
            with open(script_path, 'r') as f:
                content = f.read()
            assert 'argparse' in content
            assert 'ArgumentParser' in content
        finally:
            sys.path.remove(scripts_dir)

    def test_populate_sample_ratings_has_main_function(self):
        """Test that populate_sample_ratings.py has a main() function with argparse"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import populate_sample_ratings
            assert hasattr(populate_sample_ratings, 'main')

            # Check that argparse is used
            script_path = os.path.join(scripts_dir, 'populate_sample_ratings.py')
            with open(script_path, 'r') as f:
                content = f.read()
            assert 'argparse' in content
            assert 'ArgumentParser' in content
        finally:
            sys.path.remove(scripts_dir)


class TestCreateDemoTemplates:
    """Tests for scripts/create_demo_templates.py"""

    def test_script_can_be_imported(self):
        """Test that the script can be imported without errors"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import create_demo_templates
            assert hasattr(create_demo_templates, 'get_small_team_employees')
            assert hasattr(create_demo_templates, 'get_large_team_employees')
            assert hasattr(create_demo_templates, 'create_template_database')
        finally:
            sys.path.remove(scripts_dir)

    def test_small_team_structure(self):
        """Test that small team data has correct structure and no manager as employee"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import create_demo_templates

            employees = create_demo_templates.get_small_team_employees()

            # Should have 12 employees
            assert len(employees) == 12, f"Expected 12 employees, got {len(employees)}"

            # Each employee should have required fields
            required_fields = [
                'associate_id', 'associate', 'supervisory_organization',
                'current_job_profile', 'performance_rating_percent', 'justification'
            ]
            for emp in employees:
                for field in required_fields:
                    assert field in emp, f"Missing field {field} in employee {emp.get('associate', 'unknown')}"

            # Manager (Della Gate) should NOT be an employee (she's the user)
            employee_names = [emp['associate'] for emp in employees]
            assert 'Della Gate' not in employee_names, \
                "Della Gate should not be an employee - she is the manager using the system"

            # All employees should belong to Della Gate's team
            for emp in employees:
                assert 'Della Gate' in emp['supervisory_organization'], \
                    f"Employee {emp['associate']} should be under Della Gate's organization"

        finally:
            sys.path.remove(scripts_dir)

    def test_large_team_structure(self):
        """Test that large team data includes managers as employees"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import create_demo_templates

            employees = create_demo_templates.get_large_team_employees()

            # Should have 55 employees (10 ICs + 1 manager per team × 5 teams)
            assert len(employees) == 55, f"Expected 55 employees, got {len(employees)}"

            # Get all employee names
            employee_names = [emp['associate'] for emp in employees]

            # The 5 managers MUST be included as employees (director rates them)
            expected_managers = ['Della Gate', 'Rhoda Map', 'Kay P. Eye', 'Agie Enda', 'Mai Stone']
            for manager in expected_managers:
                assert manager in employee_names, \
                    f"Manager {manager} should be an employee in the large org (director rates them)"

            # Managers should have manager job titles
            for emp in employees:
                if emp['associate'] in expected_managers:
                    assert 'Manager' in emp['current_job_profile'], \
                        f"{emp['associate']} should have a manager job title"

        finally:
            sys.path.remove(scripts_dir)

    def test_large_team_managers_in_own_teams(self):
        """Test that each manager is an employee in their own team"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import create_demo_templates

            employees = create_demo_templates.get_large_team_employees()

            # Map of manager name to expected team name substring
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

        finally:
            sys.path.remove(scripts_dir)

    def test_rating_distribution_expressive(self):
        """Test that ratings span the full bonus curve range"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import create_demo_templates

            # Check small team
            small_employees = create_demo_templates.get_small_team_employees()
            small_ratings = [emp['performance_rating_percent'] for emp in small_employees]

            # Should have low performers (< 70%)
            assert any(r < 70 for r in small_ratings), \
                "Small team should have at least one low performer (< 70%)"

            # Should have exceptional performers (> 125%)
            assert any(r > 125 for r in small_ratings), \
                "Small team should have at least one exceptional performer (> 125%)"

            # Check large team
            large_employees = create_demo_templates.get_large_team_employees()
            large_ratings = [emp['performance_rating_percent'] for emp in large_employees]

            # Should have full range
            assert min(large_ratings) < 70, \
                f"Large team should have low performers, min is {min(large_ratings)}"
            assert max(large_ratings) > 130, \
                f"Large team should have exceptional performers, max is {max(large_ratings)}"

        finally:
            sys.path.remove(scripts_dir)

    def test_all_employees_have_ratings(self):
        """Test that all demo employees have performance ratings assigned"""
        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
        sys.path.insert(0, scripts_dir)

        try:
            import create_demo_templates

            for get_func, name in [
                (create_demo_templates.get_small_team_employees, 'small team'),
                (create_demo_templates.get_large_team_employees, 'large team'),
            ]:
                employees = get_func()
                for emp in employees:
                    assert emp.get('performance_rating_percent') is not None, \
                        f"{emp['associate']} in {name} has no rating"
                    assert emp.get('justification'), \
                        f"{emp['associate']} in {name} has no justification"

        finally:
            sys.path.remove(scripts_dir)


@pytest.mark.skipif(
    not os.path.exists(DEMO_TEMPLATES_DIR),
    reason="Demo templates not generated (run scripts/create_demo_templates.py)"
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

        # Get expected columns from the Employee model
        expected_columns = {col.name for col in Employee.__table__.columns}

        template_files = ['small-team.db', 'large-team.db']

        for template_file in template_files:
            db_path = os.path.join(DEMO_TEMPLATES_DIR, template_file)
            assert os.path.exists(db_path), f"Demo template not found: {template_file}"

            # Get actual columns from the database
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("PRAGMA table_info(employees)")
            actual_columns = {row[1] for row in cursor.fetchall()}
            conn.close()

            # Check for missing columns
            missing = expected_columns - actual_columns
            assert not missing, (
                f"Demo template '{template_file}' is missing columns: {missing}. "
                f"Run 'python3 scripts/create_demo_templates.py' to regenerate."
            )
