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

# Field display names for import change log
# Maps database field names to user-friendly labels
BONUS_FIELD_DISPLAY_NAMES = {
    'performance_rating_percent': 'Performance Rating',
    'justification': 'Justification',
    'mentor': 'Mentor',
    'mentees': 'Mentees',
    'tenets_strengths': 'Tenet Strengths',
    'tenets_improvements': 'Tenet Improvements',
    'current_base_pay_manager_currency': 'Base Salary',
    'bonus_target_manager_currency': 'Bonus Target',
    'supervisory_organization': 'Team',
    'current_job_profile': 'Job Profile',
    'grade': 'Grade',
    'management_level': 'Management Level',
}

TALENT_FIELD_DISPLAY_NAMES = {
    'talent_perf_what': 'Performance: What',
    'talent_perf_how': 'Performance: How',
    'talent_growth_agility': 'Growth Agility',
    'talent_change_agility': 'Change Agility',
    'talent_movement_readiness': 'Movement Readiness',
    'talent_proposed_actions': 'Proposed Actions',
    'talent_mentor': 'Mentor',
    'talent_mentees': 'Mentees',
    'talent_tenets_strengths': 'Tenet Strengths',
    'talent_tenets_improvements': 'Tenet Improvements',
    'management_level': 'Management Level',
    'supervisory_organization': 'Team',
    'current_job_profile': 'Job Profile',
}


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




@app.route('/analytics')
def analytics():
    """Analytics and reports page."""
    from services.analytics import (
        calculate_rating_distribution,
        calculate_tenets_analytics,
        calculate_talent_calibration_analytics,
        detect_inconsistencies,
        calculate_mentorship_analysis,
        calculate_tenure_analytics,
    )

    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees (bonus cycle only)
    all_employees = get_all_employees(bonus_cycle_only=True)

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # --- Rating distribution ---
    (rating_buckets, dept_averages, job_averages, sorted_team, special_case_count,
     rated_employees, total_rated, has_bonus_data,
     job_profile_distribution,
     seniority_composition) = calculate_rating_distribution(team_data)

    # Calibration count (talent cycle)
    calibrated_count = sum(1 for emp in team_data if is_employee_calibrated(emp))

    # Org-level calibration using existing helper
    org_calibration = calculate_calibration_for_employees(rated_employees, "Organization")
    calibration_data = org_calibration['data']

    chart_data = {
        'rating_distribution': {
            'labels': list(rating_buckets.keys()),
            'data': list(rating_buckets.values())
        },
        'department_averages': {
            'labels': list(dept_averages.keys()),
            'data': list(dept_averages.values())
        },
        'job_averages': {
            'labels': list(job_averages.keys()),
            'data': list(job_averages.values())
        }
    }

    # --- Tenets analytics ---
    tenets_config, _ = db_helpers.load_tenets_config()
    tenets_config = tenets_config or {}
    tenets_map = {t['id']: t for t in tenets_config.get('tenets', [])}

    (tenets_summary, employees_with_tenets,
     org_tenets_summary, job_level_tenets_summary) = calculate_tenets_analytics(team_data, tenets_map)

    # --- Multi-team detection ---
    unique_orgs = set()
    for emp in rated_employees:
        org = emp.get('Supervisory Organization')
        if org:
            unique_orgs.add(org)
    is_multi_team = len(unique_orgs) > 1

    team_calibrations = []
    team_comparisons = []
    if is_multi_team:
        teams_by_org = {}
        for emp in rated_employees:
            org = emp.get('Supervisory Organization', 'Unknown')
            if org not in teams_by_org:
                teams_by_org[org] = []
            teams_by_org[org].append(emp)

        for org_name, team_employees in teams_by_org.items():
            team_cal = calculate_calibration_for_employees(team_employees, org_name)
            team_calibrations.append(team_cal)
            ratings = [float(e.get('performance_rating_percent', 0)) for e in team_employees]
            avg_rating = sum(ratings) / len(ratings) if ratings else 0
            std_dev = (sum((r - avg_rating) ** 2 for r in ratings) / len(ratings)) ** 0.5 if len(ratings) > 1 else 0
            issues = sum(1 for item in team_cal['data'] if item['status'] != 'good')
            if issues == 0:
                calibration_health = 'good'
            elif issues <= 2:
                calibration_health = 'warning'
            else:
                calibration_health = 'alert'
            team_comparisons.append({
                'team_name': org_name,
                'size': len(team_employees),
                'avg_rating': round(avg_rating, 1),
                'std_dev': round(std_dev, 1),
                'issues_count': issues,
                'calibration_health': calibration_health,
                'buckets': {item['bucket']: item for item in team_cal['data']}
            })

    # --- Mentorship ---
    mentorship_stats = calculate_mentorship_stats(team_data)

    team_mentorship_stats = []
    if is_multi_team:
        teams_by_org_all = {}
        for emp in team_data:
            org = emp.get('Supervisory Organization', 'Unknown')
            if org not in teams_by_org_all:
                teams_by_org_all[org] = []
            teams_by_org_all[org].append(emp)
        for org_name, team_employees in sorted(teams_by_org_all.items()):
            team_stats = calculate_mentorship_stats(team_employees)
            team_mentorship_stats.append({
                'team_name': org_name,
                'stats': team_stats['overall']
            })

    mentorship_analysis, total_mentorship_flags = calculate_mentorship_analysis(team_data)

    # --- Talent calibration ---
    talent_calibration = calculate_talent_calibration_analytics(team_data)

    # --- Inconsistencies ---
    inconsistencies, total_inconsistencies = detect_inconsistencies(
        team_data, tenets_map, rated_employees, has_bonus_data,
        all_employees, get_bonus_settings, calculate_bonus_for_employees
    )

    # --- Tenure analytics ---
    tenure_analytics = calculate_tenure_analytics(team_data)

    return render_template('analytics.html',
                         team=sorted_team,
                         chart_data=chart_data,
                         dept_averages=dept_averages,
                         job_averages=job_averages,
                         job_profile_distribution=job_profile_distribution,
                         seniority_composition=seniority_composition,
                         calibration_data=calibration_data,
                         total_rated=total_rated,
                         calibrated_count=calibrated_count,
                         has_bonus_data=has_bonus_data,
                         total_employees=len(team_data),
                         tenets_summary=tenets_summary,
                         employees_with_tenets=employees_with_tenets,
                         org_tenets_summary=org_tenets_summary,
                         job_level_tenets_summary=job_level_tenets_summary,
                         is_multi_team=is_multi_team,
                         team_calibrations=team_calibrations,
                         team_comparisons=team_comparisons,
                         mentorship_stats=mentorship_stats,
                         team_mentorship_stats=team_mentorship_stats,
                         mentorship_analysis=mentorship_analysis,
                         total_mentorship_flags=total_mentorship_flags,
                         talent_calibration=talent_calibration,
                         inconsistencies=inconsistencies,
                         total_inconsistencies=total_inconsistencies,
                         tenure_analytics=tenure_analytics,
                         filter_info=filter_info)



@app.route('/bonus-calculation')
def bonus_calculation():
    """Bonus calculation page with configurable parameters."""
    # Default configuration parameters
    default_params = {
        'upside_exponent': 1.35,
        'downside_exponent': 1.9
    }

    # Get parameters from query string or use defaults
    params = {
        'upside_exponent': float(request.args.get('upside_exponent', default_params['upside_exponent'])),
        'downside_exponent': float(request.args.get('downside_exponent', default_params['downside_exponent']))
    }

    # Get bonus settings from database (pool and override)
    settings = get_bonus_settings()
    budget_override = settings.budget_override
    workday_pool = settings.workday_pool

    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees (bonus cycle only)
    all_employees = get_all_employees(bonus_cycle_only=True)

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Filter to only rated employees (or employees with bonus override)
    # Use 'is not None' — a 0% rating is valid (not missing)
    rated_employees = [
        emp for emp in team_data
        if emp.get('performance_rating_percent') is not None or emp.get('bonus_override_percent') is not None
    ]

    # Calculate sum of ALL employee bonus targets (for proportional pool calculation)
    # Must use all_employees (not team_data) so filtered-out employees are included
    all_targets_sum = 0
    for emp in all_employees:
        bonus_target = emp.get('Bonus Target Manager Currency') or emp.get('Bonus Target - Local Currency')
        if bonus_target:
            try:
                all_targets_sum += float(bonus_target)
            except (ValueError, TypeError):
                pass

    if not rated_employees:
        return render_template('bonus_calculation.html',
                             team=[],
                             params=params,
                             base_pool=0,
                             budget_override=budget_override,
                             total_pool=0,
                             total_allocated=0,
                             value_per_share=1.0,
                             has_data=False,
                             missing_bonus_data=False,
                             is_multi_team=False,
                             filter_info=filter_info,
                             pool_source=settings.pool_source,
                             pool_verified=settings.pool_verified)

    # Detect multi-team scenario by checking unique supervisory organizations
    unique_orgs = set()
    for emp in rated_employees:
        org = emp.get('Supervisory Organization')
        if org:
            unique_orgs.add(org)

    is_multi_team = len(unique_orgs) > 1

    # Calculate organization-level bonuses (always) with budget override and Workday pool
    # Pass all_targets_sum so partial ratings use proportional share of Workday pool
    org_level_calc = calculate_bonus_for_employees(rated_employees, params, budget_override, workday_pool, all_targets_sum)

    # If multi-team, also calculate per-team bonuses for comparison
    team_comparisons = []
    teams_data = []

    if is_multi_team:
        # Group employees by supervisory organization
        teams_by_org = {}
        for emp in rated_employees:
            org = emp.get('Supervisory Organization', 'Unknown')
            if org not in teams_by_org:
                teams_by_org[org] = []
            teams_by_org[org].append(emp)

        # Calculate bonuses for each team independently
        for org_name, team_employees in teams_by_org.items():
            team_calc = calculate_bonus_for_employees(team_employees, params)

            # Calculate average rating for this team (exclude override employees)
            team_ratings = [
                float(e.get('performance_rating_percent'))
                for e in team_employees
                if e.get('performance_rating_percent') is not None and e.get('bonus_override_percent') is None
            ]
            avg_rating = sum(team_ratings) / len(team_ratings) if team_ratings else 0

            # Calculate budget impact (org-level allocation - team-level allocation)
            team_allocated_org_level = sum(
                org_level_calc['results_by_id'][e['Associate ID']]['final_bonus']
                for e in team_employees
                if e['Associate ID'] in org_level_calc['results_by_id']
            )
            team_allocated_team_level = team_calc['total_allocated']
            budget_impact = team_allocated_org_level - team_allocated_team_level
            impact_percent = (budget_impact / team_calc['total_pool'] * 100) if team_calc['total_pool'] > 0 else 0

            team_comparisons.append({
                'team_name': org_name,
                'team_pool': team_calc['total_pool'],
                'avg_rating': round(avg_rating, 1),
                'team_norm': team_calc['value_per_share'],
                'org_norm': org_level_calc['value_per_share'],
                'budget_impact': budget_impact,
                'impact_percent': impact_percent,
                'employee_count': len(team_employees)
            })

            teams_data.append({
                'name': org_name,
                'employees': team_employees,
                'team_level_calc': team_calc,
                'org_level_calc': org_level_calc
            })

    # Check if we have any valid bonus data
    if not org_level_calc['results'] or org_level_calc['base_pool'] == 0:
        return render_template('bonus_calculation.html',
                             team=[],
                             params=params,
                             base_pool=0,
                             budget_override=budget_override,
                             total_pool=0,
                             total_allocated=0,
                             value_per_share=1.0,
                             has_data=False,
                             missing_bonus_data=True,
                             is_multi_team=False,
                             filter_info=filter_info,
                             pool_source=settings.pool_source,
                             pool_verified=settings.pool_verified)

    # Sort by final bonus descending
    org_level_calc['results'].sort(key=lambda x: x['final_bonus'], reverse=True)

    return render_template('bonus_calculation.html',
                         team=org_level_calc['results'],
                         params=params,
                         base_pool=org_level_calc['base_pool'],
                         workday_pool=org_level_calc['workday_pool'],
                         sum_of_targets=org_level_calc['sum_of_targets'],
                         budget_override=org_level_calc['budget_override'],
                         total_pool=org_level_calc['total_pool'],
                         total_allocated=org_level_calc['total_allocated'],
                         value_per_share=org_level_calc['value_per_share'],
                         has_data=True,
                         missing_bonus_data=False,
                         total_rated=len(rated_employees),
                         total_employees=len(team_data),
                         employees_without_bonus_target=org_level_calc['employees_without_bonus_target'],
                         is_multi_team=is_multi_team,
                         team_comparisons=team_comparisons,
                         teams_data=teams_data,
                         filter_info=filter_info,
                         pool_source=settings.pool_source,
                         pool_verified=settings.pool_verified)


@app.route('/import')
def import_page():
    """Import data page."""
    # Get filter info so the filter panel can be populated (for pre-navigation filtering)
    filter_params = get_filter_params()
    all_employees = get_all_employees()
    _, filter_info = apply_employee_filters(all_employees, filter_params)

    return render_template('import.html', demo_mode=DEMO_MODE, filter_info=filter_info)


@app.route('/api/import/analyze', methods=['POST'])
def analyze_import():
    """
    Analyze an uploaded XLSX file and return metadata.

    Returns counts of employees, whether bonus column exists,
    and checks if the period already exists (for historical imports).
    """
    if DEMO_MODE:
        return jsonify({'success': False, 'error': 'Imports are disabled in demo mode'}), 403

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': 'File must be an Excel file (.xlsx or .xls)'}), 400

    import_type = request.form.get('import_type', 'current')
    period_id = request.form.get('period_id', '')

    # Save to temp file for analysis
    temp_dir = os.path.expanduser('~/tmp')
    os.makedirs(temp_dir, exist_ok=True)

    # Unique, unpredictable name avoids collisions between concurrent uploads
    # and symlink/TOCTOU races from a guessable path.
    fd, temp_path = tempfile.mkstemp(dir=temp_dir, prefix='import_analyze_', suffix='.xlsx')
    os.close(fd)  # only the path is needed; file.save reopens it
    try:
        file.save(temp_path)

        # Analyze the file
        analysis = analyze_xlsx(temp_path)

        if not analysis['success']:
            return jsonify({'success': False, 'error': analysis.get('error', 'Analysis failed')}), 400

        result = {
            'success': True,
            'employee_count': analysis['employee_count'],
            'spreadsheet_type': analysis.get('spreadsheet_type', 'bonus'),
            'has_bonus_column': analysis['has_bonus_column'],
            'notes_count': analysis['notes_count'],
            'allocation_count': analysis.get('allocation_count', 0),
            'employees_with_allocations': analysis.get('employees_with_allocations', []),
            'metadata': analysis.get('metadata', {}),
            'import_detection': analysis.get('import_detection', {}),
            'period_exists': False,
            'existing_count': 0,
            'period_id': None
        }

        # For historical imports, check if period exists
        if import_type == 'historical' and period_id:
            db = get_db()
            try:
                existing_period = db.query(Period).filter(Period.id == period_id).first()
                if existing_period:
                    result['period_exists'] = True
                    result['period_id'] = period_id
                    # Count existing snapshots for this period
                    result['existing_count'] = db.query(RatingSnapshot).filter(
                        RatingSnapshot.period_id == period_id
                    ).count()
            finally:
                db.close()

        return jsonify(result)

    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.route('/api/import/current', methods=['POST'])
def import_current():
    """
    Import XLSX as current period data.

    Updates the Employee table with fresh Workday data.
    Preserves existing ratings and justifications unless clear_existing is set.
    """
    if DEMO_MODE:
        return jsonify({'success': False, 'error': 'Imports are disabled in demo mode'}), 403

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    clear_existing = request.form.get('clear_existing', '').lower() == 'true'

    # Save to temp file
    temp_dir = os.path.expanduser('~/tmp')
    os.makedirs(temp_dir, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(dir=temp_dir, prefix='import_current_', suffix='.xlsx')
    os.close(fd)  # only the path is needed; file.save reopens it
    try:
        file.save(temp_path)

        # Analyze the file to get metadata and spreadsheet type
        analysis = analyze_xlsx(temp_path)
        if not analysis.get('success'):
            return jsonify({'success': False, 'error': analysis.get('error', 'Analysis failed')}), 400

        spreadsheet_type = analysis.get('spreadsheet_type', 'bonus')
        workday_pool = None
        manager_currency = None
        if analysis.get('metadata'):
            workday_pool = analysis['metadata'].get('total_pool')

        # Parse the file using appropriate parser based on type
        parsed_metadata = {}  # Initialize for talent files (which don't return metadata)
        if spreadsheet_type == 'talent':
            from xlsx_utils import parse_talent_xlsx_employees
            success, employees, error = parse_talent_xlsx_employees(temp_path)
        else:
            success, employees, error, parsed_metadata = parse_xlsx_employees(temp_path)
            # Use calculated total_pool from parsing if not in analysis metadata
            if not workday_pool and parsed_metadata.get('total_pool'):
                workday_pool = parsed_metadata['total_pool']

        if not success:
            return jsonify({'success': False, 'error': error}), 400

        # Validate Overall Performance derivation for talent imports
        derivation_mismatches = []
        if spreadsheet_type == 'talent':
            from models import derive_overall_performance, derive_future_talent
            for emp_data in employees:
                imported_what = emp_data.get('talent_perf_what')
                imported_how = emp_data.get('talent_perf_how')
                imported_overall = emp_data.get('talent_overall_perf')

                # Only validate if all three fields are present
                if imported_what and imported_how and imported_overall:
                    derived_overall = derive_overall_performance(imported_what, imported_how)
                    if derived_overall and derived_overall != imported_overall:
                        derivation_mismatches.append({
                            'associate': emp_data.get('associate'),
                            'associate_id': emp_data.get('associate_id'),
                            'what': imported_what,
                            'how': imported_how,
                            'imported': imported_overall,
                            'expected': derived_overall
                        })

        db = get_db()
        try:
            # Clear existing employees if requested
            cleared = 0
            if clear_existing:
                cleared = db.query(Employee).count()
                db.query(Employee).delete()

            # Store Workday pool and manager currency in BonusSettings
            if workday_pool is not None or manager_currency is not None:
                settings = db.query(BonusSettings).first()
                if not settings:
                    settings = BonusSettings()
                    db.add(settings)
                if workday_pool is not None:
                    settings.workday_pool = workday_pool
                # Track pool source for verification warning
                pool_source = parsed_metadata.get('pool_source', 'calculated_sum')
                settings.pool_source = pool_source
                # Auto-verify if pool came from Workday metadata; require verification if calculated
                settings.pool_verified = (pool_source == 'workday_metadata')
                if manager_currency is not None:
                    settings.manager_currency = manager_currency
                settings.last_updated = datetime.now()

            imported = 0
            tenet_warnings = []  # Collect unrecognized tenet names for warnings

            # For bonus imports, clear cycle membership so only employees
            # in this spreadsheet will appear on /rate
            if spreadsheet_type == 'bonus':
                db.query(Employee).update({Employee.in_current_bonus_cycle: False})

            # Track changes for import change log
            import_changes = {
                'new': [],       # {associate_id, associate, org, job_profile}
                'updated': [],   # {associate_id, associate, changes: [{field, old, new}]}
                'preserved': []  # {associate_id, associate, conflicts: [{field, local, workday}]}
            }

            def format_change_value(value, field_name):
                """Format a value for display in change log."""
                if value is None:
                    return None
                if isinstance(value, (int, float)):
                    if 'percent' in field_name or 'rating' in field_name:
                        return f'{value}%'
                    if 'currency' in field_name or 'pay' in field_name or 'target' in field_name:
                        return f'{value:,.0f}'
                if isinstance(value, str):
                    if value.startswith('[') and value.endswith(']'):
                        try:
                            items = json.loads(value)
                            return f'{len(items)} items' if items else None
                        except (json.JSONDecodeError, TypeError):
                            pass
                    if len(value) > 60:
                        return value[:57] + '...'
                return str(value) if value else None

            for emp_data in employees:
                associate_id = emp_data['associate_id']

                # Check if employee exists
                existing = db.query(Employee).filter(Employee.associate_id == associate_id).first()

                if existing:
                    employee = existing
                    # Track changes for this existing employee (updated count computed at end)
                    emp_updates = []
                    emp_preserved = []
                    # Track if Workday-sourced fields changed (for accurate update count)
                    workday_fields_changed = (
                        employee.associate != emp_data['associate'] or
                        employee.supervisory_organization != emp_data['supervisory_organization'] or
                        employee.current_job_profile != emp_data['current_job_profile']
                    )
                else:
                    employee = Employee(associate_id=associate_id)
                    imported += 1
                    workday_fields_changed = False  # Not applicable for new employees
                    # Track new employee
                    import_changes['new'].append({
                        'associate_id': associate_id,
                        'associate': emp_data['associate'],
                        'org': emp_data.get('supervisory_organization', ''),
                        'job_profile': emp_data.get('current_job_profile', '')
                    })

                # Update common fields
                employee.associate = emp_data['associate']
                employee.supervisory_organization = emp_data['supervisory_organization']
                employee.current_job_profile = emp_data['current_job_profile']

                if spreadsheet_type == 'talent':
                    # Update Workday-sourced fields (always overwrite from Workday)
                    # Extended identity
                    employee.management_level = emp_data.get('management_level')
                    employee.job_category = emp_data.get('job_category')
                    employee.hire_date = emp_data.get('hire_date')
                    employee.length_of_service = emp_data.get('length_of_service')
                    employee.time_in_job_profile = emp_data.get('time_in_job_profile')
                    employee.region = emp_data.get('region')
                    employee.country = emp_data.get('country')

                    # Historical/last-cycle fields (from Workday, always overwrite)
                    employee.talent_last_overall_perf = emp_data.get('talent_last_overall_perf')
                    employee.talent_last_identified_future = emp_data.get('talent_last_identified_future')
                    employee.talent_last_movement_readiness = emp_data.get('talent_last_movement_readiness')

                    # Calibration status (from Workday)
                    employee.talent_calibration_status = emp_data.get('talent_calibration_status')

                    # Manager-input fields: ONLY set for new employees (per Spec §5.3)
                    # These are preserved on re-import to prevent data loss
                    if not existing:
                        # Set _original fields from Workday data for modification tracking
                        # These reflect what Workday has, so we can detect local changes
                        # NOTE: For existing employees, _original fields are set individually
                        # AFTER comparison in the else branch below. Setting them here would
                        # break text_unmodified() checks (current vs new instead of current vs old).
                        employee.talent_perf_what_original = emp_data.get('talent_perf_what')
                        employee.talent_perf_how_original = emp_data.get('talent_perf_how')
                        employee.talent_growth_agility_original = emp_data.get('talent_growth_agility')
                        employee.talent_change_agility_original = emp_data.get('talent_change_agility')
                        employee.talent_movement_readiness_original = emp_data.get('talent_movement_readiness')
                        employee.talent_proposed_actions_original = emp_data.get('talent_proposed_actions')

                        # Performance Assessment (manager-entered)
                        employee.talent_perf_what = emp_data.get('talent_perf_what')
                        employee.talent_perf_how = emp_data.get('talent_perf_how')
                        # Use file value if present, otherwise derive from What + How
                        employee.talent_overall_perf = (
                            emp_data.get('talent_overall_perf')
                            or derive_overall_performance(employee.talent_perf_what, employee.talent_perf_how)
                        )

                        # Future Talent (manager-entered)
                        employee.talent_growth_agility = emp_data.get('talent_growth_agility')
                        employee.talent_change_agility = emp_data.get('talent_change_agility')
                        # Use file value if present, otherwise derive from agility fields
                        employee.talent_identified_future = (
                            emp_data.get('talent_identified_future')
                            if emp_data.get('talent_identified_future') is not None
                            else derive_future_talent(employee.talent_growth_agility, employee.talent_change_agility)
                        )

                        # Movement & Career (manager-entered)
                        employee.talent_movement_readiness = emp_data.get('talent_movement_readiness')

                        # Parse tenets and mentor/mentees from Proposed Actions if present
                        # Format: [Strengths: Tenet1; Tenet2] [Improvements: Tenet3] [Mentor: Name] [Mentees: A; B]
                        raw_proposed_actions = emp_data.get('talent_proposed_actions') or ''
                        tenets_config, _ = db_helpers.load_tenets_config()

                        if tenets_config and raw_proposed_actions:
                            from xlsx_utils import parse_proposed_actions_metadata
                            metadata = parse_proposed_actions_metadata(
                                raw_proposed_actions, tenets_config
                            )
                            employee.talent_proposed_actions = metadata['clean_actions'] if metadata['clean_actions'] else None
                            if metadata['strength_ids']:
                                employee.talent_tenets_strengths = json.dumps(metadata['strength_ids'])
                            if metadata['improvement_ids']:
                                employee.talent_tenets_improvements = json.dumps(metadata['improvement_ids'])
                            if metadata['mentor']:
                                employee.talent_mentor = metadata['mentor']
                            if metadata['mentees']:
                                employee.talent_mentees = metadata['mentees']
                        else:
                            employee.talent_proposed_actions = raw_proposed_actions if raw_proposed_actions else None

                        # Promotion (manager-entered) - handle [MODIFIED] marker for our exports
                        from xlsx_utils import parse_modified_text_field

                        raw_job_profile = emp_data.get('talent_promo_job_profile') or ''
                        employee.talent_promo_job_profile = raw_job_profile if raw_job_profile else None
                        # Job profile doesn't have [MODIFIED] in text, store as original
                        employee.talent_promo_job_profile_original = employee.talent_promo_job_profile

                        raw_business_need = emp_data.get('talent_promo_business_need') or ''
                        parsed_bn = parse_modified_text_field(raw_business_need)
                        employee.talent_promo_business_need = parsed_bn['content'] if parsed_bn['content'] else None
                        if not parsed_bn['is_modified']:
                            employee.talent_promo_business_need_original = employee.talent_promo_business_need

                        raw_role_scope = emp_data.get('talent_promo_role_scope') or ''
                        parsed_rs = parse_modified_text_field(raw_role_scope)
                        employee.talent_promo_role_scope = parsed_rs['content'] if parsed_rs['content'] else None
                        if not parsed_rs['is_modified']:
                            employee.talent_promo_role_scope_original = employee.talent_promo_role_scope

                        raw_readiness = emp_data.get('talent_promo_readiness') or ''
                        parsed_pr = parse_modified_text_field(raw_readiness)
                        employee.talent_promo_readiness = parsed_pr['content'] if parsed_pr['content'] else None
                        if not parsed_pr['is_modified']:
                            employee.talent_promo_readiness_original = employee.talent_promo_readiness
                    else:
                        # EXISTING employee in talent import: update fields based on local modification status
                        # - If unmodified locally (current == _original): update from Workday
                        # - If modified locally (current != _original): preserve local, update _original to show conflict

                        # Helper to check if text field is unmodified (handles None vs empty string)
                        def text_unmodified(current, original):
                            return (current or '') == (original or '')

                        # Helper to check if JSON string field is unmodified
                        def json_string_unmodified(current, original):
                            try:
                                curr_parsed = json.loads(current) if current else []
                                orig_parsed = json.loads(original) if original else []
                                return sorted(curr_parsed) == sorted(orig_parsed)
                            except (json.JSONDecodeError, TypeError):
                                # If not valid JSON, fall back to string comparison
                                return (current or '') == (original or '')

                        # Helper to compare mentor/mentee fields (normalizes placeholders like "None", "TBD" to empty)
                        def mentor_fields_equal(val1, val2):
                            norm1, _ = normalize_mentor_field(val1)
                            norm2, _ = normalize_mentor_field(val2)
                            return norm1 == norm2

                        # Performance What
                        new_perf_what = emp_data.get('talent_perf_what')
                        old_perf_what = employee.talent_perf_what
                        if text_unmodified(employee.talent_perf_what, employee.talent_perf_what_original):
                            employee.talent_perf_what = new_perf_what
                            if (old_perf_what or '') != (new_perf_what or ''):
                                emp_updates.append({'field': 'talent_perf_what', 'old': format_change_value(old_perf_what, 'talent_perf_what'), 'new': format_change_value(new_perf_what, 'talent_perf_what')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.talent_perf_what or '') != (new_perf_what or ''):
                                emp_preserved.append({'field': 'talent_perf_what', 'local': format_change_value(employee.talent_perf_what, 'talent_perf_what'), 'workday': format_change_value(new_perf_what, 'talent_perf_what')})
                        employee.talent_perf_what_original = new_perf_what

                        # Performance How
                        new_perf_how = emp_data.get('talent_perf_how')
                        old_perf_how = employee.talent_perf_how
                        if text_unmodified(employee.talent_perf_how, employee.talent_perf_how_original):
                            employee.talent_perf_how = new_perf_how
                            if (old_perf_how or '') != (new_perf_how or ''):
                                emp_updates.append({'field': 'talent_perf_how', 'old': format_change_value(old_perf_how, 'talent_perf_how'), 'new': format_change_value(new_perf_how, 'talent_perf_how')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.talent_perf_how or '') != (new_perf_how or ''):
                                emp_preserved.append({'field': 'talent_perf_how', 'local': format_change_value(employee.talent_perf_how, 'talent_perf_how'), 'workday': format_change_value(new_perf_how, 'talent_perf_how')})
                        employee.talent_perf_how_original = new_perf_how

                        # Growth Agility
                        new_growth = emp_data.get('talent_growth_agility')
                        old_growth = employee.talent_growth_agility
                        if text_unmodified(employee.talent_growth_agility, employee.talent_growth_agility_original):
                            employee.talent_growth_agility = new_growth
                            if (old_growth or '') != (new_growth or ''):
                                emp_updates.append({'field': 'talent_growth_agility', 'old': format_change_value(old_growth, 'talent_growth_agility'), 'new': format_change_value(new_growth, 'talent_growth_agility')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.talent_growth_agility or '') != (new_growth or ''):
                                emp_preserved.append({'field': 'talent_growth_agility', 'local': format_change_value(employee.talent_growth_agility, 'talent_growth_agility'), 'workday': format_change_value(new_growth, 'talent_growth_agility')})
                        employee.talent_growth_agility_original = new_growth

                        # Change Agility
                        new_change = emp_data.get('talent_change_agility')
                        old_change = employee.talent_change_agility
                        if text_unmodified(employee.talent_change_agility, employee.talent_change_agility_original):
                            employee.talent_change_agility = new_change
                            if (old_change or '') != (new_change or ''):
                                emp_updates.append({'field': 'talent_change_agility', 'old': format_change_value(old_change, 'talent_change_agility'), 'new': format_change_value(new_change, 'talent_change_agility')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.talent_change_agility or '') != (new_change or ''):
                                emp_preserved.append({'field': 'talent_change_agility', 'local': format_change_value(employee.talent_change_agility, 'talent_change_agility'), 'workday': format_change_value(new_change, 'talent_change_agility')})
                        employee.talent_change_agility_original = new_change

                        # Movement Readiness (uses normalize function)
                        new_movement = normalize_movement_readiness(emp_data.get('talent_movement_readiness'))
                        old_movement = employee.talent_movement_readiness
                        if text_unmodified(employee.talent_movement_readiness, employee.talent_movement_readiness_original):
                            employee.talent_movement_readiness = new_movement
                            if (old_movement or '') != (new_movement or ''):
                                emp_updates.append({'field': 'talent_movement_readiness', 'old': format_change_value(old_movement, 'talent_movement_readiness'), 'new': format_change_value(new_movement, 'talent_movement_readiness')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.talent_movement_readiness or '') != (new_movement or ''):
                                emp_preserved.append({'field': 'talent_movement_readiness', 'local': format_change_value(employee.talent_movement_readiness, 'talent_movement_readiness'), 'workday': format_change_value(new_movement, 'talent_movement_readiness')})
                        employee.talent_movement_readiness_original = new_movement

                        # Tool additions fields - parse from Workday's proposed_actions
                        raw_proposed_actions = emp_data.get('talent_proposed_actions') or ''
                        tenets_config, _ = db_helpers.load_tenets_config()
                        if tenets_config and raw_proposed_actions:
                            from xlsx_utils import parse_proposed_actions_metadata
                            metadata = parse_proposed_actions_metadata(raw_proposed_actions, tenets_config)
                            new_actions = metadata['clean_actions'] if metadata['clean_actions'] else None
                            new_strengths = json.dumps(metadata['strength_ids']) if metadata['strength_ids'] else None
                            new_improvements = json.dumps(metadata['improvement_ids']) if metadata['improvement_ids'] else None
                            new_mentor = metadata['mentor'] if metadata['mentor'] else None
                            new_mentees = metadata['mentees'] if metadata['mentees'] else None
                        else:
                            # No tenets config or empty proposed_actions
                            new_actions = raw_proposed_actions if raw_proposed_actions else None
                            new_strengths = None
                            new_improvements = None
                            new_mentor = None
                            new_mentees = None

                        # Proposed Actions
                        old_actions = employee.talent_proposed_actions
                        if text_unmodified(employee.talent_proposed_actions, employee.talent_proposed_actions_original):
                            employee.talent_proposed_actions = new_actions
                            if (old_actions or '') != (new_actions or ''):
                                emp_updates.append({'field': 'talent_proposed_actions', 'old': format_change_value(old_actions, 'talent_proposed_actions'), 'new': format_change_value(new_actions, 'talent_proposed_actions')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.talent_proposed_actions or '') != (new_actions or ''):
                                emp_preserved.append({'field': 'talent_proposed_actions', 'local': format_change_value(employee.talent_proposed_actions, 'talent_proposed_actions'), 'workday': format_change_value(new_actions, 'talent_proposed_actions')})
                        employee.talent_proposed_actions_original = new_actions

                        # Talent Tenets Strengths (JSON string)
                        old_strengths = employee.talent_tenets_strengths
                        if json_string_unmodified(employee.talent_tenets_strengths, employee.talent_tenets_strengths_original):
                            employee.talent_tenets_strengths = new_strengths
                            if (old_strengths or '') != (new_strengths or ''):
                                emp_updates.append({'field': 'talent_tenets_strengths', 'old': format_change_value(old_strengths, 'talent_tenets_strengths'), 'new': format_change_value(new_strengths, 'talent_tenets_strengths')})
                        else:
                            # Only show conflict if local differs from workday
                            if not json_string_unmodified(employee.talent_tenets_strengths, new_strengths):
                                emp_preserved.append({'field': 'talent_tenets_strengths', 'local': format_change_value(employee.talent_tenets_strengths, 'talent_tenets_strengths'), 'workday': format_change_value(new_strengths, 'talent_tenets_strengths')})
                        employee.talent_tenets_strengths_original = new_strengths

                        # Talent Tenets Improvements (JSON string)
                        old_improvements = employee.talent_tenets_improvements
                        if json_string_unmodified(employee.talent_tenets_improvements, employee.talent_tenets_improvements_original):
                            employee.talent_tenets_improvements = new_improvements
                            if (old_improvements or '') != (new_improvements or ''):
                                emp_updates.append({'field': 'talent_tenets_improvements', 'old': format_change_value(old_improvements, 'talent_tenets_improvements'), 'new': format_change_value(new_improvements, 'talent_tenets_improvements')})
                        else:
                            # Only show conflict if local differs from workday
                            if not json_string_unmodified(employee.talent_tenets_improvements, new_improvements):
                                emp_preserved.append({'field': 'talent_tenets_improvements', 'local': format_change_value(employee.talent_tenets_improvements, 'talent_tenets_improvements'), 'workday': format_change_value(new_improvements, 'talent_tenets_improvements')})
                        employee.talent_tenets_improvements_original = new_improvements

                        # Talent Mentor (use mentor_fields_equal to handle placeholders like "None", "TBD")
                        old_mentor_t = employee.talent_mentor
                        if text_unmodified(employee.talent_mentor, employee.talent_mentor_original):
                            employee.talent_mentor = new_mentor
                            if not mentor_fields_equal(old_mentor_t, new_mentor):
                                emp_updates.append({'field': 'talent_mentor', 'old': format_change_value(old_mentor_t, 'talent_mentor'), 'new': format_change_value(new_mentor, 'talent_mentor')})
                        else:
                            # Only show conflict if local differs from workday (considering placeholders)
                            if not mentor_fields_equal(employee.talent_mentor, new_mentor):
                                emp_preserved.append({'field': 'talent_mentor', 'local': format_change_value(employee.talent_mentor, 'talent_mentor'), 'workday': format_change_value(new_mentor, 'talent_mentor')})
                        employee.talent_mentor_original = new_mentor

                        # Talent Mentees (use mentor_fields_equal to handle placeholders like "None", "TBD")
                        old_mentees_t = employee.talent_mentees
                        if text_unmodified(employee.talent_mentees, employee.talent_mentees_original):
                            employee.talent_mentees = new_mentees
                            if not mentor_fields_equal(old_mentees_t, new_mentees):
                                emp_updates.append({'field': 'talent_mentees', 'old': format_change_value(old_mentees_t, 'talent_mentees'), 'new': format_change_value(new_mentees, 'talent_mentees')})
                        else:
                            # Only show conflict if local differs from workday (considering placeholders)
                            if not mentor_fields_equal(employee.talent_mentees, new_mentees):
                                emp_preserved.append({'field': 'talent_mentees', 'local': format_change_value(employee.talent_mentees, 'talent_mentees'), 'workday': format_change_value(new_mentees, 'talent_mentees')})
                        employee.talent_mentees_original = new_mentees

                        # Derive computed fields from updated What/How and agility values
                        employee.talent_overall_perf = derive_overall_performance(
                            employee.talent_perf_what, employee.talent_perf_how
                        )
                        employee.talent_identified_future = derive_future_talent(
                            employee.talent_growth_agility, employee.talent_change_agility
                        )

                        # Aggregate per-employee changes for existing talent employees
                        if emp_updates or workday_fields_changed:
                            import_changes['updated'].append({
                                'associate_id': associate_id,
                                'associate': emp_data['associate'],
                                'changes': emp_updates
                            })
                        if emp_preserved:
                            import_changes['preserved'].append({
                                'associate_id': associate_id,
                                'associate': emp_data['associate'],
                                'conflicts': emp_preserved
                            })
                elif spreadsheet_type != 'talent':
                    # Update bonus-specific fields
                    employee.photo = emp_data.get('photo', '')
                    employee.errors = emp_data.get('errors', '')
                    employee.current_base_pay_all_countries = emp_data.get('current_base_pay_all_countries')
                    employee.current_base_pay_manager_currency = emp_data.get('current_base_pay_manager_currency')
                    employee.currency = emp_data.get('currency', '')
                    employee.grade = emp_data.get('grade', '')
                    employee.annual_bonus_target_percent = emp_data.get('annual_bonus_target_percent')
                    employee.last_bonus_allocation_percent = emp_data.get('last_bonus_allocation_percent')
                    employee.bonus_target_local_currency = emp_data.get('bonus_target_local_currency')
                    employee.bonus_target_manager_currency = emp_data.get('bonus_target_manager_currency')
                    employee.proposed_bonus_amount = emp_data.get('proposed_bonus_amount')
                    employee.proposed_bonus_amount_manager_currency = emp_data.get('proposed_bonus_amount_manager_currency')
                    employee.proposed_percent_of_target_bonus = emp_data.get('proposed_percent_of_target_bonus')
                    employee.notes = emp_data.get('notes', '')
                    employee.zero_bonus_allocated = emp_data.get('zero_bonus_allocated', '')
                    # New fields from 2025 Workday format
                    if emp_data.get('management_level'):
                        employee.management_level = emp_data['management_level']
                    if emp_data.get('country'):
                        employee.country = emp_data['country']
                    if emp_data.get('hire_date'):
                        employee.hire_date = emp_data['hire_date']
                    if emp_data.get('time_in_job_profile'):
                        employee.time_in_job_profile = emp_data['time_in_job_profile']
                    if emp_data.get('last_perf_review_name'):
                        employee.last_perf_review_name = emp_data['last_perf_review_name']
                    if emp_data.get('last_perf_review_rating'):
                        employee.last_perf_review_rating = emp_data['last_perf_review_rating']

                if spreadsheet_type == 'bonus':
                    employee.in_current_bonus_cycle = True

                # Parse Notes field for bonus imports (both new and existing employees)
                # This sets _original fields for modification tracking
                if spreadsheet_type != 'talent':
                    notes_data = parse_notes_field(emp_data.get('notes', ''))
                    tenets_config, _ = db_helpers.load_tenets_config()

                    # Convert tenet names to JSON IDs for storage (needed for both new and existing)
                    imported_strengths = convert_tenet_names_to_ids(
                        notes_data.get('tenets_strengths'), tenets_config
                    )
                    imported_improvements = convert_tenet_names_to_ids(
                        notes_data.get('tenets_improvements'), tenets_config
                    )

                    # Track per-employee changes for change log
                    emp_updates = []    # Fields updated from Workday
                    emp_preserved = []  # Fields preserved locally (conflicts)

                    # For existing employees: update fields based on local modification status
                    # - If unmodified locally (current == _original): update from Workday
                    # - If modified locally (current != _original): preserve local, update _original to show conflict
                    if existing:
                        new_rating = notes_data.get('performance_rating')
                        old_rating = employee.performance_rating_percent
                        # Performance rating: unmodified means current == original
                        if employee.performance_rating_percent == employee.performance_rating_percent_original:
                            # Unmodified locally - update from Workday
                            if new_rating is not None:
                                employee.performance_rating_percent = new_rating
                            if old_rating != new_rating:
                                emp_updates.append({'field': 'performance_rating_percent', 'old': format_change_value(old_rating, 'performance_rating_percent'), 'new': format_change_value(new_rating, 'performance_rating_percent')})
                            employee.performance_rating_percent_original = new_rating
                        else:
                            # Modified locally - only show conflict if local differs from workday
                            if employee.performance_rating_percent != new_rating:
                                emp_preserved.append({'field': 'performance_rating_percent', 'local': format_change_value(employee.performance_rating_percent, 'performance_rating_percent'), 'workday': format_change_value(new_rating, 'performance_rating_percent')})
                            employee.performance_rating_percent_original = new_rating

                        # Helper to check if text field is unmodified (handles None vs empty string)
                        def text_unmodified(current, original):
                            return (current or '') == (original or '')

                        # Helper to compare mentor/mentee fields (normalizes placeholders like "None", "TBD" to empty)
                        def mentor_fields_equal(val1, val2):
                            norm1, _ = normalize_mentor_field(val1)
                            norm2, _ = normalize_mentor_field(val2)
                            return norm1 == norm2

                        # Justification
                        new_justification = notes_data.get('justification') or ''
                        old_justification = employee.justification
                        if text_unmodified(employee.justification, employee.justification_original):
                            employee.justification = new_justification
                            employee.justification_original = new_justification
                            if (old_justification or '') != (new_justification or ''):
                                emp_updates.append({'field': 'justification', 'old': format_change_value(old_justification, 'justification'), 'new': format_change_value(new_justification, 'justification')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.justification or '') != (new_justification or ''):
                                emp_preserved.append({'field': 'justification', 'local': format_change_value(employee.justification, 'justification'), 'workday': format_change_value(new_justification, 'justification')})
                            employee.justification_original = new_justification

                        # Mentor (use mentor_fields_equal to handle placeholders like "None", "TBD")
                        new_mentor = notes_data.get('mentors') or ''
                        old_mentor_b = employee.mentor
                        if text_unmodified(employee.mentor, employee.mentor_original):
                            employee.mentor = new_mentor
                            employee.mentor_original = new_mentor
                            if not mentor_fields_equal(old_mentor_b, new_mentor):
                                emp_updates.append({'field': 'mentor', 'old': format_change_value(old_mentor_b, 'mentor'), 'new': format_change_value(new_mentor, 'mentor')})
                        else:
                            # Only show conflict if local differs from workday (considering placeholders)
                            if not mentor_fields_equal(employee.mentor, new_mentor):
                                emp_preserved.append({'field': 'mentor', 'local': format_change_value(employee.mentor, 'mentor'), 'workday': format_change_value(new_mentor, 'mentor')})
                            employee.mentor_original = new_mentor

                        # Mentees (use mentor_fields_equal to handle placeholders like "None", "TBD")
                        new_mentees = notes_data.get('mentees') or ''
                        old_mentees_b = employee.mentees
                        if text_unmodified(employee.mentees, employee.mentees_original):
                            employee.mentees = new_mentees
                            employee.mentees_original = new_mentees
                            if not mentor_fields_equal(old_mentees_b, new_mentees):
                                emp_updates.append({'field': 'mentees', 'old': format_change_value(old_mentees_b, 'mentees'), 'new': format_change_value(new_mentees, 'mentees')})
                        else:
                            # Only show conflict if local differs from workday (considering placeholders)
                            if not mentor_fields_equal(employee.mentees, new_mentees):
                                emp_preserved.append({'field': 'mentees', 'local': format_change_value(employee.mentees, 'mentees'), 'workday': format_change_value(new_mentees, 'mentees')})
                            employee.mentees_original = new_mentees

                        # Tenets (JSON arrays) - compare as JSON strings for equality
                        def tenets_unmodified(current, original):
                            curr_str = json.dumps(current, sort_keys=True) if current else '[]'
                            orig_str = json.dumps(original, sort_keys=True) if original else '[]'
                            return curr_str == orig_str

                        old_strengths_b = employee.tenets_strengths
                        if tenets_unmodified(employee.tenets_strengths, employee.tenets_strengths_original):
                            employee.tenets_strengths = imported_strengths
                            employee.tenets_strengths_original = imported_strengths
                            if not tenets_unmodified(old_strengths_b, imported_strengths):
                                emp_updates.append({'field': 'tenets_strengths', 'old': format_change_value(json.dumps(old_strengths_b) if old_strengths_b else None, 'tenets_strengths'), 'new': format_change_value(json.dumps(imported_strengths) if imported_strengths else None, 'tenets_strengths')})
                        else:
                            # Only show conflict if local differs from workday
                            if not tenets_unmodified(employee.tenets_strengths, imported_strengths):
                                emp_preserved.append({'field': 'tenets_strengths', 'local': format_change_value(json.dumps(employee.tenets_strengths) if employee.tenets_strengths else None, 'tenets_strengths'), 'workday': format_change_value(json.dumps(imported_strengths) if imported_strengths else None, 'tenets_strengths')})
                            employee.tenets_strengths_original = imported_strengths

                        old_improvements_b = employee.tenets_improvements
                        if tenets_unmodified(employee.tenets_improvements, employee.tenets_improvements_original):
                            employee.tenets_improvements = imported_improvements
                            employee.tenets_improvements_original = imported_improvements
                            if not tenets_unmodified(old_improvements_b, imported_improvements):
                                emp_updates.append({'field': 'tenets_improvements', 'old': format_change_value(json.dumps(old_improvements_b) if old_improvements_b else None, 'tenets_improvements'), 'new': format_change_value(json.dumps(imported_improvements) if imported_improvements else None, 'tenets_improvements')})
                        else:
                            # Only show conflict if local differs from workday
                            if not tenets_unmodified(employee.tenets_improvements, imported_improvements):
                                emp_preserved.append({'field': 'tenets_improvements', 'local': format_change_value(json.dumps(employee.tenets_improvements) if employee.tenets_improvements else None, 'tenets_improvements'), 'workday': format_change_value(json.dumps(imported_improvements) if imported_improvements else None, 'tenets_improvements')})
                            employee.tenets_improvements_original = imported_improvements

                        # Bonus override (special case) - only update if currently not set locally
                        # This preserves local changes but imports if we don't have a local value
                        new_override = notes_data.get('bonus_override_percent')
                        new_notes = notes_data.get('special_case_notes')
                        if employee.bonus_override_percent is None and new_override is not None:
                            employee.bonus_override_percent = new_override
                        if employee.special_case_notes is None and new_notes:
                            employee.special_case_notes = new_notes
                        employee.bonus_override_percent_original = new_override

                        # Aggregate per-employee changes for existing employees
                        # Count as updated if any field actually changed (manager-input OR Workday-sourced)
                        if emp_updates or workday_fields_changed:
                            import_changes['updated'].append({
                                'associate_id': associate_id,
                                'associate': emp_data['associate'],
                                'changes': emp_updates  # Only detailed changes for manager-input fields
                            })
                        if emp_preserved:
                            import_changes['preserved'].append({
                                'associate_id': associate_id,
                                'associate': emp_data['associate'],
                                'conflicts': emp_preserved
                            })

                    # Initialize manager input fields for new employees only
                    if not existing:
                        # Set _original fields from Workday data for modification tracking
                        employee.performance_rating_percent_original = notes_data.get('performance_rating')
                        employee.justification_original = notes_data.get('justification') or None
                        employee.mentor_original = notes_data.get('mentors') or None
                        employee.mentees_original = notes_data.get('mentees') or None
                        employee.tenets_strengths_original = imported_strengths
                        employee.tenets_improvements_original = imported_improvements

                        if notes_data.get('performance_rating') is not None:
                            employee.performance_rating_percent = notes_data.get('performance_rating')
                            employee.justification = notes_data.get('justification') or ''
                            employee.mentor = notes_data.get('mentors') or ''
                            employee.mentees = notes_data.get('mentees') or ''
                            employee.tenets_strengths = imported_strengths
                            employee.tenets_improvements = imported_improvements
                        else:
                            employee.performance_rating_percent = None
                            employee.tenets_strengths = None
                            employee.tenets_improvements = None
                            employee.justification = ''
                            employee.mentor = ''
                            employee.mentees = ''
                        # Bonus override (special case) for new employees
                        employee.bonus_override_percent = notes_data.get('bonus_override_percent')
                        employee.bonus_override_percent_original = notes_data.get('bonus_override_percent')
                        employee.special_case_notes = notes_data.get('special_case_notes')
                        employee.last_updated = None
                        db.add(employee)
                elif not existing:
                    # Talent import for new employee
                    employee.last_updated = None
                    db.add(employee)

            db.commit()

            result = {
                'success': True,
                'imported': imported,
                'updated': len(import_changes['updated'])  # Only count records with actual changes
            }
            if clear_existing:
                result['cleared'] = cleared
            if derivation_mismatches:
                result['derivation_mismatches'] = derivation_mismatches
                result['derivation_mismatch_count'] = len(derivation_mismatches)
            # Include pool verification info for post-import modal (bonus imports only)
            pool_source = parsed_metadata.get('pool_source', 'calculated_sum')
            if spreadsheet_type != 'talent' and pool_source == 'calculated_sum' and workday_pool:
                result['pool_verification'] = {
                    'amount': workday_pool,
                    'source': pool_source,
                    'needs_verification': True,
                    'currency': manager_currency or 'USD'
                }

            # Add change log with field display names
            if import_changes['new'] or import_changes['updated'] or import_changes['preserved']:
                display_names = TALENT_FIELD_DISPLAY_NAMES if spreadsheet_type == 'talent' else BONUS_FIELD_DISPLAY_NAMES
                for item in import_changes['updated']:
                    for change in item['changes']:
                        change['field_display'] = display_names.get(change['field'], change['field'])
                for item in import_changes['preserved']:
                    for conflict in item['conflicts']:
                        conflict['field_display'] = display_names.get(conflict['field'], conflict['field'])
                result['changes'] = import_changes

            return jsonify(result)

        except Exception as e:
            db.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
        finally:
            db.close()

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.route('/api/import/historical', methods=['POST'])
def import_historical():
    """
    Import XLSX as a historical period snapshot.

    Creates Period and RatingSnapshot records.
    Parses Notes field for rating data.
    """
    if DEMO_MODE:
        return jsonify({'success': False, 'error': 'Imports are disabled in demo mode'}), 403

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    period_id = request.form.get('period_id', '').strip()
    period_name = request.form.get('period_name', '').strip()

    if not period_id or not period_name:
        return jsonify({'success': False, 'error': 'Period ID and name are required'}), 400

    if not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    # Save to temp file
    temp_dir = os.path.expanduser('~/tmp')
    os.makedirs(temp_dir, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(dir=temp_dir, prefix='import_historical_', suffix='.xlsx')
    os.close(fd)  # only the path is needed; file.save reopens it
    try:
        file.save(temp_path)

        # Parse the file
        success, employees, error, parsed_metadata = parse_xlsx_employees(temp_path)
        if not success:
            return jsonify({'success': False, 'error': error}), 400

        db = get_db()
        try:
            # Create or update period
            period = db.query(Period).filter(Period.id == period_id).first()
            if not period:
                period = Period(id=period_id, name=period_name, archived_at=datetime.now())
                db.add(period)
            else:
                period.name = period_name
                period.archived_at = datetime.now()

            imported = 0
            updated = 0
            full_details_count = 0

            for emp_data in employees:
                associate_id = emp_data['associate_id']

                # Parse notes for rating data
                notes_data = parse_notes_field(emp_data.get('notes', ''))

                # Get bonus allocation from Workday column
                bonus_allocation = emp_data.get('proposed_percent_of_target_bonus')

                # Prepare new field values
                new_values = {
                    'performance_rating': notes_data.get('performance_rating'),
                    'bonus_allocation': bonus_allocation,
                    'justification': notes_data.get('justification'),
                    'tenets_strengths': notes_data.get('tenets_strengths'),
                    'tenets_improvements': notes_data.get('tenets_improvements'),
                    'mentors': notes_data.get('mentors'),
                    'mentees': notes_data.get('mentees'),
                    'snapshot_name': emp_data['associate'],
                    'snapshot_org': emp_data['supervisory_organization'],
                    'snapshot_job_profile': emp_data['current_job_profile'],
                    'snapshot_bonus_target_manager_currency': emp_data.get('bonus_target_manager_currency') or emp_data.get('bonus_target_local_currency'),
                }

                # Check if snapshot exists
                existing = db.query(RatingSnapshot).filter(
                    RatingSnapshot.period_id == period_id,
                    RatingSnapshot.associate_id == associate_id
                ).first()

                if existing:
                    snapshot = existing
                    # Check if any field actually changed
                    has_changes = any(
                        getattr(snapshot, field) != value
                        for field, value in new_values.items()
                    )
                    if has_changes:
                        updated += 1
                else:
                    snapshot = RatingSnapshot(
                        period_id=period_id,
                        associate_id=associate_id
                    )
                    imported += 1

                # Update snapshot fields
                for field, value in new_values.items():
                    setattr(snapshot, field, value)

                snapshot.archived_at = datetime.now()

                # Mark if we have full details (performance rating parsed from notes)
                has_full = notes_data.get('performance_rating') is not None
                snapshot.has_full_details = has_full
                if has_full:
                    full_details_count += 1

                if not existing:
                    db.add(snapshot)

            db.commit()

            return jsonify({
                'success': True,
                'imported': imported,
                'updated': updated,
                'full_details': full_details_count
            })

        except Exception as e:
            db.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
        finally:
            db.close()

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ═══════════════════════════════════════════════════════════════════════════
# BLUEPRINT REGISTRATION
# Blueprints register on the existing module-level `app` (no app factory yet).
# Imported at the bottom so app-level globals (DEMO_MODE, filters, helpers) are
# defined before a blueprint module does `import app`. See REFACTOR_APP_SPLIT.md.
# ═══════════════════════════════════════════════════════════════════════════
from blueprints.export import export_bp  # noqa: E402
from blueprints.history import history_bp  # noqa: E402
app.register_blueprint(export_bp)
app.register_blueprint(history_bp)


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
