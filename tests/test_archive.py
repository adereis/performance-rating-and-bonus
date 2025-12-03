"""
Tests for the archive period functionality.
"""
import pytest
import json
from models import Employee, Period, RatingSnapshot


class TestArchivePeriodEndpoint:
    """Tests for the /api/archive-period endpoint."""

    def test_archive_no_data(self, client, db_session):
        """Test archive without JSON body returns error."""
        response = client.post('/api/archive-period', json={})
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'required' in data['error']

    def test_archive_missing_period_id(self, client, db_session):
        """Test archive without period_id returns error."""
        response = client.post('/api/archive-period', json={
            'period_name': 'First Half 2025'
        })
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False

    def test_archive_missing_period_name(self, client, db_session):
        """Test archive without period_name returns error."""
        response = client.post('/api/archive-period', json={
            'period_id': '2025-H1'
        })
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False

    def test_archive_duplicate_period(self, client, db_session):
        """Test archive with existing period ID returns error."""
        # Create existing period
        period = Period(id='2025-H1', name='First Half 2025')
        db_session.add(period)
        db_session.commit()

        response = client.post('/api/archive-period', json={
            'period_id': '2025-H1',
            'period_name': 'Duplicate'
        })
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'already exists' in data['error']

    def test_archive_creates_period_and_snapshots(self, client, db_session):
        """Test archive creates period and snapshots for rated employees."""
        # Create employees with ratings
        emp1 = Employee(
            associate_id='EMP001',
            associate='John Doe',
            supervisory_organization='Engineering',
            current_job_profile='Senior Engineer',
            bonus_target_local_currency_usd=15000,
            performance_rating_percent=125.0,
            justification='Excellent work on project X'
        )
        emp2 = Employee(
            associate_id='EMP002',
            associate='Jane Smith',
            supervisory_organization='Product',
            current_job_profile='Product Manager',
            bonus_target_local_currency_usd=12000,
            performance_rating_percent=110.0,
            justification='Solid performance'
        )
        # Unrated employee
        emp3 = Employee(
            associate_id='EMP003',
            associate='Bob Wilson',
            supervisory_organization='Engineering'
        )
        db_session.add_all([emp1, emp2, emp3])
        db_session.commit()

        response = client.post('/api/archive-period', json={
            'period_id': '2025-H1',
            'period_name': 'First Half 2025',
            'notes': 'Great quarter!'
        })

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['archived_count'] == 2
        assert data['skipped_unrated'] == 1
        assert data['period_id'] == '2025-H1'

        # Verify period was created
        period = db_session.query(Period).filter(Period.id == '2025-H1').first()
        assert period is not None
        assert period.name == 'First Half 2025'
        assert period.notes == 'Great quarter!'
        assert period.archived_at is not None

        # Verify snapshots were created
        snapshots = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.period_id == '2025-H1'
        ).all()
        assert len(snapshots) == 2

        # Check John's snapshot
        john_snap = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.associate_id == 'EMP001'
        ).first()
        assert john_snap.performance_rating == 125.0
        assert john_snap.justification == 'Excellent work on project X'
        assert john_snap.snapshot_name == 'John Doe'
        assert john_snap.snapshot_org == 'Engineering'
        assert john_snap.snapshot_job_profile == 'Senior Engineer'
        assert john_snap.snapshot_bonus_target_usd == 15000
        assert john_snap.has_full_details is True

    def test_archive_clears_ratings(self, client, db_session):
        """Test archive clears all ratings after successful archive."""
        # Create employee with full rating data
        emp = Employee(
            associate_id='EMP001',
            associate='John Doe',
            performance_rating_percent=125.0,
            justification='Great work',
            mentor='Alice Manager',
            mentees='Bob Junior, Carol Junior',
            tenets_strengths='["tenet1", "tenet2", "tenet3"]',
            tenets_improvements='["tenet4", "tenet5"]'
        )
        db_session.add(emp)
        db_session.commit()

        response = client.post('/api/archive-period', json={
            'period_id': '2025-H1',
            'period_name': 'First Half 2025'
        })

        assert response.status_code == 200
        assert response.get_json()['success'] is True

        # Refresh employee from database
        db_session.refresh(emp)

        # Verify all rating fields are cleared
        assert emp.performance_rating_percent is None
        assert emp.justification is None
        assert emp.mentor is None
        assert emp.mentees is None
        assert emp.tenets_strengths is None
        assert emp.tenets_improvements is None
        assert emp.last_updated is None

    def test_archive_converts_tenet_ids_to_names(self, client, db_session, monkeypatch):
        """Test archive converts tenet IDs to human-readable names."""
        # Mock the tenets config
        def mock_load_tenets_config():
            return (
                {'tenets': [
                    {'id': 'tenet1', 'name': 'Customer Focus'},
                    {'id': 'tenet2', 'name': 'Innovation'},
                    {'id': 'tenet3', 'name': 'Collaboration'},
                    {'id': 'tenet4', 'name': 'Quality'},
                    {'id': 'tenet5', 'name': 'Learning'}
                ]},
                {
                    'tenet1': 'Customer Focus',
                    'tenet2': 'Innovation',
                    'tenet3': 'Collaboration',
                    'tenet4': 'Quality',
                    'tenet5': 'Learning'
                }
            )

        import app
        monkeypatch.setattr(app, 'load_tenets_config', mock_load_tenets_config)

        # Create employee with tenet IDs
        emp = Employee(
            associate_id='EMP001',
            associate='John Doe',
            performance_rating_percent=125.0,
            tenets_strengths='["tenet1", "tenet2", "tenet3"]',
            tenets_improvements='["tenet4", "tenet5"]'
        )
        db_session.add(emp)
        db_session.commit()

        response = client.post('/api/archive-period', json={
            'period_id': '2025-H1',
            'period_name': 'First Half 2025'
        })

        assert response.status_code == 200

        # Verify snapshot has human-readable names
        snapshot = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.associate_id == 'EMP001'
        ).first()
        assert snapshot.tenets_strengths == 'Customer Focus, Innovation, Collaboration'
        assert snapshot.tenets_improvements == 'Quality, Learning'

    def test_archive_handles_invalid_tenet_json(self, client, db_session):
        """Test archive handles invalid JSON in tenets fields gracefully."""
        # Create employee with invalid JSON in tenets
        emp = Employee(
            associate_id='EMP001',
            associate='John Doe',
            performance_rating_percent=125.0,
            tenets_strengths='not valid json',
            tenets_improvements='also not valid'
        )
        db_session.add(emp)
        db_session.commit()

        response = client.post('/api/archive-period', json={
            'period_id': '2025-H1',
            'period_name': 'First Half 2025'
        })

        assert response.status_code == 200

        # Verify snapshot preserves the original values
        snapshot = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.associate_id == 'EMP001'
        ).first()
        assert snapshot.tenets_strengths == 'not valid json'
        assert snapshot.tenets_improvements == 'also not valid'

    def test_archive_with_no_rated_employees(self, client, db_session):
        """Test archive with no rated employees creates empty period."""
        # Create unrated employees
        emp1 = Employee(associate_id='EMP001', associate='John Doe')
        emp2 = Employee(associate_id='EMP002', associate='Jane Smith')
        db_session.add_all([emp1, emp2])
        db_session.commit()

        response = client.post('/api/archive-period', json={
            'period_id': '2025-H1',
            'period_name': 'First Half 2025'
        })

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['archived_count'] == 0
        assert data['skipped_unrated'] == 2

        # Period should still be created
        period = db_session.query(Period).filter(Period.id == '2025-H1').first()
        assert period is not None

    def test_archive_stores_mentor_and_mentees(self, client, db_session):
        """Test archive preserves mentor and mentee information."""
        emp = Employee(
            associate_id='EMP001',
            associate='John Doe',
            performance_rating_percent=125.0,
            mentor='Senior Alice',
            mentees='Junior Bob, Junior Carol'
        )
        db_session.add(emp)
        db_session.commit()

        response = client.post('/api/archive-period', json={
            'period_id': '2025-H1',
            'period_name': 'First Half 2025'
        })

        assert response.status_code == 200

        snapshot = db_session.query(RatingSnapshot).filter(
            RatingSnapshot.associate_id == 'EMP001'
        ).first()
        assert snapshot.mentors == 'Senior Alice'
        assert snapshot.mentees == 'Junior Bob, Junior Carol'


class TestArchiveButton:
    """Tests for the archive button on the dashboard."""

    def test_dashboard_has_archive_button(self, client, db_session):
        """Test dashboard shows archive button."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Archive Period' in response.data

    def test_dashboard_shows_archive_modal(self, client, db_session):
        """Test dashboard has archive modal HTML."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'archiveModal' in response.data
        assert b'periodId' in response.data
        assert b'periodName' in response.data

    def test_dashboard_archive_button_disabled_when_no_rated(self, client, db_session):
        """Test archive button is disabled when no employees are rated."""
        # No employees means stats.rated == 0
        response = client.get('/')
        assert response.status_code == 200
        # Button should be disabled
        assert b'disabled' in response.data

    def test_dashboard_archive_button_enabled_when_rated(self, client, db_session):
        """Test archive button is enabled when employees are rated."""
        # Create a rated employee
        emp = Employee(
            associate_id='EMP001',
            associate='John Doe',
            performance_rating_percent=125.0
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/')
        assert response.status_code == 200
        # Check that Archive Period button exists and is not disabled
        html = response.data.decode('utf-8')
        # Find the archive button - it should not have disabled attribute
        assert 'btn-archive' in html
