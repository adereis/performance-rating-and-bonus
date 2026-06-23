"""
Tests for demo_mode.py - session-based database isolation for cloud deployment.

These tests verify:
- Session ID generation and caching
- Database file path management
- Template-based session initialization
- Engine creation and mtime-based invalidation
- Stale session cleanup
- Cookie handling in responses
"""
import os
import time
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from flask import g

# Import the module under test
import demo_mode
from models import Base, Employee


@pytest.fixture
def temp_demo_dir():
    """Create a temporary directory for demo session databases."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def demo_mode_enabled(temp_demo_dir, monkeypatch):
    """Enable demo mode with isolated temp directory."""
    # Patch module-level variables
    monkeypatch.setattr(demo_mode, 'DEMO_MODE', True)
    monkeypatch.setattr(demo_mode, 'SESSION_DB_DIR', temp_demo_dir)
    monkeypatch.setattr(demo_mode, 'SESSION_TIMEOUT_SECONDS', 60)

    # Clear any cached state from previous tests
    demo_mode._session_engines.clear()
    demo_mode._session_last_access.clear()
    demo_mode._session_db_mtime.clear()

    yield temp_demo_dir

    # Cleanup engines after test
    for engine in demo_mode._session_engines.values():
        try:
            engine.dispose()
        except Exception:
            pass
    demo_mode._session_engines.clear()
    demo_mode._session_last_access.clear()
    demo_mode._session_db_mtime.clear()


@pytest.fixture
def template_db(temp_demo_dir):
    """Create a mock template database for testing."""
    templates_dir = os.path.join(temp_demo_dir, 'templates')
    os.makedirs(templates_dir, exist_ok=True)

    # Create a small template database with schema and sample data
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    template_path = os.path.join(templates_dir, 'small-team.db')
    engine = create_engine(f'sqlite:///{template_path}')
    Base.metadata.create_all(bind=engine)

    # Add a sample employee so we can verify template copying
    Session = sessionmaker(bind=engine)
    session = Session()
    employee = Employee(
        associate_id='DEMO001',
        associate='Demo Employee',
        supervisory_organization='Demo Team (Demo Manager)',
        current_job_profile='Software Engineer',
        currency='USD',
        bonus_target_local_currency=15000.0,
        performance_rating_percent=110.0,
        justification='Demo justification',
    )
    session.add(employee)
    session.commit()
    session.close()
    engine.dispose()

    return template_path


class TestGetSessionId:
    """Tests for get_session_id() function."""

    def test_returns_cookie_value_when_present(self, app):
        """Should return an existing valid (UUID) session ID from the cookie."""
        valid_id = '11111111-2222-4333-8444-555555555555'
        with app.test_request_context(
            '/',
            headers={'Cookie': f'{demo_mode.SESSION_COOKIE_NAME}={valid_id}'}
        ):
            session_id = demo_mode.get_session_id()
            assert session_id == valid_id

    def test_rejects_invalid_or_malicious_cookie(self, app):
        """A non-UUID cookie (path traversal / hijack attempt) is discarded.

        The session id is interpolated into a DB file path, so an attacker
        cookie like '../../etc/x' must never be used; a fresh UUID is minted.
        """
        import uuid as _uuid
        for bad in ['test-session-123', '../../etc/passwd', 'a/b', '..', '']:
            with app.test_request_context(
                '/',
                headers={'Cookie': f'{demo_mode.SESSION_COOKIE_NAME}={bad}'}
            ):
                session_id = demo_mode.get_session_id()
                assert session_id != bad
                # Must be a fresh, valid UUID (no path separators possible)
                assert str(_uuid.UUID(session_id)) == session_id
                assert '/' not in session_id and '..' not in session_id

    def test_generates_uuid_when_no_cookie(self, app):
        """Should generate a new UUID when no cookie present."""
        with app.test_request_context('/'):
            session_id = demo_mode.get_session_id()
            # UUID4 format: 8-4-4-4-12 hex digits
            assert len(session_id) == 36
            assert session_id.count('-') == 4

    def test_caches_session_id_in_flask_g(self, app):
        """Should cache session ID in Flask's g object for request consistency."""
        with app.test_request_context('/'):
            first_call = demo_mode.get_session_id()
            second_call = demo_mode.get_session_id()

            assert first_call == second_call
            assert hasattr(g, '_demo_session_id')
            assert g._demo_session_id == first_call

    def test_generates_valid_uuid_format(self, app):
        """Generated session IDs should be valid UUIDs."""
        import uuid

        with app.test_request_context('/'):
            session_id = demo_mode.get_session_id()

            # Should be parseable as UUID (raises ValueError if invalid)
            parsed = uuid.UUID(session_id)
            assert str(parsed) == session_id


class TestGetSessionDbPath:
    """Tests for get_session_db_path() function."""

    def test_creates_session_directory(self, demo_mode_enabled):
        """Should create the session directory if it doesn't exist."""
        session_dir = demo_mode_enabled
        # Remove the directory to test creation
        shutil.rmtree(session_dir)
        assert not os.path.exists(session_dir)

        path = demo_mode.get_session_db_path('test-session')

        assert os.path.exists(session_dir)
        assert path == os.path.join(session_dir, 'session_test-session.db')

    def test_returns_correct_path_format(self, demo_mode_enabled):
        """Should return path in expected format."""
        path = demo_mode.get_session_db_path('abc-123-def')

        assert path.endswith('session_abc-123-def.db')
        assert demo_mode_enabled in path


class TestSessionHasData:
    """Tests for session_has_data() function."""

    def test_returns_false_for_nonexistent_db(self, demo_mode_enabled):
        """Should return False when database doesn't exist."""
        assert demo_mode.session_has_data('nonexistent-session') is False

    def test_returns_false_for_tiny_db(self, demo_mode_enabled):
        """Should return False for very small database files."""
        session_id = 'tiny-session'
        db_path = demo_mode.get_session_db_path(session_id)

        # Create a tiny file (below 10KB threshold used by session_has_data)
        with open(db_path, 'wb') as f:
            f.write(b'x' * 5000)  # 5KB, below threshold

        assert demo_mode.session_has_data(session_id) is False

    def test_returns_true_for_schema_db(self, demo_mode_enabled):
        """Schema-only database exceeds size threshold (57KB > 10KB)."""
        session_id = 'schema-session'
        db_path = demo_mode.get_session_db_path(session_id)

        # Create database with full Employee schema (no data)
        from sqlalchemy import create_engine
        engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(bind=engine)
        engine.dispose()

        # Employee schema alone is ~57KB, exceeding the 10KB threshold
        # This tests the actual behavior: session_has_data checks file size,
        # not whether rows exist
        assert demo_mode.session_has_data(session_id) is True

    def test_returns_true_for_populated_db(self, demo_mode_enabled, template_db, monkeypatch):
        """Should return True when database has substantial data."""
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR',
                          os.path.dirname(template_db))

        session_id = 'populated-session'
        demo_mode.initialize_session_from_template(session_id, 'small')

        assert demo_mode.session_has_data(session_id) is True


class TestInitializeSessionFromTemplate:
    """Tests for initialize_session_from_template() function."""

    def test_copies_template_to_session_db(self, demo_mode_enabled, template_db, monkeypatch):
        """Should copy template database to session path."""
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR',
                          os.path.dirname(template_db))

        session_id = 'new-session'
        result = demo_mode.initialize_session_from_template(session_id, 'small')

        assert result is True
        db_path = demo_mode.get_session_db_path(session_id)
        assert os.path.exists(db_path)
        assert os.path.getsize(db_path) > 0

    def test_preserves_template_data(self, demo_mode_enabled, template_db, monkeypatch):
        """Should preserve employee data from template."""
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR',
                          os.path.dirname(template_db))

        session_id = 'data-session'
        demo_mode.initialize_session_from_template(session_id, 'small')

        # Verify data was copied
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        db_path = demo_mode.get_session_db_path(session_id)
        engine = create_engine(f'sqlite:///{db_path}')
        Session = sessionmaker(bind=engine)
        session = Session()

        employee = session.query(Employee).filter_by(associate_id='DEMO001').first()
        assert employee is not None
        assert employee.associate == 'Demo Employee'
        assert employee.performance_rating_percent == 110.0

        session.close()
        engine.dispose()

    def test_clears_ratings_when_requested(self, demo_mode_enabled, template_db, monkeypatch):
        """Should clear manager-entered fields when clear_ratings=True."""
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR',
                          os.path.dirname(template_db))

        session_id = 'cleared-session'
        demo_mode.initialize_session_from_template(
            session_id, 'small', clear_ratings=True
        )

        # Verify ratings were cleared
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        db_path = demo_mode.get_session_db_path(session_id)
        engine = create_engine(f'sqlite:///{db_path}')
        Session = sessionmaker(bind=engine)
        session = Session()

        employee = session.query(Employee).filter_by(associate_id='DEMO001').first()
        assert employee is not None
        assert employee.performance_rating_percent is None
        assert employee.justification is None

        session.close()
        engine.dispose()

    def test_returns_false_for_missing_template(self, demo_mode_enabled, monkeypatch):
        """Should return False when template doesn't exist."""
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR', '/nonexistent/path')

        result = demo_mode.initialize_session_from_template('session', 'small')

        assert result is False

    def test_disposes_existing_engine(self, demo_mode_enabled, template_db, monkeypatch):
        """Should dispose existing engine before reinitializing."""
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR',
                          os.path.dirname(template_db))

        session_id = 'reinit-session'

        # First initialization
        demo_mode.initialize_session_from_template(session_id, 'small')
        demo_mode.get_session_engine(session_id)
        assert session_id in demo_mode._session_engines

        # Second initialization should dispose old engine
        demo_mode.initialize_session_from_template(session_id, 'small')
        assert session_id not in demo_mode._session_engines


class TestGetSessionEngine:
    """Tests for get_session_engine() function."""

    def test_creates_engine_for_new_session(self, demo_mode_enabled):
        """Should create a new engine when none exists."""
        session_id = 'engine-test'

        engine = demo_mode.get_session_engine(session_id)

        assert engine is not None
        assert session_id in demo_mode._session_engines
        assert session_id in demo_mode._session_last_access

    def test_reuses_existing_engine(self, demo_mode_enabled):
        """Should return cached engine on subsequent calls."""
        session_id = 'reuse-test'

        engine1 = demo_mode.get_session_engine(session_id)
        engine2 = demo_mode.get_session_engine(session_id)

        assert engine1 is engine2

    def test_updates_last_access_time(self, demo_mode_enabled):
        """Should update last access timestamp on each call."""
        session_id = 'access-time-test'

        demo_mode.get_session_engine(session_id)
        first_access = demo_mode._session_last_access[session_id]

        time.sleep(0.01)  # Small delay to ensure different timestamp

        demo_mode.get_session_engine(session_id)
        second_access = demo_mode._session_last_access[session_id]

        assert second_access > first_access

    def test_detects_mtime_change(self, demo_mode_enabled, template_db, monkeypatch):
        """Should recreate engine when database file is modified externally."""
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR',
                          os.path.dirname(template_db))

        session_id = 'mtime-test'
        demo_mode.initialize_session_from_template(session_id, 'small')

        engine1 = demo_mode.get_session_engine(session_id)

        # Simulate external modification (like another worker copying template)
        db_path = demo_mode.get_session_db_path(session_id)
        time.sleep(0.01)  # Ensure different mtime
        Path(db_path).touch()

        engine2 = demo_mode.get_session_engine(session_id)

        # Should be a different engine instance
        assert engine1 is not engine2

    def test_handles_deleted_database(self, demo_mode_enabled):
        """Should handle case where database file is deleted."""
        session_id = 'deleted-db-test'

        # Create engine (creates database)
        demo_mode.get_session_engine(session_id)
        db_path = demo_mode.get_session_db_path(session_id)
        assert os.path.exists(db_path)

        # Delete the database
        os.remove(db_path)

        # Getting engine again should recreate it
        engine = demo_mode.get_session_engine(session_id)
        assert engine is not None
        assert os.path.exists(db_path)


class TestCleanupStaleSessions:
    """Tests for cleanup_stale_sessions() function."""

    def test_removes_expired_sessions(self, demo_mode_enabled, monkeypatch):
        """Should remove sessions that exceed timeout."""
        monkeypatch.setattr(demo_mode, 'SESSION_TIMEOUT_SECONDS', 1)

        session_id = 'stale-session'
        demo_mode.get_session_engine(session_id)
        db_path = demo_mode.get_session_db_path(session_id)

        assert os.path.exists(db_path)
        assert session_id in demo_mode._session_engines

        # Simulate time passing
        demo_mode._session_last_access[session_id] = time.time() - 10

        demo_mode.cleanup_stale_sessions()

        assert session_id not in demo_mode._session_engines
        assert session_id not in demo_mode._session_last_access
        assert not os.path.exists(db_path)

    def test_preserves_recent_sessions(self, demo_mode_enabled, monkeypatch):
        """Should preserve sessions accessed recently."""
        monkeypatch.setattr(demo_mode, 'SESSION_TIMEOUT_SECONDS', 3600)

        session_id = 'active-session'
        demo_mode.get_session_engine(session_id)
        db_path = demo_mode.get_session_db_path(session_id)

        demo_mode.cleanup_stale_sessions()

        assert session_id in demo_mode._session_engines
        assert os.path.exists(db_path)

    def test_noop_when_demo_mode_disabled(self, temp_demo_dir, monkeypatch):
        """Should do nothing when DEMO_MODE is False."""
        monkeypatch.setattr(demo_mode, 'DEMO_MODE', False)
        monkeypatch.setattr(demo_mode, 'SESSION_DB_DIR', temp_demo_dir)

        # This should not raise even with no setup
        demo_mode.cleanup_stale_sessions()


class TestDemoResponseWrapper:
    """Tests for demo_response_wrapper() function."""

    def test_sets_cookie_when_missing(self, app):
        """Should set session cookie when not in request."""
        with app.test_request_context('/'):
            from flask import make_response
            response = make_response('test')

            wrapped = demo_mode.demo_response_wrapper(response)

            # Check cookie was set
            cookie_header = wrapped.headers.get('Set-Cookie', '')
            assert demo_mode.SESSION_COOKIE_NAME in cookie_header

    def test_does_not_overwrite_existing_cookie(self, app):
        """Should not set cookie when already present in request."""
        with app.test_request_context(
            '/',
            headers={'Cookie': f'{demo_mode.SESSION_COOKIE_NAME}=existing-id'}
        ):
            from flask import make_response
            response = make_response('test')

            wrapped = demo_mode.demo_response_wrapper(response)

            # Should not have Set-Cookie header
            cookie_header = wrapped.headers.get('Set-Cookie', '')
            assert demo_mode.SESSION_COOKIE_NAME not in cookie_header


class TestClearAllSessions:
    """Tests for clear_all_sessions() function."""

    def test_removes_all_session_files(self, demo_mode_enabled):
        """Should remove all session database files."""
        # Create multiple sessions
        for i in range(3):
            demo_mode.get_session_engine(f'session-{i}')

        session_dir = Path(demo_mode_enabled)
        assert len(list(session_dir.glob('session_*.db'))) == 3

        demo_mode.clear_all_sessions()

        assert len(list(session_dir.glob('session_*.db'))) == 0
        assert len(demo_mode._session_engines) == 0
        assert len(demo_mode._session_last_access) == 0

    def test_noop_when_demo_mode_disabled(self, temp_demo_dir, monkeypatch):
        """Should do nothing when DEMO_MODE is False."""
        monkeypatch.setattr(demo_mode, 'DEMO_MODE', False)

        # Should not raise
        demo_mode.clear_all_sessions()


class TestGetActiveSessionCount:
    """Tests for get_active_session_count() function."""

    def test_returns_zero_initially(self, demo_mode_enabled):
        """Should return 0 when no sessions exist."""
        assert demo_mode.get_active_session_count() == 0

    def test_counts_active_sessions(self, demo_mode_enabled):
        """Should return correct count of active sessions."""
        demo_mode.get_session_engine('session-1')
        demo_mode.get_session_engine('session-2')
        demo_mode.get_session_engine('session-3')

        assert demo_mode.get_active_session_count() == 3


class TestEnsureTemplatesExist:
    """Tests for ensure_templates_exist() - auto-generation of template DBs."""

    def test_generates_missing_templates(self, temp_demo_dir, monkeypatch):
        """Should generate both template DBs when they don't exist."""
        templates_dir = os.path.join(temp_demo_dir, 'demo-templates')
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR', templates_dir)

        small_path = os.path.join(templates_dir, 'small-team.db')
        large_path = os.path.join(templates_dir, 'large-team.db')

        assert not os.path.exists(small_path)
        assert not os.path.exists(large_path)

        demo_mode.ensure_templates_exist()

        assert os.path.exists(small_path)
        assert os.path.exists(large_path)
        # Templates should have real data (not just schema)
        assert os.path.getsize(small_path) > 10000
        assert os.path.getsize(large_path) > 10000

    def test_noop_when_templates_exist(self, temp_demo_dir, template_db, monkeypatch):
        """Should not regenerate when both templates already exist."""
        templates_dir = os.path.dirname(template_db)
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR', templates_dir)

        # Create the large template too
        large_path = os.path.join(templates_dir, 'large-team.db')
        shutil.copy(template_db, large_path)

        small_mtime = os.path.getmtime(template_db)
        large_mtime = os.path.getmtime(large_path)

        time.sleep(0.01)
        demo_mode.ensure_templates_exist()

        # Files should not have been touched
        assert os.path.getmtime(template_db) == small_mtime
        assert os.path.getmtime(large_path) == large_mtime

    def test_generated_templates_have_employees(self, temp_demo_dir, monkeypatch):
        """Generated templates should contain queryable employee data."""
        templates_dir = os.path.join(temp_demo_dir, 'demo-templates')
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR', templates_dir)

        demo_mode.ensure_templates_exist()

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        # Verify small team has 12 employees
        small_engine = create_engine(
            f'sqlite:///{os.path.join(templates_dir, "small-team.db")}')
        Session = sessionmaker(bind=small_engine)
        session = Session()
        assert session.query(Employee).count() == 12
        session.close()
        small_engine.dispose()

        # Verify large team has 55 employees
        large_engine = create_engine(
            f'sqlite:///{os.path.join(templates_dir, "large-team.db")}')
        Session = sessionmaker(bind=large_engine)
        session = Session()
        assert session.query(Employee).count() == 55
        session.close()
        large_engine.dispose()


class TestDemoResetEndpoint:
    """Tests for /api/demo/reset endpoint - end-to-end demo loading."""

    @pytest.fixture(autouse=True)
    def enable_demo_in_app(self, demo_mode_enabled, monkeypatch):
        """Patch app module to enable demo mode with all required imports.

        DEMO_MODE is False at import time in tests, so the conditional
        imports (get_session_id, demo_response_wrapper, etc.) never run.
        We inject them into the app module namespace for the test, then
        clean up afterwards.
        """
        import app as app_module
        monkeypatch.setattr(app_module, 'DEMO_MODE', True)

        # These attributes don't exist when DEMO_MODE was False at import,
        # so we set them directly and clean up via finalizer
        attrs_to_inject = {
            'get_session_id': demo_mode.get_session_id,
            'initialize_session_from_template': demo_mode.initialize_session_from_template,
            'demo_response_wrapper': demo_mode.demo_response_wrapper,
        }
        for name, func in attrs_to_inject.items():
            setattr(app_module, name, func)

        yield

        for name in attrs_to_inject:
            if hasattr(app_module, name):
                delattr(app_module, name)

    def test_reset_succeeds_with_generated_templates(self, app, demo_mode_enabled,
                                                      monkeypatch):
        """The /api/demo/reset endpoint should work after template generation."""
        templates_dir = os.path.join(demo_mode_enabled, 'demo-templates')
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR', templates_dir)

        # Generate templates (simulating what startup does)
        demo_mode.ensure_templates_exist()

        client = app.test_client()

        # Load small team
        response = client.post('/api/demo/reset',
                               json={'type': 'small'},
                               content_type='application/json')
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True
        assert data['demo_type'] == 'small'

    def test_reset_fails_without_templates(self, app, monkeypatch):
        """Should return success=false when templates are missing."""
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR', '/nonexistent/path')

        client = app.test_client()

        response = client.post('/api/demo/reset',
                               json={'type': 'small'},
                               content_type='application/json')
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is False

    def test_reset_with_large_team(self, app, demo_mode_enabled, monkeypatch):
        """Should support loading the large team dataset."""
        templates_dir = os.path.join(demo_mode_enabled, 'demo-templates')
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR', templates_dir)

        demo_mode.ensure_templates_exist()

        client = app.test_client()

        response = client.post('/api/demo/reset',
                               json={'type': 'large'},
                               content_type='application/json')
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True
        assert data['demo_type'] == 'large'

    def test_reset_with_clear_ratings(self, app, demo_mode_enabled, monkeypatch):
        """Should support clearing ratings on load."""
        templates_dir = os.path.join(demo_mode_enabled, 'demo-templates')
        monkeypatch.setattr(demo_mode, 'TEMPLATES_DIR', templates_dir)

        demo_mode.ensure_templates_exist()

        client = app.test_client()

        response = client.post('/api/demo/reset',
                               json={'type': 'small', 'clear_ratings': True},
                               content_type='application/json')
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True
        assert data['clear_ratings'] is True


class TestGetDemoDb:
    """Tests for get_demo_db() function."""

    def test_returns_session_for_current_request(self, app, demo_mode_enabled):
        """Should return a database session bound to the request's session ID."""
        with app.test_request_context('/'):
            db_session = demo_mode.get_demo_db()

            assert db_session is not None
            # Should be able to query (empty result is fine)
            result = db_session.query(Employee).all()
            assert isinstance(result, list)

            db_session.close()
