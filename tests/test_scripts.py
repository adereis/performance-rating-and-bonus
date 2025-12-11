"""
Tests for sample data generation scripts.

These tests verify that the scripts in scripts/ can be imported and run
correctly, including proper handling of imports from the parent directory.
"""
import pytest
import os
import sys
import tempfile


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
