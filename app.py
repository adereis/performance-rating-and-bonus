#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify, send_file, make_response, Response
import os
import logging
import json
import csv
import io
import tempfile
from datetime import datetime
from collections import defaultdict
import re
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from sqlalchemy import text
from models import Employee, BonusSettings, Period, RatingSnapshot, init_db, get_db
from xlsx_utils import analyze_xlsx, parse_xlsx_employees
from notes_parser import parse_notes_field
import demo_mode
from config import Config
from services.db_helpers import (  # noqa: F401 - re-exported for tests
    load_tenets_config, convert_tenet_names_to_ids,
    get_all_employees, get_employee_by_id,
    get_bonus_settings, update_bonus_settings,
    get_manager_currency, get_filter_params,
    apply_employee_filters,
)
from services import db_helpers
from services.import_handler import (  # noqa: F401 - available for import routes
    text_unmodified, json_string_unmodified, mentor_fields_equal,
    update_text_field, update_mentor_field, update_json_field,
)
from services.bonus import (  # noqa: F401 - re-exported for tests
    calculate_bonus_for_employees, calculate_calibration_for_employees,
    calculate_mentorship_stats,
)
from services.export import (  # noqa: F401 - re-exported for tests
    build_context_markdown, resolve_tenets_text,
    write_xlsx_sheet, prepare_snapshot_data,
    HEADER_FILL, HEADER_FONT,
    SNAPSHOT_EMPLOYEE_HEADERS, SNAPSHOT_BONUS_HEADERS,
    SNAPSHOT_TALENT_HEADERS, SNAPSHOT_HISTORY_HEADERS,
)
from services.employee_utils import (  # noqa: F401 - re-exported for tests
    RATING_THRESHOLD_HIGH, RATING_THRESHOLD_MID, RATING_THRESHOLD_LOW,
    CURRENCY_FORMATS, CURRENCY_SYMBOLS, MENTOR_FIELD_PLACEHOLDERS,
    normalize_mentor_field, _parse_mentee_set, _has_tenets,
    is_employee_rated, is_employee_calibrated,
    has_direct_reports, normalize_movement_readiness,
    parse_tenure_to_months, get_tenure_band,
    get_currency_format, parse_manager_name_from_org,
    get_rating_category, is_manager,
)

# Demo mode configuration.
# Kept as a module-level global (not only on Config) because the request hooks,
# error handlers, and context processor below read it, and tests monkeypatch
# app.DEMO_MODE directly. Config.DEMO_MODE mirrors this for create_app's setup.
DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'


# ───────────────────────────────────────────────────────────────────────────
# App-level registrations (filters, context processor, hooks, error handlers).
# Defined as plain functions and wired up inside create_app(). They stay
# app-level (not in a blueprint) because they apply to every request.
# ───────────────────────────────────────────────────────────────────────────

def inject_global_context():
    """Make global config available in all templates."""
    # Get manager's currency for display
    # This is called per-request but is fast (single DB query)
    currency_code, currency_symbol = get_manager_currency()
    currency_format = get_currency_format(currency_code)

    return {
        'demo_mode': DEMO_MODE,
        'rating_thresholds': {
            'high': RATING_THRESHOLD_HIGH,
            'mid': RATING_THRESHOLD_MID,
            'low': RATING_THRESHOLD_LOW
        },
        'currency': currency_format
    }


def format_currency_filter(value, show_sign=False):
    """Format a number with the manager's currency symbol.

    Handles symbol position (before/after) and spacing based on currency conventions.
    Usage in templates: {{ amount|format_currency }} or {{ amount|format_currency(show_sign=True) }}
    """
    currency_code, _ = get_manager_currency()
    fmt = get_currency_format(currency_code)

    # Format the number
    if value >= 0:
        sign = '+' if show_sign else ''
        formatted_num = f"{sign}{value:,.0f}"
    else:
        formatted_num = f"{value:,.0f}"

    # Build the formatted string based on position and spacing
    space = ' ' if fmt['space'] else ''
    if fmt['position'] == 'before':
        return f"{fmt['symbol']}{space}{formatted_num}"
    else:
        return f"{formatted_num}{space}{fmt['symbol']}"


def format_pct_filter(value):
    """Format a percentage value, dropping a trailing '.0'.

    140.0 -> '140', 137.5 -> '137.5'. Pairs with a literal '%' in the
    template: {{ employee.performance_rating_percent|pct }}%
    """
    if value is None or value == '':
        return value
    try:
        return f'{float(value):g}'
    except (ValueError, TypeError):
        return value


def fromjson_filter(value):
    """Parse a JSON string into a Python object.

    Usage in templates: {{ json_string | fromjson }}
    Returns empty list if value is falsy or invalid JSON.
    """
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


def log_demo_request():
    """Log requests in demo mode for debugging."""
    if DEMO_MODE and request.endpoint not in ('static', 'core.health_check'):
        from demo_mode import get_session_id, _log
        sid = get_session_id()[:8]
        _log(f">>> {request.method} {request.path} [session:{sid}]")


def add_demo_session_cookie(response):
    """Add session cookie in demo mode."""
    if DEMO_MODE:
        return demo_mode.demo_response_wrapper(response)
    return response


def handle_exception(error):
    """Handle all exceptions with clean logging and error page.

    Catches exceptions before Flask's default handler to prevent
    verbose tracebacks in production logs.
    """
    from werkzeug.exceptions import HTTPException
    from models import DatabaseSchemaError

    # Pass through HTTP exceptions (404, etc.) to default handlers
    if isinstance(error, HTTPException):
        return error

    # For other exceptions (database errors, etc.), log concisely
    error_type = type(error).__name__
    error_msg = str(error)

    # One-line log: "DatabaseError: unable to open database file"
    app.logger.error(f"{error_type}: {error_msg}")

    # Schema errors get a specific, helpful error page
    if isinstance(error, DatabaseSchemaError):
        return render_template('error.html',
            error_code=500,
            error_title="Database Update Required",
            error_message="Your database was created with an older version and needs to be recreated. "
                          "Delete 'ratings.db' and re-import your Workday data. "
                          "(Workday is the source of truth, so no data will be lost.)",
            demo_mode=DEMO_MODE,
            show_reset=DEMO_MODE
        ), 500

    # Return a clean error page
    return render_template('error.html',
        error_code=500,
        error_title="Something went wrong",
        error_message="The server encountered an error. Please try refreshing the page.",
        demo_mode=DEMO_MODE,
        show_reset=DEMO_MODE
    ), 500


def internal_error(error):
    """Handle 500 errors (fallback if Exception handler doesn't catch)."""
    error_msg = str(error.original_exception) if hasattr(error, 'original_exception') else str(error)
    app.logger.error(f"Internal error: {error_msg}")

    return render_template('error.html',
        error_code=500,
        error_title="Something went wrong",
        error_message="The server encountered an error. Please try refreshing the page.",
        demo_mode=DEMO_MODE,
        show_reset=DEMO_MODE
    ), 500


def _configure_logging():
    """Concise logging in production (no verbose tracebacks for handled errors)."""
    if os.getenv('FLASK_ENV') == 'production':
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)


def _register_blueprints(flask_app):
    """Register all route blueprints on the app.

    Imported here (not at module top) so app-level globals are defined first.
    Blueprints never `import app` — that would break `python app.py`, where app
    runs as __main__ — so they read config via demo_mode/models/services.
    See docs/REFACTOR_APP_SPLIT.md.
    """
    from blueprints.core import core_bp
    from blueprints.export import export_bp
    from blueprints.history import history_bp
    from blueprints.import_ import import_bp
    from blueprints.analytics import analytics_bp
    from blueprints.bonus import bonus_bp
    from blueprints.rate import rate_bp
    from blueprints.calibrate import calibrate_bp

    for bp in (core_bp, export_bp, history_bp, import_bp,
               analytics_bp, bonus_bp, rate_bp, calibrate_bp):
        flask_app.register_blueprint(bp)


def create_app(config=None):
    """Application factory.

    Builds and configures the Flask app: config (with the production SECRET_KEY
    fail-fast), logging, DB init, demo-mode startup, app-level registrations,
    and blueprints. A module-level ``app = create_app()`` below keeps
    ``from app import app`` working for tests, `python app.py`, and tooling.
    """
    config = config or Config()
    _configure_logging()

    flask_app = Flask(__name__)
    flask_app.secret_key = config.SECRET_KEY
    flask_app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

    # Initialize database on startup
    init_db()

    # Start demo mode cleanup thread if enabled
    if config.DEMO_MODE:
        demo_mode.ensure_templates_exist()
        demo_mode.clear_all_sessions()
        demo_mode.start_cleanup_thread()
        demo_mode._log("Session isolation enabled")

    # App-level registrations
    flask_app.context_processor(inject_global_context)
    flask_app.template_filter('format_currency')(format_currency_filter)
    flask_app.template_filter('pct')(format_pct_filter)
    flask_app.template_filter('fromjson')(fromjson_filter)
    flask_app.before_request(log_demo_request)
    flask_app.after_request(add_demo_session_cookie)
    flask_app.errorhandler(Exception)(handle_exception)
    flask_app.errorhandler(500)(internal_error)

    _register_blueprints(flask_app)

    return flask_app


app = create_app()


if __name__ == '__main__':
    print("\n" + "="*60)
    print("Performance Rating System")
    print("="*60)

    if DEMO_MODE:
        print("Mode: DEMO (session isolation enabled)")
        print(f"Session timeout: {os.getenv('SESSION_TIMEOUT_SECONDS', 3600)}s")
    else:
        print(f"Database: {os.getenv('DATABASE_URL', 'sqlite:///ratings.db')}")

    # Allow host to be configured via environment variable (for Docker)
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    port = int(os.getenv('FLASK_PORT', '5000'))
    debug = os.getenv('FLASK_ENV') == 'development'

    print(f"Starting web server at http://{host}:{port}")
    print(f"Health check: http://{host}:{port}/health")
    print("Press Ctrl+C to stop")
    print("="*60 + "\n")

    app.run(debug=debug, host=host, port=port)
