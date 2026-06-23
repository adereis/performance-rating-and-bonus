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

app = Flask(__name__)

# Configure logging to reduce noise from exceptions
# Show only the error type and message, not full tracebacks for handled errors
if os.getenv('FLASK_ENV') == 'production':
    # In production, log errors concisely
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Reduce verbosity of werkzeug and SQLAlchemy loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

# Session security - required for secure cookies in production
# In production, set SECRET_KEY environment variable to a random 32+ character string
# Example: export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
app.secret_key = os.getenv('SECRET_KEY', 'dev-only-insecure-key-change-in-production')

# Cap upload size to prevent disk/memory exhaustion from oversized files.
# Workday XLSX exports are small; 10 MB is generous. Override via MAX_UPLOAD_MB.
# Flask returns 413 (Request Entity Too Large) automatically when exceeded.
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_MB', '10')) * 1024 * 1024

# Demo mode configuration
DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'

# Constants and utility functions imported from services.employee_utils

# Initialize database on startup
init_db()

# Start demo mode cleanup thread if enabled
if DEMO_MODE:
    from demo_mode import (
        start_cleanup_thread, clear_all_sessions, demo_response_wrapper,
        get_session_id, initialize_session_from_template,
        ensure_templates_exist
    )
    from demo_mode import _log
    ensure_templates_exist()
    clear_all_sessions()
    start_cleanup_thread()
    _log("Session isolation enabled")


@app.context_processor
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


@app.template_filter('format_currency')
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


@app.template_filter('pct')
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


@app.template_filter('fromjson')
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


@app.before_request
def log_demo_request():
    """Log requests in demo mode for debugging."""
    if DEMO_MODE and request.endpoint not in ('static', 'health_check'):
        from demo_mode import get_session_id, _log
        sid = get_session_id()[:8]
        _log(f">>> {request.method} {request.path} [session:{sid}]")


@app.after_request
def add_demo_session_cookie(response):
    """Add session cookie in demo mode."""
    if DEMO_MODE:
        return demo_response_wrapper(response)
    return response


@app.route('/health')
def health_check():
    """Health check endpoint for load balancers and monitoring.

    In demo mode, checks template availability without creating a session.
    In production mode, checks actual database connectivity.
    """
    status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'demo_mode': DEMO_MODE
    }

    if DEMO_MODE:
        # Check demo infrastructure without creating a session
        from demo_mode import get_template_path, SESSION_DB_DIR, get_active_session_count
        import os
        from pathlib import Path

        status['active_sessions'] = get_active_session_count()

        # Verify templates exist (required to create new sessions)
        small_template = get_template_path('small')
        large_template = get_template_path('large')
        templates_ok = os.path.exists(small_template) and os.path.exists(large_template)
        status['templates'] = 'available' if templates_ok else 'missing'

        # Verify session directory is writable
        try:
            Path(SESSION_DB_DIR).mkdir(parents=True, exist_ok=True)
            test_file = os.path.join(SESSION_DB_DIR, '.health_check')
            Path(test_file).touch()
            os.remove(test_file)
            status['session_dir'] = 'writable'
        except Exception as e:
            status['session_dir'] = 'error'
            status['session_dir_error'] = str(e)
            status['status'] = 'unhealthy'
            return jsonify(status), 503

        if not templates_ok:
            status['status'] = 'unhealthy'
            return jsonify(status), 503
    else:
        # Production mode: check actual database connectivity
        try:
            db = get_db()
            db.execute(text('SELECT 1'))
            db.close()
            status['database'] = 'connected'
        except Exception as e:
            status['database'] = 'error'
            status['database_error'] = str(e)
            return jsonify(status), 503

    return jsonify(status)


# Error handlers for cleaner error pages and logs
@app.errorhandler(Exception)
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


@app.errorhandler(500)
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


@app.route('/demo/<demo_type>')
def demo_init(demo_type):
    """Initialize demo with specified dataset type."""
    from flask import redirect, url_for

    if not DEMO_MODE:
        return redirect(url_for('index'))

    if demo_type not in ('small', 'large'):
        demo_type = 'small'

    session_id = get_session_id()
    success = initialize_session_from_template(session_id, demo_type)

    if success:
        return redirect(url_for('rate_page'))
    else:
        return redirect(url_for('index'))


@app.route('/api/demo/reset', methods=['POST'])
def demo_reset():
    """Reset demo data to a fresh template."""
    if not DEMO_MODE:
        return jsonify({'success': False, 'error': 'Not in demo mode'}), 400

    data = request.get_json() or {}
    demo_type = data.get('type', 'small')
    clear_ratings = data.get('clear_ratings', False)

    if demo_type not in ('small', 'large'):
        demo_type = 'small'

    session_id = get_session_id()
    success = initialize_session_from_template(session_id, demo_type, clear_ratings=clear_ratings)

    return jsonify({
        'success': success,
        'demo_type': demo_type,
        'clear_ratings': clear_ratings,
        'message': f'Demo reset to {demo_type} team dataset' if success else 'Failed to reset demo'
    })


@app.route('/')
def index():
    """Main dashboard page."""
    from models import get_cross_cycle_alignment

    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    total_employees = len(team_data)
    rated_employees = sum(1 for emp in team_data if is_employee_rated(emp))
    unrated_employees = total_employees - rated_employees

    # Calculate average rating
    ratings = [emp.get('performance_rating_percent') for emp in team_data if emp.get('performance_rating_percent')]
    avg_rating = sum(ratings) / len(ratings) if ratings else None

    stats = {
        'total': total_employees,
        'rated': rated_employees,
        'unrated': unrated_employees,
        'avg_rating': avg_rating
    }

    # Calculate cross-cycle alignment data
    alignment_data = []
    alignment_stats = {'aligned': 0, 'review': 0, 'incomplete': 0}

    for emp in team_data:
        # Special case employees (bonus override) get special alignment status
        if emp.get('bonus_override_percent') is not None:
            emp['alignment'] = 'special_case'
            emp['alignment_detail'] = 'bonus_override'
            # Don't count in alignment stats - they're excluded from normal distribution
            continue

        bonus_pct = emp.get('performance_rating_percent')
        talent_overall = emp.get('talent_overall_perf')
        alignment = get_cross_cycle_alignment(bonus_pct, talent_overall)
        alignment_stats[alignment] += 1

        # Add alignment to employee for display in Team Overview table
        emp['alignment'] = alignment
        # Set detail for incomplete cases so template can show specific messages
        if alignment == 'incomplete':
            if bonus_pct is None and talent_overall is not None:
                emp['alignment_detail'] = 'missing_rating'
            elif bonus_pct is not None and talent_overall is None:
                emp['alignment_detail'] = 'missing_talent'
            else:
                emp['alignment_detail'] = None
        else:
            emp['alignment_detail'] = None

        # Only include employees with some data for the alignment table
        if bonus_pct is not None or talent_overall is not None:
            alignment_data.append({
                'associate_id': emp.get('Associate ID'),
                'name': emp.get('Associate'),
                'bonus_pct': bonus_pct,
                'talent_overall': talent_overall,
                'alignment': alignment,
            })

    # Stamp calibration status on each employee for template display, and count
    for emp in team_data:
        emp['is_calibrated'] = is_employee_calibrated(emp)
    calibrated_count = sum(1 for emp in team_data if emp['is_calibrated'])

    # Track employees ready for promotion (Movement Readiness = "Ready Now...")
    promotion_ready = [emp for emp in team_data
                       if (emp.get('talent_movement_readiness') or '').startswith('Ready Now')]

    # Check for historical data if no current employees
    historical_info = None
    if total_employees == 0:
        db = get_db()
        try:
            period_count = db.query(Period).count()
            if period_count > 0:
                # Get most recent period
                latest_period = db.query(Period).order_by(Period.archived_at.desc()).first()
                snapshot_count = db.query(RatingSnapshot).count()
                historical_info = {
                    'period_count': period_count,
                    'snapshot_count': snapshot_count,
                    'latest_period_name': latest_period.name if latest_period else None
                }
        finally:
            db.close()

    return render_template('index.html', team=team_data, stats=stats, filter_info=filter_info,
                         demo_mode=DEMO_MODE, historical_info=historical_info,
                         alignment_data=alignment_data, alignment_stats=alignment_stats,
                         calibrated_count=calibrated_count, promotion_ready=promotion_ready)


@app.route('/rate')
def rate_page():
    """Rating form page."""
    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees (bonus cycle only)
    all_employees = get_all_employees(bonus_cycle_only=True)

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Pre-compute rating status for each employee
    for emp in team_data:
        # Parse tenets and check counts: 3 strengths required, 2-3 improvements required
        strengths_count = 0
        improvements_count = 0
        try:
            strengths_raw = emp.get('tenets_strengths')
            if strengths_raw and strengths_raw != '[]':
                strengths_count = len(json.loads(strengths_raw))
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            improvements_raw = emp.get('tenets_improvements')
            if improvements_raw and improvements_raw != '[]':
                improvements_count = len(json.loads(improvements_raw))
        except (json.JSONDecodeError, TypeError):
            pass

        has_valid_tenets = (strengths_count >= 3) and (improvements_count >= 2)
        emp['_is_rated'] = bool(
            emp.get('performance_rating_percent') is not None and
            emp.get('justification') and
            has_valid_tenets
        )
        emp['_has_override'] = emp.get('bonus_override_percent') is not None
        emp['_is_complete'] = emp['_is_rated'] or emp['_has_override']

    # Count completed employees (rated OR override)
    rated_count = sum(1 for e in team_data if e['_is_complete'])

    # Check if bonus data has been imported (employees have bonus targets)
    employees_with_bonus_targets = [
        emp for emp in team_data
        if emp.get('Bonus Target Manager Currency') or emp.get('Bonus Target - Local Currency')
    ]
    has_bonus_data = len(employees_with_bonus_targets) > 0

    # Detect multi-team scenario and group by supervisory organization
    unique_orgs = set()
    for emp in team_data:
        org = emp.get('Supervisory Organization')
        if org:
            unique_orgs.add(org)

    is_multi_team = len(unique_orgs) > 1

    # Group employees by supervisory organization for multi-team view
    teams_grouped = []
    if is_multi_team:
        teams_by_org = {}
        for emp in team_data:
            org = emp.get('Supervisory Organization', 'Unknown')
            if org not in teams_by_org:
                teams_by_org[org] = []
            teams_by_org[org].append(emp)

        # Build grouped structure with per-team rating counts
        for org, members in sorted(teams_by_org.items()):
            team_rated = sum(1 for e in members if e['_is_complete'])
            teams_grouped.append({
                'org': org,
                'members': members,
                'total': len(members),
                'rated': team_rated,
            })

    return render_template(
        'rate.html',
        team=team_data,
        teams_grouped=teams_grouped,
        is_multi_team=is_multi_team,
        filter_info=filter_info,
        rated_count=rated_count,
        has_bonus_data=has_bonus_data,
    )


@app.route('/api/rate', methods=['POST'])
def rate_employee():
    """API endpoint to rate an employee and save additional manager inputs.

    Only updates fields that are explicitly provided in the request.
    This allows partial updates (e.g., compact view only sends rating).
    """
    # Check if bonus data has been imported before allowing ratings
    all_employees = get_all_employees(bonus_cycle_only=True)
    employees_with_bonus_targets = [
        emp for emp in all_employees
        if emp.get('Bonus Target Manager Currency') or emp.get('Bonus Target - Local Currency')
    ]
    if not employees_with_bonus_targets:
        return jsonify({'error': 'Cannot save ratings until bonus data is imported'}), 400

    data = request.get_json()
    associate_id = data.get('associate_id')

    if not associate_id:
        return jsonify({'error': 'Missing associate ID'}), 400

    # Validate rating percent if provided
    rating_percent = None
    if 'rating_percent' in data:
        rating_value = data.get('rating_percent')
        if rating_value is not None and rating_value != '':
            try:
                rating_percent = float(rating_value)
                if rating_percent < 0 or rating_percent > 200:
                    return jsonify({'error': 'Rating must be between 0 and 200'}), 400
            except ValueError:
                return jsonify({'error': 'Invalid rating value'}), 400

    # Get optional fields (only if provided in request)
    tenets_strengths = data.get('tenets_strengths', []) if 'tenets_strengths' in data else None
    tenets_improvements = data.get('tenets_improvements', []) if 'tenets_improvements' in data else None

    # Validate tenets data if provided
    if tenets_strengths is not None:
        if tenets_strengths and not isinstance(tenets_strengths, list):
            return jsonify({'error': 'Tenets strengths must be an array'}), 400
        # Validate count (exactly 3 strengths if provided and non-empty)
        if tenets_strengths and len(tenets_strengths) != 3:
            return jsonify({'error': 'Must select exactly 3 strength tenets'}), 400

    if tenets_improvements is not None:
        if tenets_improvements and not isinstance(tenets_improvements, list):
            return jsonify({'error': 'Tenets improvements must be an array'}), 400
        # Validate count (2-3 improvements if provided and non-empty)
        if tenets_improvements and (len(tenets_improvements) < 2 or len(tenets_improvements) > 3):
            return jsonify({'error': 'Must select 2 or 3 improvement tenets'}), 400

    # Validate no duplicates between lists (if both provided)
    if tenets_strengths and tenets_improvements:
        if set(tenets_strengths) & set(tenets_improvements):
            return jsonify({'error': 'Cannot select the same tenet as both strength and improvement'}), 400

    db = get_db()
    try:
        employee = db.query(Employee).filter(Employee.associate_id == associate_id).first()

        if not employee:
            return jsonify({'error': 'Employee not found'}), 404

        # Only update fields that were explicitly provided in the request
        # Track fields that were normalized from placeholder values
        normalized_fields = []

        if 'rating_percent' in data:
            employee.performance_rating_percent = rating_percent
        if 'justification' in data:
            employee.justification = data.get('justification', '')
        if 'mentor' in data:
            mentor_value, was_placeholder = normalize_mentor_field(data.get('mentor', ''))
            employee.mentor = mentor_value
            if was_placeholder:
                normalized_fields.append('mentor')
        if 'mentees' in data:
            mentees_value, was_placeholder = normalize_mentor_field(data.get('mentees', ''))
            employee.mentees = mentees_value
            if was_placeholder:
                normalized_fields.append('mentees')
        if tenets_strengths is not None:
            employee.tenets_strengths = json.dumps(tenets_strengths) if tenets_strengths else None
        if tenets_improvements is not None:
            employee.tenets_improvements = json.dumps(tenets_improvements) if tenets_improvements else None

        # Special case handling (bonus override for pro-rata leave, etc.)
        if 'bonus_override_percent' in data:
            override_value = data.get('bonus_override_percent')
            if override_value is not None and override_value != '':
                try:
                    override_pct = float(override_value)
                    if override_pct < 0 or override_pct > 200:
                        return jsonify({'error': 'Bonus override must be between 0 and 200'}), 400
                    employee.bonus_override_percent = override_pct
                except ValueError:
                    return jsonify({'error': 'Invalid bonus override value'}), 400
            else:
                # Clear override if empty/null
                employee.bonus_override_percent = None
        if 'special_case_notes' in data:
            employee.special_case_notes = data.get('special_case_notes', '') or None

        employee.last_updated = datetime.now()

        db.commit()

        response = {'success': True, 'message': 'Rating saved successfully'}
        if normalized_fields:
            response['normalized_fields'] = normalized_fields
        return jsonify(response)
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# TALENT CALIBRATION ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

# Talent calibration enum values (from Spec §3)
TALENT_PERF_WHAT_VALUES = [
    'Surpasses Expectations',
    'Meets Expectations',
    'Meets Some Expectations',
    'Does Not Meet Expectations',
]

TALENT_PERF_HOW_VALUES = [
    'Surpasses Expectations',
    'Meets Expectations',
    'Meets Some Expectations',
    'Does Not Meet Expectations',
]

TALENT_AGILITY_VALUES = [
    'Always/Most of the Time',
    'Sometimes',
]

TALENT_MOVEMENT_VALUES = [
    'Continue growing in current role',
    'Ready Now to be promoted in current role',
    'Ready for lateral move',
    'Ready to be promoted outside of current role',
    'Not well placed',
]


@app.route('/calibrate')
def calibrate_page():
    """Talent calibration page."""
    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Pre-compute calibration status for consistent Jinja/JS validation
    for emp in team_data:
        emp['_is_calibrated'] = is_employee_calibrated(emp)
        emp['_has_tenets'] = _has_tenets(
            emp.get('talent_tenets_strengths'),
            emp.get('talent_tenets_improvements')
        )

    # Count calibrated employees (What + How + Actions + Tenets)
    calibrated_count = sum(1 for e in team_data if e['_is_calibrated'])

    # Check if talent data has been imported (employees have Workday talent fields)
    # We check for _original fields (set during talent import) or historical fields
    employees_with_talent_data = [
        emp for emp in team_data
        if emp.get('talent_perf_what_original') or emp.get('talent_perf_how_original')
        or emp.get('talent_last_overall_perf') or emp.get('talent_last_identified_future')
    ]
    has_talent_data = len(employees_with_talent_data) > 0

    # Detect multi-team scenario and group by supervisory organization
    unique_orgs = set()
    for emp in team_data:
        org = emp.get('Supervisory Organization')
        if org:
            unique_orgs.add(org)

    is_multi_team = len(unique_orgs) > 1

    # Group employees by supervisory organization for multi-team view
    teams_grouped = []
    if is_multi_team:
        teams_by_org = {}
        for emp in team_data:
            org = emp.get('Supervisory Organization', 'Unknown')
            if org not in teams_by_org:
                teams_by_org[org] = []
            teams_by_org[org].append(emp)

        # Build grouped structure with per-team calibration counts
        for org, members in sorted(teams_by_org.items()):
            team_calibrated = sum(1 for e in members if e['_is_calibrated'])
            teams_grouped.append({
                'org': org,
                'members': members,
                'total': len(members),
                'calibrated': team_calibrated,
            })

    return render_template(
        'calibrate.html',
        team=team_data,
        teams_grouped=teams_grouped,
        is_multi_team=is_multi_team,
        filter_info=filter_info,
        calibrated_count=calibrated_count,
        has_talent_data=has_talent_data,
        perf_what_values=TALENT_PERF_WHAT_VALUES,
        perf_how_values=TALENT_PERF_HOW_VALUES,
        agility_values=TALENT_AGILITY_VALUES,
        movement_values=TALENT_MOVEMENT_VALUES,
    )


@app.route('/api/calibrate', methods=['POST'])
def calibrate_employee():
    """API endpoint to save talent calibration data.

    Accepts talent assessment fields and computes derived values:
    - talent_overall_perf from talent_perf_what + talent_perf_how
    - talent_identified_future from talent_growth_agility + talent_change_agility
    """
    from models import derive_overall_performance, derive_future_talent

    # Check if talent data has been imported before allowing calibration
    all_employees = get_all_employees()
    employees_with_talent_data = [
        emp for emp in all_employees
        if emp.get('talent_perf_what_original') or emp.get('talent_perf_how_original')
        or emp.get('talent_last_overall_perf') or emp.get('talent_last_identified_future')
    ]
    if not employees_with_talent_data:
        return jsonify({'error': 'Cannot save calibration until talent data is imported'}), 400

    data = request.get_json()
    associate_id = data.get('associate_id')

    if not associate_id:
        return jsonify({'success': False, 'error': 'Missing associate ID'}), 400

    db = get_db()
    try:
        employee = db.query(Employee).filter_by(associate_id=associate_id).first()
        if not employee:
            db.close()
            return jsonify({'success': False, 'error': f'Employee not found: {associate_id}'}), 404

        # Validate and update talent fields
        talent_fields = [
            ('talent_perf_what', TALENT_PERF_WHAT_VALUES),
            ('talent_perf_how', TALENT_PERF_HOW_VALUES),
            ('talent_growth_agility', TALENT_AGILITY_VALUES),
            ('talent_change_agility', TALENT_AGILITY_VALUES),
            ('talent_movement_readiness', TALENT_MOVEMENT_VALUES),
        ]

        for field, valid_values in talent_fields:
            if field in data:
                value = data.get(field)
                if value:
                    # Sanitize: strip whitespace and normalize unicode (NFKC handles
                    # non-breaking spaces, fullwidth chars, compatibility forms)
                    import unicodedata
                    value = unicodedata.normalize('NFKC', value.strip())

                    # Case-insensitive validation with normalization to canonical casing
                    value_lower = value.lower()
                    matched_value = next(
                        (v for v in valid_values if v.lower() == value_lower),
                        None
                    )
                    if matched_value is None:
                        return jsonify({
                            'success': False,
                            'error': f"Invalid value for {field}: '{value}'. Must be one of: {', '.join(valid_values)}"
                        }), 400
                    # Use canonical casing from valid_values
                    setattr(employee, field, matched_value)
                else:
                    setattr(employee, field, None)

        # Update free-form text fields
        # Track fields that were normalized from placeholder values
        normalized_fields = []

        text_fields = [
            'talent_proposed_actions',
            'talent_promo_job_profile',
            'talent_promo_business_need',
            'talent_promo_role_scope',
            'talent_promo_readiness',
        ]
        # Mentor/mentee fields need placeholder normalization
        mentor_text_fields = ['talent_mentor', 'talent_mentees']

        for field in text_fields:
            if field in data:
                value = data.get(field)
                setattr(employee, field, value if value else None)

        for field in mentor_text_fields:
            if field in data:
                value, was_placeholder = normalize_mentor_field(data.get(field, ''))
                setattr(employee, field, value if value else None)
                if was_placeholder:
                    normalized_fields.append(field)

        # Validate talent tenets before updating
        talent_tenets_strengths = data.get('talent_tenets_strengths', []) if 'talent_tenets_strengths' in data else None
        talent_tenets_improvements = data.get('talent_tenets_improvements', []) if 'talent_tenets_improvements' in data else None

        if talent_tenets_strengths is not None:
            if talent_tenets_strengths and not isinstance(talent_tenets_strengths, list):
                return jsonify({'success': False, 'error': 'Talent tenets strengths must be an array'}), 400
            # Validate count (exactly 3 strengths if provided and non-empty)
            if talent_tenets_strengths and len(talent_tenets_strengths) != 3:
                return jsonify({'success': False, 'error': 'Must select exactly 3 strength tenets'}), 400

        if talent_tenets_improvements is not None:
            if talent_tenets_improvements and not isinstance(talent_tenets_improvements, list):
                return jsonify({'success': False, 'error': 'Talent tenets improvements must be an array'}), 400
            # Validate count (2-3 improvements if provided and non-empty)
            if talent_tenets_improvements and (len(talent_tenets_improvements) < 2 or len(talent_tenets_improvements) > 3):
                return jsonify({'success': False, 'error': 'Must select 2 or 3 improvement tenets'}), 400

        # Validate no duplicates between lists (if both provided)
        if talent_tenets_strengths and talent_tenets_improvements:
            if set(talent_tenets_strengths) & set(talent_tenets_improvements):
                return jsonify({'success': False, 'error': 'Cannot select the same tenet as both strength and improvement'}), 400

        # Update talent tenets (JSON arrays)
        # Layer 3: Only update if tenets is a non-empty list (defensive check)
        # Empty arrays now mean "no change" rather than "clear" - this prevents
        # race conditions where unrendered checkboxes send empty arrays
        if 'talent_tenets_strengths' in data:
            tenets = data.get('talent_tenets_strengths')
            if isinstance(tenets, list) and tenets:  # Only update if non-empty list
                import json
                employee.talent_tenets_strengths = json.dumps(tenets)
            # Empty array or non-list: preserve existing value (do nothing)

        if 'talent_tenets_improvements' in data:
            tenets = data.get('talent_tenets_improvements')
            if isinstance(tenets, list) and tenets:  # Only update if non-empty list
                import json
                employee.talent_tenets_improvements = json.dumps(tenets)
            # Empty array or non-list: preserve existing value (do nothing)

        # Compute derived fields
        employee.talent_overall_perf = derive_overall_performance(
            employee.talent_perf_what,
            employee.talent_perf_how
        )
        employee.talent_identified_future = derive_future_talent(
            employee.talent_growth_agility,
            employee.talent_change_agility
        )

        # Update timestamp
        employee.talent_last_updated = datetime.now()

        db.commit()

        response = {
            'success': True,
            'data': {
                'talent_overall_perf': employee.talent_overall_perf,
                'talent_identified_future': employee.talent_identified_future,
                'talent_last_updated': employee.talent_last_updated.strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        if normalized_fields:
            response['normalized_fields'] = normalized_fields
        return jsonify(response)

    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/calibrate/status', methods=['GET'])
def calibrate_status():
    """API endpoint to get talent calibration progress."""
    db = get_db()
    try:
        employees = db.query(Employee).all()
        total = len(employees)

        # Calibrated = has talent_perf_what OR talent_perf_how
        calibrated = sum(
            1 for e in employees
            if e.talent_perf_what or e.talent_perf_how
        )

        percent = round(calibrated / total * 100) if total > 0 else 0

        return jsonify({
            'success': True,
            'data': {
                'total': total,
                'calibrated': calibrated,
                'percent': percent
            }
        })
    finally:
        db.close()


@app.route('/api/tenets', methods=['GET'])
def get_tenets():
    """API endpoint to serve tenets configuration."""
    tenets_config, _ = db_helpers.load_tenets_config()
    if tenets_config is None:
        return jsonify({
            'error': 'No tenets.json found. Copy samples/tenets-sample.json '
                     'to tenets.json and customize it for your organization.'
        }), 404
    return jsonify(tenets_config)


@app.route('/api/bonus-settings', methods=['GET', 'POST'])
def bonus_settings_api():
    """API endpoint to get or update bonus calculation settings."""
    if request.method == 'GET':
        settings = get_bonus_settings()
        return jsonify(settings.to_dict())

    elif request.method == 'POST':
        data = request.get_json()
        budget_override = data.get('budget_override')

        if budget_override is None:
            return jsonify({'error': 'Missing budget_override'}), 400

        try:
            budget_override = float(budget_override)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid budget_override value'}), 400

        try:
            update_bonus_settings(budget_override)
            return jsonify({'success': True, 'message': 'Budget override saved successfully'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@app.route('/api/bonus-settings/verify-pool', methods=['POST'])
def verify_pool_api():
    """Mark the calculated bonus pool as verified by the user."""
    try:
        db = get_db()
        settings = db.query(BonusSettings).first()
        if not settings:
            return jsonify({'success': False, 'error': 'No bonus settings found'}), 404

        settings.pool_verified = True
        db.commit()
        return jsonify({'success': True, 'message': 'Pool verified'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/employee/<associate_id>', methods=['GET'])
def get_employee_details(associate_id):
    """API endpoint to get details for a specific employee by ID."""
    try:
        employee = get_employee_by_id(associate_id)

        if not employee:
            return jsonify({
                'success': False,
                'error': f'Employee not found: {associate_id}'
            }), 404

        return jsonify({
            'success': True,
            'employee': employee.to_dict()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/employee/<associate_id>/history', methods=['GET'])
def get_employee_history(associate_id):
    """API endpoint to get historical rating snapshots for an employee."""
    db = get_db()
    try:
        # Get all snapshots for this employee, joined with period data
        snapshots = db.query(RatingSnapshot, Period).join(
            Period, RatingSnapshot.period_id == Period.id
        ).filter(
            RatingSnapshot.associate_id == associate_id
        ).order_by(
            Period.archived_at.desc()
        ).all()

        history = []
        for snapshot, period in snapshots:
            history.append({
                'period': period.to_dict(),
                'snapshot': snapshot.to_dict()
            })

        return jsonify({
            'success': True,
            'associate_id': associate_id,
            'history': history
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        db.close()




# ═══════════════════════════════════════════════════════════════════════════
# BLUEPRINT REGISTRATION
# Blueprints register on the existing module-level `app` (no app factory yet).
# Imported at the bottom so app-level globals (DEMO_MODE, filters, helpers) are
# defined before a blueprint module does `import app`. See REFACTOR_APP_SPLIT.md.
# ═══════════════════════════════════════════════════════════════════════════
from blueprints.export import export_bp  # noqa: E402
from blueprints.history import history_bp  # noqa: E402
from blueprints.import_ import import_bp  # noqa: E402
from blueprints.analytics import analytics_bp  # noqa: E402
from blueprints.bonus import bonus_bp  # noqa: E402
app.register_blueprint(export_bp)
app.register_blueprint(history_bp)
app.register_blueprint(import_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(bonus_bp)


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
