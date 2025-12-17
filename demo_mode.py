"""
Demo mode functionality for cloud deployment.

Provides session-based database isolation so each visitor gets their own sandbox.
Uses pre-built template databases for consistent demo experience.
"""
import os
import uuid
import time
import threading
import shutil
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from flask import request, g


# Configuration
DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'
SESSION_TIMEOUT_SECONDS = int(os.getenv('SESSION_TIMEOUT_SECONDS', 3600))  # 1 hour default
SESSION_COOKIE_NAME = 'demo_session_id'
SESSION_DB_DIR = os.getenv('SESSION_DB_DIR', '/tmp/demo_sessions')

# Path to pre-built template databases
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, 'demo-templates')

# Session tracking
_session_engines = {}
_session_last_access = {}
_session_db_mtime = {}  # Track DB file modification time to detect changes from other workers
_cleanup_lock = threading.Lock()


def get_session_id():
    """Get or create a session ID from cookie.

    Uses Flask's g object to cache the session ID within a single request,
    ensuring all calls return the same value (critical for cookie consistency).
    """
    # Return cached session ID if we already generated one this request
    if hasattr(g, '_demo_session_id'):
        return g._demo_session_id

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        session_id = str(uuid.uuid4())

    # Cache for this request so all calls return the same ID
    g._demo_session_id = session_id
    return session_id


def get_session_db_path(session_id):
    """Get the database file path for a session."""
    Path(SESSION_DB_DIR).mkdir(parents=True, exist_ok=True)
    return os.path.join(SESSION_DB_DIR, f'session_{session_id}.db')


def get_template_path(demo_type='small'):
    """Get the path to a template database."""
    if demo_type == 'large':
        return os.path.join(TEMPLATES_DIR, 'large-team.db')
    return os.path.join(TEMPLATES_DIR, 'small-team.db')


def session_has_data(session_id):
    """Check if a session already has a database with data."""
    db_path = get_session_db_path(session_id)
    # Check if database exists and has reasonable size (not just schema)
    return os.path.exists(db_path) and os.path.getsize(db_path) > 10000


def _remove_session_files(db_path):
    """Remove a session database and its WAL mode files (.db-wal, .db-shm)."""
    for suffix in ['', '-wal', '-shm']:
        file_path = db_path + suffix if suffix else db_path
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"[Demo Mode] Error removing {file_path}: {e}")


def initialize_session_from_template(session_id, demo_type='small'):
    """
    Initialize a session database by copying a template.

    Args:
        session_id: The session ID
        demo_type: 'small' or 'large'

    Returns:
        bool: True if successful, False otherwise
    """
    global _session_engines, _session_db_mtime

    template_path = get_template_path(demo_type)
    db_path = get_session_db_path(session_id)

    # Close existing engine if any
    if session_id in _session_engines:
        try:
            _session_engines[session_id].dispose()
        except Exception:
            pass
        del _session_engines[session_id]

    # Clear mtime tracking so next access creates fresh engine
    if session_id in _session_db_mtime:
        del _session_db_mtime[session_id]

    # Remove existing database AND its WAL files
    _remove_session_files(db_path)

    # Copy template
    if not os.path.exists(template_path):
        print(f"[Demo Mode] Template not found: {template_path}")
        # Fall back to creating empty database
        return False

    try:
        shutil.copy2(template_path, db_path)
        print(f"[Demo Mode] Initialized session {session_id[:8]}... with {demo_type} template")
        return True
    except Exception as e:
        print(f"[Demo Mode] Error copying template: {e}")
        return False


def _create_sqlite_engine(db_path):
    """Create a SQLite engine with settings optimized for concurrency.

    Uses WAL (Write-Ahead Logging) mode for better concurrent access:
    - Multiple readers can access simultaneously
    - Writers don't block readers
    - Better performance under Gunicorn with multiple workers
    """
    engine = create_engine(
        f'sqlite:///{db_path}',
        echo=False,
        connect_args={"check_same_thread": False},  # Required for multi-threaded access
        pool_pre_ping=True,  # Verify connections before using
    )

    # Enable WAL mode for better concurrency
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s for locks
        cursor.close()

    return engine


def get_session_engine(session_id):
    """Get or create a SQLAlchemy engine for a session.

    Handles multi-worker scenarios by checking if the database file has been
    modified since we created the engine (e.g., by another Gunicorn worker
    copying a template). If so, we recreate the engine to pick up the changes.
    """
    global _session_engines, _session_last_access, _session_db_mtime

    db_path = get_session_db_path(session_id)

    # Check if we need to recreate the engine (file was modified externally)
    if session_id in _session_engines and os.path.exists(db_path):
        current_mtime = os.path.getmtime(db_path)
        cached_mtime = _session_db_mtime.get(session_id, 0)
        if current_mtime > cached_mtime:
            # Database was modified by another worker, recreate engine
            try:
                _session_engines[session_id].dispose()
            except Exception:
                pass
            del _session_engines[session_id]
            print(f"[Demo Mode] Recreating engine for {session_id[:8]}... (file changed)")

    if session_id not in _session_engines:
        # If database doesn't exist, create empty schema
        # (Data will be populated when user selects demo type)
        if not os.path.exists(db_path):
            # Create empty database with schema
            engine = _create_sqlite_engine(db_path)
            from models import Base
            Base.metadata.create_all(bind=engine)
            _session_engines[session_id] = engine
        else:
            # Database exists, just create engine
            engine = _create_sqlite_engine(db_path)
            _session_engines[session_id] = engine

        # Track the file's mtime so we can detect changes
        if os.path.exists(db_path):
            _session_db_mtime[session_id] = os.path.getmtime(db_path)

    # Update last access time
    _session_last_access[session_id] = time.time()

    return _session_engines[session_id]


def get_demo_db():
    """Get a database session for the current demo session."""
    session_id = get_session_id()
    engine = get_session_engine(session_id)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def reset_session_data(session_id, demo_type='small'):
    """
    Reset a session's database to a fresh template.

    Args:
        session_id: The session ID
        demo_type: 'small' or 'large'

    Returns:
        bool: True if successful
    """
    return initialize_session_from_template(session_id, demo_type)


def cleanup_stale_sessions():
    """Remove session databases that haven't been accessed recently."""
    global _session_engines, _session_last_access

    if not DEMO_MODE:
        return

    with _cleanup_lock:
        current_time = time.time()
        stale_sessions = []

        for session_id, last_access in list(_session_last_access.items()):
            if current_time - last_access > SESSION_TIMEOUT_SECONDS:
                stale_sessions.append(session_id)

        for session_id in stale_sessions:
            try:
                # Close and remove engine
                if session_id in _session_engines:
                    _session_engines[session_id].dispose()
                    del _session_engines[session_id]

                # Remove database and WAL files
                db_path = get_session_db_path(session_id)
                _remove_session_files(db_path)

                # Remove from tracking
                if session_id in _session_last_access:
                    del _session_last_access[session_id]
                if session_id in _session_db_mtime:
                    del _session_db_mtime[session_id]

                print(f"[Demo Mode] Cleaned up stale session: {session_id[:8]}...")
            except Exception as e:
                print(f"[Demo Mode] Error cleaning session {session_id[:8]}: {e}")


def clear_all_sessions():
    """Clear all session databases on startup for a fresh experience."""
    global _session_engines, _session_last_access, _session_db_mtime

    if not DEMO_MODE:
        return

    # Close all existing engines
    for session_id, engine in list(_session_engines.items()):
        try:
            engine.dispose()
        except Exception:
            pass

    _session_engines = {}
    _session_last_access = {}
    _session_db_mtime = {}

    # Remove all session database files (including WAL mode files)
    session_dir = Path(SESSION_DB_DIR)
    if session_dir.exists():
        count = 0
        # Get all .db files, then remove them along with their WAL files
        for db_file in session_dir.glob('session_*.db'):
            _remove_session_files(str(db_file))
            count += 1
        if count > 0:
            print(f"[Demo Mode] Cleared {count} session(s) from previous run")


def start_cleanup_thread():
    """Start background thread for session cleanup."""
    if not DEMO_MODE:
        return

    # Clear old sessions on startup for fresh experience
    clear_all_sessions()

    def cleanup_loop():
        while True:
            time.sleep(300)  # Run every 5 minutes
            cleanup_stale_sessions()

    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()
    print("[Demo Mode] Started session cleanup thread")


def demo_response_wrapper(response):
    """Add session cookie to response if needed."""
    session_id = get_session_id()

    # Only set cookie if it wasn't already in the request
    if SESSION_COOKIE_NAME not in request.cookies:
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session_id,
            max_age=SESSION_TIMEOUT_SECONDS,
            httponly=True,
            samesite='Lax'
        )

    return response


def get_active_session_count():
    """Get the number of active demo sessions."""
    return len(_session_engines)
