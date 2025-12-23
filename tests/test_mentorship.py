"""
Tests for mentorship analytics functionality.

Tests the mentorship statistics calculation and analytics display.
"""
import pytest
from app import calculate_mentorship_stats


class TestMentorshipStatsCalculation:
    """Tests for the calculate_mentorship_stats function."""

    def test_empty_employees_list(self):
        """Empty list returns zero stats."""
        stats = calculate_mentorship_stats([])

        assert stats['overall']['total'] == 0
        assert stats['overall']['with_mentor'] == 0
        assert stats['overall']['with_mentees'] == 0
        assert stats['by_job_title'] == []
        assert stats['top_mentors'] == []

    def test_counts_employees_with_mentors(self):
        """Employees with non-empty mentor field are counted."""
        employees = [
            {'Associate': 'Alice', 'mentor': 'Bob', 'mentees': '', 'Current Job Profile': 'Engineer'},
            {'Associate': 'Carol', 'mentor': '', 'mentees': '', 'Current Job Profile': 'Engineer'},
            {'Associate': 'Dave', 'mentor': 'Eve', 'mentees': '', 'Current Job Profile': 'Engineer'},
        ]
        stats = calculate_mentorship_stats(employees)

        assert stats['overall']['total'] == 3
        assert stats['overall']['with_mentor'] == 2
        assert stats['overall']['pct_with_mentor'] == pytest.approx(66.7, 0.1)

    def test_counts_employees_with_mentees(self):
        """Employees with non-empty mentees field are counted as mentoring others."""
        employees = [
            {'Associate': 'Alice', 'mentor': '', 'mentees': 'Bob, Carol', 'Current Job Profile': 'Senior'},
            {'Associate': 'Dave', 'mentor': '', 'mentees': 'Eve', 'Current Job Profile': 'Senior'},
            {'Associate': 'Frank', 'mentor': '', 'mentees': '', 'Current Job Profile': 'Junior'},
        ]
        stats = calculate_mentorship_stats(employees)

        assert stats['overall']['with_mentees'] == 2
        assert stats['overall']['pct_with_mentees'] == pytest.approx(66.7, 0.1)

    def test_counts_total_mentee_relationships(self):
        """Total mentee count sums all mentees across all mentors."""
        employees = [
            {'Associate': 'Alice', 'mentor': '', 'mentees': 'Bob, Carol, Dave', 'Current Job Profile': 'Principal'},
            {'Associate': 'Eve', 'mentor': '', 'mentees': 'Frank', 'Current Job Profile': 'Senior'},
            {'Associate': 'Grace', 'mentor': '', 'mentees': '', 'Current Job Profile': 'Junior'},
        ]
        stats = calculate_mentorship_stats(employees)

        assert stats['overall']['total_mentee_count'] == 4  # 3 + 1

    def test_handles_whitespace_in_mentees(self):
        """Whitespace-only entries in comma-separated mentees are ignored."""
        employees = [
            {'Associate': 'Alice', 'mentor': '', 'mentees': 'Bob, , Carol,  ', 'Current Job Profile': 'Senior'},
        ]
        stats = calculate_mentorship_stats(employees)

        assert stats['overall']['total_mentee_count'] == 2  # Bob and Carol only

    def test_handles_none_values(self):
        """None values for mentor/mentees are handled gracefully."""
        employees = [
            {'Associate': 'Alice', 'mentor': None, 'mentees': None, 'Current Job Profile': 'Engineer'},
            {'Associate': 'Bob', 'mentor': 'Carol', 'mentees': None, 'Current Job Profile': 'Engineer'},
        ]
        stats = calculate_mentorship_stats(employees)

        assert stats['overall']['total'] == 2
        assert stats['overall']['with_mentor'] == 1
        assert stats['overall']['with_mentees'] == 0


class TestMentorshipByJobTitle:
    """Tests for the by_job_title breakdown."""

    def test_groups_by_job_title(self):
        """Stats are grouped by job title correctly."""
        employees = [
            {'Associate': 'A', 'mentor': 'X', 'mentees': '', 'Current Job Profile': 'Junior'},
            {'Associate': 'B', 'mentor': 'X', 'mentees': '', 'Current Job Profile': 'Junior'},
            {'Associate': 'C', 'mentor': '', 'mentees': 'A, B', 'Current Job Profile': 'Senior'},
        ]
        stats = calculate_mentorship_stats(employees)

        junior = next(j for j in stats['by_job_title'] if j['job_title'] == 'Junior')
        senior = next(j for j in stats['by_job_title'] if j['job_title'] == 'Senior')

        assert junior['count'] == 2
        assert junior['with_mentor'] == 2
        assert junior['pct_with_mentor'] == 100.0
        assert junior['with_mentees'] == 0

        assert senior['count'] == 1
        assert senior['with_mentees'] == 1
        assert senior['pct_with_mentees'] == 100.0

    def test_handles_missing_job_title(self):
        """Employees without job title are grouped as 'Unknown'."""
        employees = [
            {'Associate': 'A', 'mentor': 'X', 'mentees': '', 'Current Job Profile': None},
            {'Associate': 'B', 'mentor': '', 'mentees': '', 'Current Job Profile': ''},
        ]
        stats = calculate_mentorship_stats(employees)

        unknown = next(j for j in stats['by_job_title'] if j['job_title'] == 'Unknown')
        assert unknown['count'] == 2


class TestTopMentors:
    """Tests for the top_mentors list."""

    def test_top_mentors_sorted_by_mentee_count(self):
        """Top mentors are sorted by mentee count descending."""
        employees = [
            {'Associate': 'Alice', 'Associate ID': 'A1', 'mentor': '', 'mentees': 'X', 'Current Job Profile': 'Senior'},
            {'Associate': 'Bob', 'Associate ID': 'B1', 'mentor': '', 'mentees': 'X, Y, Z', 'Current Job Profile': 'Principal'},
            {'Associate': 'Carol', 'Associate ID': 'C1', 'mentor': '', 'mentees': 'X, Y', 'Current Job Profile': 'Senior'},
        ]
        stats = calculate_mentorship_stats(employees)

        assert len(stats['top_mentors']) == 3
        assert stats['top_mentors'][0]['name'] == 'Bob'
        assert stats['top_mentors'][0]['mentee_count'] == 3
        assert stats['top_mentors'][1]['name'] == 'Carol'
        assert stats['top_mentors'][1]['mentee_count'] == 2

    def test_top_mentors_limited_to_10(self):
        """Top mentors list is limited to 10 entries."""
        employees = [
            {'Associate': f'Person{i}', 'Associate ID': f'P{i}', 'mentor': '', 'mentees': 'X', 'Current Job Profile': 'Eng'}
            for i in range(15)
        ]
        stats = calculate_mentorship_stats(employees)

        assert len(stats['top_mentors']) == 10

    def test_top_mentors_includes_metadata(self):
        """Top mentors include name, associate_id, job_profile, and mentee_count."""
        employees = [
            {'Associate': 'Alice', 'Associate ID': 'A1', 'mentor': '', 'mentees': 'Bob, Carol', 'Current Job Profile': 'Principal Engineer'},
        ]
        stats = calculate_mentorship_stats(employees)

        mentor = stats['top_mentors'][0]
        assert mentor['name'] == 'Alice'
        assert mentor['associate_id'] == 'A1'
        assert mentor['job_profile'] == 'Principal Engineer'
        assert mentor['mentee_count'] == 2


class TestMentorshipAnalyticsRoute:
    """Integration tests for the analytics route with mentorship stats."""

    def test_analytics_page_includes_mentorship_stats(self, client, db_session):
        """Analytics page renders mentorship statistics section."""
        from models import Employee

        # Create employees with mentorship data
        emp1 = Employee(
            associate_id='EMP001',
            associate='Alice Principal',
            current_job_profile='Principal Engineer',
            performance_rating_percent=120,
            mentor='',
            mentees='Bob, Carol'
        )
        emp2 = Employee(
            associate_id='EMP002',
            associate='Bob Senior',
            current_job_profile='Senior Engineer',
            performance_rating_percent=100,
            mentor='Alice Principal',
            mentees=''
        )
        db_session.add_all([emp1, emp2])
        db_session.commit()

        response = client.get('/analytics')

        assert response.status_code == 200
        html = response.data.decode()
        assert 'Mentorship Analytics' in html
        assert 'Being Mentored' in html
        assert 'Mentoring Others' in html

    def test_analytics_shows_by_job_title_breakdown(self, client, db_session):
        """Analytics page shows mentorship breakdown by job title."""
        from models import Employee

        emp1 = Employee(
            associate_id='EMP001',
            associate='Alice',
            current_job_profile='Principal Engineer',
            performance_rating_percent=100,
            mentees='Bob'
        )
        emp2 = Employee(
            associate_id='EMP002',
            associate='Bob',
            current_job_profile='Software Engineer',
            performance_rating_percent=100,
            mentor='Alice'
        )
        db_session.add_all([emp1, emp2])
        db_session.commit()

        response = client.get('/analytics')

        html = response.data.decode()
        assert 'By Job Title' in html
        assert 'Principal Engineer' in html
        assert 'Software Engineer' in html

    def test_analytics_shows_top_mentors(self, client, db_session):
        """Analytics page shows top mentors section."""
        from models import Employee

        emp = Employee(
            associate_id='EMP001',
            associate='Alice Principal',
            current_job_profile='Principal Engineer',
            performance_rating_percent=100,
            mentees='Bob, Carol, Dave'
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/analytics')

        html = response.data.decode()
        assert 'Top Mentors' in html
        assert 'Alice Principal' in html
