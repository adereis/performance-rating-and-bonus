#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify, send_file, make_response, Response
import os
import logging
import json
import csv
import io
from datetime import datetime
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from sqlalchemy import text
from models import Employee, BonusSettings, Period, RatingSnapshot, init_db, get_db
from xlsx_utils import analyze_xlsx, parse_xlsx_employees
from notes_parser import parse_notes_field

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

# Demo mode configuration
DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'

# Rating thresholds for color-coding and calibration buckets
# These define the boundaries between performance categories:
#   - High performers: rating >= RATING_THRESHOLD_HIGH (green)
#   - Solid performers: RATING_THRESHOLD_MID <= rating < HIGH (yellow)
#   - Needs improvement: RATING_THRESHOLD_LOW <= rating < MID (orange)
#   - Below expectations: rating < LOW (red)
RATING_THRESHOLD_HIGH = 120  # "Exceeds expectations" threshold
RATING_THRESHOLD_MID = 90    # "Meets expectations" threshold
RATING_THRESHOLD_LOW = 60    # "Needs improvement" threshold

# Currency formatting for display (manager's currency)
# Each currency specifies: symbol, position (before/after number), space between symbol and number
# Format: {'symbol': str, 'position': 'before'|'after', 'space': bool}
CURRENCY_FORMATS = {
    'USD': {'symbol': '$', 'position': 'before', 'space': False},
    'AUD': {'symbol': 'A$', 'position': 'before', 'space': False},
    'BRL': {'symbol': 'R$', 'position': 'before', 'space': True},
    'CAD': {'symbol': 'C$', 'position': 'before', 'space': False},
    'CHF': {'symbol': 'CHF', 'position': 'before', 'space': True},
    'CZK': {'symbol': 'Kč', 'position': 'after', 'space': True},
    'EUR': {'symbol': '€', 'position': 'before', 'space': False},
    'GBP': {'symbol': '£', 'position': 'before', 'space': False},
    'HKD': {'symbol': 'HK$', 'position': 'before', 'space': False},
    'ILS': {'symbol': '₪', 'position': 'before', 'space': False},
    'INR': {'symbol': '₹', 'position': 'before', 'space': False},
    'JPY': {'symbol': '¥', 'position': 'before', 'space': False},
    'NZD': {'symbol': 'NZ$', 'position': 'before', 'space': False},
    'SGD': {'symbol': 'S$', 'position': 'before', 'space': False},
    'ZAR': {'symbol': 'R', 'position': 'before', 'space': False},
}

# Legacy lookup for simple symbol access
CURRENCY_SYMBOLS = {code: fmt['symbol'] for code, fmt in CURRENCY_FORMATS.items()}


def _has_tenets(tenets_strengths, tenets_improvements):
    """Check if employee has at least one tenet selected (strengths or improvements).

    Tenets are stored as JSON arrays, so we check for non-empty, non-'[]' values.
    """
    def is_non_empty(val):
        if not val:
            return False
        if isinstance(val, str):
            return val not in ('', '[]', 'null')
        if isinstance(val, list):
            return len(val) > 0
        return False

    return is_non_empty(tenets_strengths) or is_non_empty(tenets_improvements)


def is_employee_rated(emp):
    """Check if an employee is fully rated for bonus cycle.

    Required fields:
    - performance_rating_percent: The rating value (0-200%)
    - justification: Text explanation for the rating
    - tenets: At least one strength OR improvement tenet selected
    """
    # Handle both dict (from to_dict()) and ORM object
    if isinstance(emp, dict):
        rating = emp.get('performance_rating_percent')
        justification = emp.get('justification')
        tenets_s = emp.get('tenets_strengths')
        tenets_i = emp.get('tenets_improvements')
    else:
        rating = emp.performance_rating_percent
        justification = emp.justification
        tenets_s = emp.tenets_strengths
        tenets_i = emp.tenets_improvements

    return bool(rating) and bool(justification) and _has_tenets(tenets_s, tenets_i)


def is_employee_calibrated(emp):
    """Check if an employee is fully calibrated for talent cycle.

    Required fields:
    - talent_perf_what: Performance "What" assessment
    - talent_perf_how: Performance "How" assessment
    - talent_proposed_actions: Action plan text
    - talent_tenets: At least one strength OR improvement tenet selected
    """
    # Handle both dict (from to_dict()) and ORM object
    if isinstance(emp, dict):
        what = emp.get('talent_perf_what')
        how = emp.get('talent_perf_how')
        actions = emp.get('talent_proposed_actions')
        tenets_s = emp.get('talent_tenets_strengths')
        tenets_i = emp.get('talent_tenets_improvements')
    else:
        what = emp.talent_perf_what
        how = emp.talent_perf_how
        actions = emp.talent_proposed_actions
        tenets_s = emp.talent_tenets_strengths
        tenets_i = emp.talent_tenets_improvements

    return bool(what) and bool(how) and bool(actions) and _has_tenets(tenets_s, tenets_i)


# Initialize database on startup
init_db()

# Start demo mode cleanup thread if enabled
if DEMO_MODE:
    from demo_mode import (
        start_cleanup_thread, demo_response_wrapper,
        get_session_id, initialize_session_from_template
    )
    from demo_mode import _log
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


def get_all_employees():
    """Get all employees from database."""
    db = get_db()
    try:
        employees = db.query(Employee).all()
        return [emp.to_dict() for emp in employees]
    finally:
        db.close()


def get_currency_format(currency_code):
    """Get the full formatting info for a currency code.

    Returns:
        dict: {'code': str, 'symbol': str, 'position': 'before'|'after', 'space': bool}
    """
    default = {'symbol': currency_code, 'position': 'before', 'space': False}
    fmt = CURRENCY_FORMATS.get(currency_code, default)
    return {
        'code': currency_code,
        'symbol': fmt['symbol'],
        'position': fmt['position'],
        'space': fmt['space'],
    }


def get_manager_currency():
    """Detect the manager's currency from employee data.

    The manager's currency is determined by looking at domestic employees
    (those whose bonus_target_manager_currency is NULL, meaning their local
    currency IS the manager's currency).

    Returns:
        tuple: (currency_code, currency_symbol) e.g., ('AUD', 'A$')
               Defaults to ('USD', '$') if no employees or unable to detect.

    Note: Result is cached per-request in Flask's g object to avoid
    repeated database queries (important for template filters).
    """
    from flask import g, has_request_context

    # Return cached result if available (avoids repeated DB queries in templates)
    if has_request_context() and hasattr(g, '_manager_currency'):
        return g._manager_currency

    db = get_db()
    try:
        # Domestic employees have NULL in bonus_target_manager_currency
        # because their local currency IS the manager's currency
        domestic = db.query(Employee).filter(
            Employee.bonus_target_manager_currency.is_(None),
            Employee.currency.isnot(None)
        ).first()

        if domestic and domestic.currency:
            currency = domestic.currency
            symbol = CURRENCY_SYMBOLS.get(currency, currency)
            result = (currency, symbol)
        elif db.query(Employee).filter(Employee.currency.isnot(None)).first():
            # If all employees have manager_currency set, use majority currency
            from collections import Counter
            all_employees = db.query(Employee).filter(
                Employee.currency.isnot(None)
            ).all()
            currencies = [e.currency for e in all_employees]
            if currencies:
                most_common = Counter(currencies).most_common(1)[0][0]
                symbol = CURRENCY_SYMBOLS.get(most_common, most_common)
                result = (most_common, symbol)
            else:
                result = ('USD', '$')
        else:
            # Default to USD
            result = ('USD', '$')

        # Cache result for this request
        if has_request_context():
            g._manager_currency = result

        return result
    finally:
        db.close()


def get_employee_by_id(associate_id):
    """Get a single employee by ID."""
    db = get_db()
    try:
        return db.query(Employee).filter(Employee.associate_id == associate_id).first()
    finally:
        db.close()


def get_bonus_settings():
    """Get bonus settings from database, creating default if needed."""
    db = get_db()
    try:
        settings = db.query(BonusSettings).first()
        if not settings:
            # Create default settings
            settings = BonusSettings(budget_override=0.0, last_updated=datetime.now())
            db.add(settings)
            db.commit()
            db.refresh(settings)
        return settings
    finally:
        db.close()


def update_bonus_settings(budget_override):
    """Update bonus settings in database."""
    db = get_db()
    try:
        settings = db.query(BonusSettings).first()
        if not settings:
            settings = BonusSettings()
            db.add(settings)

        settings.budget_override = budget_override
        settings.last_updated = datetime.now()
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def load_tenets_config():
    """
    Load tenets configuration from tenets.json.

    Returns:
        tuple: (tenets_config dict, tenets_map dict mapping id->name)
               Returns (None, {}) if no config found
    """
    tenets_file = 'tenets.json'
    if os.path.exists(tenets_file):
        try:
            with open(tenets_file, 'r') as f:
                tenets_config = json.load(f)
                tenets_map = {t['id']: t['name'] for t in tenets_config.get('tenets', [])}
                return tenets_config, tenets_map
        except Exception as e:
            print(f"Error loading tenets from {tenets_file}: {e}")
    return None, {}


def get_filter_params():
    """
    Extract filter parameters from URL query string.

    Returns dict with:
    {
        'exclude_managers': bool,
        'exclude_titles': [str],
        'exclude_ids': [str]
    }
    """
    return {
        'exclude_managers': request.args.get('exclude_managers', '').lower() == 'true',
        'exclude_titles': [t.strip() for t in request.args.get('exclude_titles', '').split(',') if t.strip()],
        'exclude_ids': [i.strip() for i in request.args.get('exclude_ids', '').split(',') if i.strip()]
    }


def has_direct_reports(employee, all_employees):
    """
    Check if an employee has direct reports (is a manager).

    Detection methods (OR logic):
    1. Supervisory org lookup: employee's name appears in other employees'
       "Supervisory Organization" field (works for bonus files)
    2. Management level: employee's management_level contains "Manager"
       or "Director" (works for talent calibration files)

    Args:
        employee: Employee dict to check
        all_employees: List of all employee dicts

    Returns:
        bool: True if employee has direct reports/is a manager
    """
    # Method 1: Check management_level field (from talent calibration data)
    # Values like "Manager", "Senior Manager", "Director" indicate management
    management_level = (employee.get('management_level') or '').lower()
    if management_level:
        # Check for manager/director keywords (not "Individual Contributor")
        manager_keywords = ['manager', 'director', 'vp', 'vice president', 'head of']
        if any(keyword in management_level for keyword in manager_keywords):
            return True

    # Method 2: Check if name appears in other employees' supervisory org
    employee_name = employee.get('Associate', '')
    if employee_name:
        for other_emp in all_employees:
            if other_emp.get('Associate ID') == employee.get('Associate ID'):
                continue  # Skip self

            supervisory_org = other_emp.get('Supervisory Organization') or ''
            if employee_name in supervisory_org:
                return True

    return False


def apply_employee_filters(employees, filter_params):
    """
    Apply filters to employee list and return filter metadata.

    Args:
        employees: List of ALL employee dicts (unfiltered)
        filter_params: Dict with filter criteria from get_filter_params()

    Returns:
        tuple: (filtered_employees, filter_info)

        filter_info includes:
        {
            'active': bool,                     # Any filters active?
            'total_count': int,                 # Original count
            'filtered_count': int,              # After filtering
            'hidden_count': int,                # How many hidden
            'params': filter_params,            # For UI state
            'available_titles': [str],          # All unique job titles
            'available_employees': [dict],      # All employees [{id, name}]
            'manager_ids': [str],               # IDs of managers
            'employee_titles': {id: title},     # ID -> job title mapping
        }
    """
    filtered = employees.copy()

    # Apply manager exclusion
    if filter_params.get('exclude_managers'):
        filtered = [emp for emp in filtered if not has_direct_reports(emp, employees)]

    # Apply title exclusion
    if filter_params.get('exclude_titles'):
        exclude_titles = filter_params['exclude_titles']
        filtered = [emp for emp in filtered
                   if emp.get('Current Job Profile') not in exclude_titles]

    # Apply ID exclusion
    if filter_params.get('exclude_ids'):
        exclude_ids = filter_params['exclude_ids']
        filtered = [emp for emp in filtered
                   if emp.get('Associate ID') not in exclude_ids]

    # Build available options from ALL employees (unfiltered)
    available_titles = sorted(set(
        emp.get('Current Job Profile', '')
        for emp in employees
        if emp.get('Current Job Profile')
    ))

    # Build list of employees with ID, name pairs (sorted by name for UI)
    available_employees = sorted(
        [{'id': emp.get('Associate ID', ''), 'name': emp.get('Associate', '')}
         for emp in employees
         if emp.get('Associate ID') and emp.get('Associate')],
        key=lambda x: x['name']
    )

    # Build manager list (IDs of employees with direct reports)
    manager_ids = [
        emp.get('Associate ID', '')
        for emp in employees
        if has_direct_reports(emp, employees)
    ]

    # Build employee ID -> job title mapping
    employee_titles = {
        emp.get('Associate ID', ''): emp.get('Current Job Profile', '')
        for emp in employees
        if emp.get('Associate ID')
    }

    # Build filter info
    filter_info = {
        'active': any([
            filter_params.get('exclude_managers'),
            filter_params.get('exclude_titles'),
            filter_params.get('exclude_ids')
        ]),
        'total_count': len(employees),
        'filtered_count': len(filtered),
        'hidden_count': len(employees) - len(filtered),
        'params': filter_params,
        'available_titles': available_titles,
        'available_employees': available_employees,
        'manager_ids': manager_ids,
        'employee_titles': employee_titles,
    }

    return filtered, filter_info


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
        bonus_pct = emp.get('performance_rating_percent')
        talent_overall = emp.get('talent_overall_perf')
        alignment = get_cross_cycle_alignment(bonus_pct, talent_overall)
        alignment_stats[alignment] += 1

        # Add alignment to employee for display in Team Overview table
        emp['alignment'] = alignment

        # Only include employees with some data for the alignment table
        if bonus_pct is not None or talent_overall is not None:
            alignment_data.append({
                'associate_id': emp.get('Associate ID'),
                'name': emp.get('Associate'),
                'bonus_pct': bonus_pct,
                'talent_overall': talent_overall,
                'alignment': alignment,
            })

    # Count calibrated employees (What + How + Actions + Tenets)
    calibrated_count = sum(1 for emp in team_data if is_employee_calibrated(emp))

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
                         calibrated_count=calibrated_count)


@app.route('/rate')
def rate_page():
    """Rating form page."""
    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Pre-compute rating status for each employee
    for emp in team_data:
        has_tenets = bool(
            (emp.get('tenets_strengths') and emp.get('tenets_strengths') != '[]') or
            (emp.get('tenets_improvements') and emp.get('tenets_improvements') != '[]')
        )
        emp['_is_rated'] = bool(
            emp.get('performance_rating_percent') and
            emp.get('justification') and
            has_tenets
        )

    # Count rated employees
    rated_count = sum(1 for e in team_data if e['_is_rated'])

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
            team_rated = sum(1 for e in members if e['_is_rated'])
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
    all_employees = get_all_employees()
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
        if 'rating_percent' in data:
            employee.performance_rating_percent = rating_percent
        if 'justification' in data:
            employee.justification = data.get('justification', '')
        if 'mentor' in data:
            employee.mentor = data.get('mentor', '')
        if 'mentees' in data:
            employee.mentees = data.get('mentees', '')
        if tenets_strengths is not None:
            employee.tenets_strengths = json.dumps(tenets_strengths) if tenets_strengths else None
        if tenets_improvements is not None:
            employee.tenets_improvements = json.dumps(tenets_improvements) if tenets_improvements else None

        employee.last_updated = datetime.now()

        db.commit()

        return jsonify({'success': True, 'message': 'Rating saved successfully'})
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

    # Count calibrated employees (What + How + Actions + Tenets)
    calibrated_count = sum(1 for e in team_data if is_employee_calibrated(e))

    return render_template(
        'calibrate.html',
        team=team_data,
        filter_info=filter_info,
        calibrated_count=calibrated_count,
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
        text_fields = [
            'talent_proposed_actions',
            'talent_promo_job_profile',
            'talent_promo_business_need',
            'talent_promo_role_scope',
            'talent_promo_readiness',
            'talent_mentor',
            'talent_mentees',
        ]

        for field in text_fields:
            if field in data:
                value = data.get(field)
                setattr(employee, field, value if value else None)

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

        return jsonify({
            'success': True,
            'data': {
                'talent_overall_perf': employee.talent_overall_perf,
                'talent_identified_future': employee.talent_identified_future,
                'talent_last_updated': employee.talent_last_updated.strftime('%Y-%m-%d %H:%M:%S')
            }
        })

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
    tenets_config, _ = load_tenets_config()
    if tenets_config is None:
        return jsonify({'error': 'Tenets configuration file not found'}), 404
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


def calculate_calibration_for_employees(employees, team_name=None):
    """
    Calculate calibration distribution for a group of employees.

    Args:
        employees: List of employee dicts (must have performance_rating_percent)
        team_name: Optional name of team for display purposes

    Returns:
        Dict with calibration data, total_rated, and team_name
    """
    total_rated = len(employees)

    calibration_buckets = {
        'above_120': {'count': 0, 'suggested_min': 10, 'suggested_max': 20},
        '90_to_120': {'count': 0, 'suggested_min': 60, 'suggested_max': 80},
        '60_to_90': {'count': 0, 'suggested_min': 5, 'suggested_max': 15},
        'below_60': {'count': 0, 'suggested_min': 2, 'suggested_max': 5}
    }

    for emp in employees:
        rating = emp.get('performance_rating_percent')
        if rating:
            try:
                rating = float(rating)
                if rating > RATING_THRESHOLD_HIGH:
                    calibration_buckets['above_120']['count'] += 1
                elif rating >= RATING_THRESHOLD_MID:
                    calibration_buckets['90_to_120']['count'] += 1
                elif rating >= RATING_THRESHOLD_LOW:
                    calibration_buckets['60_to_90']['count'] += 1
                else:
                    calibration_buckets['below_60']['count'] += 1
            except (ValueError, TypeError):
                continue

    # Calculate percentages and deltas
    calibration_data = []
    for bucket_key, bucket_data in calibration_buckets.items():
        count = bucket_data['count']
        percentage = round((count / total_rated * 100), 1) if total_rated > 0 else 0
        suggested_min = bucket_data['suggested_min']
        suggested_max = bucket_data['suggested_max']
        suggested_mid = (suggested_min + suggested_max) / 2

        # Calculate suggested people counts based on percentages
        suggested_min_people = round(suggested_min * total_rated / 100) if total_rated > 0 else 0
        suggested_max_people = round(suggested_max * total_rated / 100) if total_rated > 0 else 0

        # Determine if within range
        within_range = suggested_min <= percentage <= suggested_max

        # Calculate delta from range limits (0 if within range, otherwise distance from nearest limit)
        if percentage < suggested_min:
            delta = percentage - suggested_min  # Negative value (below range)
        elif percentage > suggested_max:
            delta = percentage - suggested_max  # Positive value (above range)
        else:
            delta = 0  # Within range

        # Determine status: green (within), yellow (slightly off), orange (significantly off)
        if within_range:
            status = 'good'
        elif abs(delta) <= 10:
            status = 'warning'
        else:
            status = 'alert'

        calibration_data.append({
            'bucket': bucket_key,
            'count': count,
            'percentage': percentage,
            'suggested_min': suggested_min,
            'suggested_max': suggested_max,
            'suggested_mid': suggested_mid,
            'suggested_min_people': suggested_min_people,
            'suggested_max_people': suggested_max_people,
            'delta': delta,
            'within_range': within_range,
            'status': status
        })

    return {
        'data': calibration_data,
        'total_rated': total_rated,
        'team_name': team_name
    }


def calculate_mentorship_stats(employees):
    """
    Calculate mentorship statistics for a group of employees.

    Args:
        employees: List of employee dicts

    Returns:
        Dict with:
        - overall: {total, with_mentor, with_mentees, pct_with_mentor, pct_with_mentees, total_mentee_count}
        - by_job_title: [{job_title, count, with_mentor, with_mentees, pct_with_mentor, pct_with_mentees}]
        - top_mentors: [{name, associate_id, job_profile, mentee_count}]
    """
    total = len(employees)
    if total == 0:
        return {
            'overall': {
                'total': 0, 'with_mentor': 0, 'with_mentees': 0,
                'pct_with_mentor': 0, 'pct_with_mentees': 0, 'total_mentee_count': 0
            },
            'by_job_title': [],
            'top_mentors': []
        }

    # Track overall stats
    with_mentor = 0
    with_mentees = 0
    total_mentee_count = 0

    # Track by job title
    job_title_stats = {}  # {job_title: {count, with_mentor, with_mentees}}

    # Track top mentors
    mentors_list = []

    for emp in employees:
        # Check if employee has a mentor (combine bonus + talent cycle fields)
        bonus_mentor = (emp.get('mentor') or '').strip()
        talent_mentor = (emp.get('talent_mentor') or '').strip()
        has_mentor = bool(bonus_mentor or talent_mentor)
        if has_mentor:
            with_mentor += 1

        # Check if employee is mentoring others (combine bonus + talent cycle fields)
        bonus_mentees = emp.get('mentees') or ''
        talent_mentees = emp.get('talent_mentees') or ''
        # Combine both fields, avoiding duplicates
        all_mentees = set()
        for mentee_str in [bonus_mentees, talent_mentees]:
            for m in mentee_str.split(','):
                if m.strip():
                    all_mentees.add(m.strip())
        mentee_names = list(all_mentees)
        mentee_count = len(mentee_names)
        has_mentees = mentee_count > 0
        if has_mentees:
            with_mentees += 1
            total_mentee_count += mentee_count
            mentors_list.append({
                'name': emp.get('Associate', 'Unknown'),
                'associate_id': emp.get('Associate ID', ''),
                'job_profile': emp.get('Current Job Profile', 'Unknown'),
                'mentee_count': mentee_count
            })

        # Aggregate by job title
        job_title = emp.get('Current Job Profile', 'Unknown') or 'Unknown'
        if job_title not in job_title_stats:
            job_title_stats[job_title] = {'count': 0, 'with_mentor': 0, 'with_mentees': 0}
        job_title_stats[job_title]['count'] += 1
        if has_mentor:
            job_title_stats[job_title]['with_mentor'] += 1
        if has_mentees:
            job_title_stats[job_title]['with_mentees'] += 1

    # Build by_job_title list with percentages
    by_job_title = []
    for job_title, stats in sorted(job_title_stats.items()):
        count = stats['count']
        by_job_title.append({
            'job_title': job_title,
            'count': count,
            'with_mentor': stats['with_mentor'],
            'with_mentees': stats['with_mentees'],
            'pct_with_mentor': round(stats['with_mentor'] / count * 100, 1) if count > 0 else 0,
            'pct_with_mentees': round(stats['with_mentees'] / count * 100, 1) if count > 0 else 0
        })

    # Sort top mentors by mentee count descending
    top_mentors = sorted(mentors_list, key=lambda x: x['mentee_count'], reverse=True)[:10]

    return {
        'overall': {
            'total': total,
            'with_mentor': with_mentor,
            'with_mentees': with_mentees,
            'pct_with_mentor': round(with_mentor / total * 100, 1) if total > 0 else 0,
            'pct_with_mentees': round(with_mentees / total * 100, 1) if total > 0 else 0,
            'total_mentee_count': total_mentee_count
        },
        'by_job_title': by_job_title,
        'top_mentors': top_mentors
    }


@app.route('/analytics')
def analytics():
    """Analytics and reports page."""
    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Rating distribution by buckets
    rating_buckets = {
        '0-50%': 0,
        '51-80%': 0,
        '81-100%': 0,
        '101-130%': 0,
        '131-200%': 0
    }

    department_ratings = defaultdict(list)
    job_ratings = defaultdict(list)

    for emp in team_data:
        rating = emp.get('performance_rating_percent')
        if rating:
            try:
                rating = float(rating)

                # Bucket the rating
                if rating <= 50:
                    rating_buckets['0-50%'] += 1
                elif rating <= 80:
                    rating_buckets['51-80%'] += 1
                elif rating <= 100:
                    rating_buckets['81-100%'] += 1
                elif rating <= 130:
                    rating_buckets['101-130%'] += 1
                else:
                    rating_buckets['131-200%'] += 1

                # By supervisory org
                dept = emp.get('Supervisory Organization', 'Unknown')
                department_ratings[dept].append(rating)

                # By job profile
                job = emp.get('Current Job Profile', 'Unknown')
                job_ratings[job].append(rating)
            except (ValueError, TypeError):
                continue

    dept_averages = {
        dept: round(sum(ratings) / len(ratings), 1) if ratings else 0
        for dept, ratings in department_ratings.items()
    }

    job_averages = {
        job: round(sum(ratings) / len(ratings), 1) if ratings else 0
        for job, ratings in job_ratings.items()
    }

    # Sort team by rating
    def get_rating(emp):
        try:
            return float(emp.get('performance_rating_percent', 0) or 0)
        except (ValueError, TypeError):
            return 0

    sorted_team = sorted(team_data, key=get_rating, reverse=True)

    # Calculate calibration distribution
    # Only count rated employees for calibration
    rated_employees = [emp for emp in team_data if emp.get('performance_rating_percent')]
    total_rated = len(rated_employees)

    # Calculate org-level calibration using helper function
    org_calibration = calculate_calibration_for_employees(rated_employees, "Organization")
    calibration_data = org_calibration['data']

    # Load tenets configuration
    tenets_config, _ = load_tenets_config()
    tenets_config = tenets_config or {}
    # Create a map of tenet ID to full tenet data (for analytics display)
    tenets_map = {t['id']: t for t in tenets_config.get('tenets', [])}

    # Analyze tenets data - Overall
    strength_counts = defaultdict(int)
    improvement_counts = defaultdict(int)
    employees_with_tenets = 0

    for emp in team_data:
        has_tenets = False

        # Count strengths (combine bonus + talent cycle fields, deduplicate)
        all_strengths = set()
        for field in ['tenets_strengths', 'talent_tenets_strengths']:
            if emp.get(field):
                try:
                    strengths = json.loads(emp[field])
                    all_strengths.update(strengths)
                except json.JSONDecodeError:
                    pass
        for tenet_id in all_strengths:
            strength_counts[tenet_id] += 1
            has_tenets = True

        # Count improvements (combine bonus + talent cycle fields, deduplicate)
        all_improvements = set()
        for field in ['tenets_improvements', 'talent_tenets_improvements']:
            if emp.get(field):
                try:
                    improvements = json.loads(emp[field])
                    all_improvements.update(improvements)
                except json.JSONDecodeError:
                    pass
        for tenet_id in all_improvements:
            improvement_counts[tenet_id] += 1
            has_tenets = True

        if has_tenets:
            employees_with_tenets += 1

    # Build tenets summary with names
    tenets_summary = []
    all_tenet_ids = set(strength_counts.keys()) | set(improvement_counts.keys())

    for tenet_id in all_tenet_ids:
        tenet_info = tenets_map.get(tenet_id, {})
        tenets_summary.append({
            'id': tenet_id,
            'name': tenet_info.get('name', tenet_id),
            'category': tenet_info.get('category', 'Unknown'),
            'strength_count': strength_counts.get(tenet_id, 0),
            'improvement_count': improvement_counts.get(tenet_id, 0),
            'total_mentions': strength_counts.get(tenet_id, 0) + improvement_counts.get(tenet_id, 0)
        })

    # Sort by total mentions descending
    tenets_summary.sort(key=lambda x: x['total_mentions'], reverse=True)

    # Analyze tenets data - Per Organization
    org_tenets = {}
    for emp in team_data:
        org = emp.get('Supervisory Organization', 'Unknown')
        if org not in org_tenets:
            org_tenets[org] = {
                'strength_counts': defaultdict(int),
                'improvement_counts': defaultdict(int),
                'employees_with_tenets': 0
            }

        has_tenets = False

        # Count strengths per org
        if emp.get('tenets_strengths'):
            try:
                strengths = json.loads(emp['tenets_strengths'])
                for tenet_id in strengths:
                    org_tenets[org]['strength_counts'][tenet_id] += 1
                    has_tenets = True
            except json.JSONDecodeError:
                pass

        # Count improvements per org
        if emp.get('tenets_improvements'):
            try:
                improvements = json.loads(emp['tenets_improvements'])
                for tenet_id in improvements:
                    org_tenets[org]['improvement_counts'][tenet_id] += 1
                    has_tenets = True
            except json.JSONDecodeError:
                pass

        if has_tenets:
            org_tenets[org]['employees_with_tenets'] += 1

    # Build per-org tenets summary
    org_tenets_summary = {}
    for org, data in org_tenets.items():
        org_all_tenet_ids = set(data['strength_counts'].keys()) | set(data['improvement_counts'].keys())
        org_summary = []

        for tenet_id in org_all_tenet_ids:
            tenet_info = tenets_map.get(tenet_id, {})
            org_summary.append({
                'id': tenet_id,
                'name': tenet_info.get('name', tenet_id),
                'category': tenet_info.get('category', 'Unknown'),
                'strength_count': data['strength_counts'].get(tenet_id, 0),
                'improvement_count': data['improvement_counts'].get(tenet_id, 0),
                'total_mentions': data['strength_counts'].get(tenet_id, 0) + data['improvement_counts'].get(tenet_id, 0)
            })

        # Sort by net score (strengths - improvements) descending
        org_summary.sort(key=lambda x: x['strength_count'] - x['improvement_count'], reverse=True)

        org_tenets_summary[org] = {
            'tenets': org_summary,
            'employees_with_tenets': data['employees_with_tenets']
        }

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

    # Detect multi-team scenario by checking unique supervisory organizations
    unique_orgs = set()
    for emp in rated_employees:
        org = emp.get('Supervisory Organization')
        if org:
            unique_orgs.add(org)

    is_multi_team = len(unique_orgs) > 1

    # If multi-team, calculate per-team calibrations and comparisons
    team_calibrations = []
    team_comparisons = []

    if is_multi_team:
        # Group employees by supervisory organization
        teams_by_org = {}
        for emp in rated_employees:
            org = emp.get('Supervisory Organization', 'Unknown')
            if org not in teams_by_org:
                teams_by_org[org] = []
            teams_by_org[org].append(emp)

        # Calculate calibration for each team
        for org_name, team_employees in teams_by_org.items():
            team_cal = calculate_calibration_for_employees(team_employees, org_name)
            team_calibrations.append(team_cal)

            # Calculate team stats for comparison
            ratings = [float(e.get('performance_rating_percent', 0)) for e in team_employees]
            avg_rating = sum(ratings) / len(ratings) if ratings else 0
            std_dev = (sum((r - avg_rating) ** 2 for r in ratings) / len(ratings)) ** 0.5 if len(ratings) > 1 else 0

            # Count issues (buckets outside range)
            issues = sum(1 for item in team_cal['data'] if item['status'] != 'good')

            # Determine calibration health
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

    # Calculate mentorship statistics
    mentorship_stats = calculate_mentorship_stats(team_data)

    # If multi-team, also calculate per-team mentorship stats
    team_mentorship_stats = []
    if is_multi_team:
        teams_by_org = {}
        for emp in team_data:
            org = emp.get('Supervisory Organization', 'Unknown')
            if org not in teams_by_org:
                teams_by_org[org] = []
            teams_by_org[org].append(emp)

        for org_name, team_employees in sorted(teams_by_org.items()):
            team_stats = calculate_mentorship_stats(team_employees)
            team_mentorship_stats.append({
                'team_name': org_name,
                'stats': team_stats['overall']
            })

    # Mentorship analysis - identify patterns worth reviewing
    senior_keywords = ['senior', 'staff', 'principal', 'lead', 'director', 'manager', 'head', 'vp']
    junior_keywords = ['associate', 'junior', 'intern', 'trainee', 'graduate', 'entry']

    mentorship_analysis = {
        'seniors_without_mentees': [],   # Senior roles not mentoring anyone
        'heavy_mentoring_load': [],      # Anyone with 4+ mentees
        'unmentored_juniors': []         # Junior roles without a mentor
    }

    for emp in team_data:
        job_profile = (emp.get('Current Job Profile') or '').lower()
        # Combine bonus + talent cycle mentorship fields
        bonus_mentees = emp.get('mentees') or ''
        talent_mentees = emp.get('talent_mentees') or ''
        bonus_mentor = (emp.get('mentor') or '').strip()
        talent_mentor = (emp.get('talent_mentor') or '').strip()
        # Combine mentees from both fields, avoiding duplicates
        all_mentees = set()
        for mentee_str in [bonus_mentees, talent_mentees]:
            for m in mentee_str.split(','):
                if m.strip():
                    all_mentees.add(m.strip())
        mentee_count = len(all_mentees)
        has_mentees = mentee_count > 0
        has_mentor = bool(bonus_mentor or talent_mentor)

        emp_info = {
            'name': emp.get('Associate', 'Unknown'),
            'id': emp.get('Associate ID', ''),
            'job': emp.get('Current Job Profile', ''),
            'mentee_count': mentee_count,
            'has_mentor': has_mentor
        }

        # Seniors without mentees
        is_senior = any(kw in job_profile for kw in senior_keywords)
        if is_senior and not has_mentees:
            mentorship_analysis['seniors_without_mentees'].append(emp_info)

        # Heavy mentoring load (4+ mentees)
        if mentee_count >= 4:
            mentorship_analysis['heavy_mentoring_load'].append(emp_info)

        # Unmentored juniors
        is_junior = any(kw in job_profile for kw in junior_keywords)
        if is_junior and not has_mentor:
            mentorship_analysis['unmentored_juniors'].append(emp_info)

    total_mentorship_flags = sum(len(v) for v in mentorship_analysis.values())

    # Calculate talent calibration distributions (Spec §7.3)
    talent_calibration = None
    employees_with_talent = [emp for emp in team_data if emp.get('talent_overall_perf')]

    if employees_with_talent:
        total_talent = len(employees_with_talent)

        # Overall Performance Distribution
        overall_perf_counts = {
            'High Impact Performer': 0,
            'Successful Performer': 0,
            'Evolving Performer': 0,
            'Low Performer': 0
        }
        for emp in employees_with_talent:
            perf = emp.get('talent_overall_perf')
            if perf in overall_perf_counts:
                overall_perf_counts[perf] += 1

        # Future Talent count
        future_talent_count = sum(1 for emp in team_data if emp.get('talent_identified_future'))

        # Movement Readiness Distribution
        movement_counts = {
            'Continue growing in current role': 0,
            'Ready Now to be promoted in current role': 0,
            'Ready for lateral move': 0
        }
        for emp in employees_with_talent:
            movement = emp.get('talent_movement_readiness')
            if movement in movement_counts:
                movement_counts[movement] += 1

        # Suggested ranges based on Gartner research benchmarks
        talent_suggested_ranges = {
            'High Impact Performer': (10, 20),
            'Successful Performer': (60, 80),
            'Evolving Performer': (5, 15),
            'Low Performer': (2, 5),
            'Future Talent': (10, 20)
        }

        # Build talent calibration data
        talent_calibration_data = []
        for perf_level in ['High Impact Performer', 'Successful Performer', 'Evolving Performer', 'Low Performer']:
            count = overall_perf_counts[perf_level]
            pct = round(count / total_talent * 100, 1) if total_talent > 0 else 0
            suggested_min, suggested_max = talent_suggested_ranges[perf_level]

            # Calculate delta from range (same as bonus calibration)
            within_range = suggested_min <= pct <= suggested_max
            if pct < suggested_min:
                delta_from_range = pct - suggested_min  # Negative
            elif pct > suggested_max:
                delta_from_range = pct - suggested_max  # Positive
            else:
                delta_from_range = 0  # Within range

            # Determine status (same logic as bonus calibration)
            if within_range:
                status = 'good'
            elif abs(delta_from_range) <= 10:
                status = 'warning'
            else:
                status = 'alert'

            # Delta for display (distance from midpoint)
            suggested_mid = (suggested_min + suggested_max) / 2
            delta = pct - suggested_mid

            talent_calibration_data.append({
                'level': perf_level,
                'count': count,
                'percentage': pct,
                'suggested_min': suggested_min,
                'suggested_max': suggested_max,
                'suggested_min_people': round(total_talent * suggested_min / 100),
                'suggested_max_people': round(total_talent * suggested_max / 100),
                'delta': delta,
                'status': status
            })

        # Future Talent row (same status logic as bonus calibration)
        ft_pct = round(future_talent_count / total_talent * 100, 1) if total_talent > 0 else 0
        ft_min, ft_max = talent_suggested_ranges['Future Talent']
        ft_within_range = ft_min <= ft_pct <= ft_max
        if ft_pct < ft_min:
            ft_delta_from_range = ft_pct - ft_min
        elif ft_pct > ft_max:
            ft_delta_from_range = ft_pct - ft_max
        else:
            ft_delta_from_range = 0

        if ft_within_range:
            ft_status = 'good'
        elif abs(ft_delta_from_range) <= 10:
            ft_status = 'warning'
        else:
            ft_status = 'alert'

        # Movement readiness data (informational, no ranges)
        movement_data = []
        for movement_level, count in movement_counts.items():
            pct = round(count / total_talent * 100, 1) if total_talent > 0 else 0
            movement_data.append({
                'level': movement_level,
                'count': count,
                'percentage': pct
            })

        # 9-Box Talent Matrix: Performance (X) vs Future Talent (Y)
        # Rows: Future Talent Yes (top), Future Talent No (bottom)
        # Columns: Low, Evolving, Successful, High Impact (left to right)
        perf_levels = ['Low Performer', 'Evolving Performer', 'Successful Performer', 'High Impact Performer']
        talent_matrix = {
            'future_talent_yes': {level: [] for level in perf_levels},
            'future_talent_no': {level: [] for level in perf_levels}
        }

        for emp in employees_with_talent:
            perf = emp.get('talent_overall_perf')
            is_future = emp.get('talent_identified_future', False)

            if perf in perf_levels:
                row_key = 'future_talent_yes' if is_future else 'future_talent_no'
                talent_matrix[row_key][perf].append({
                    'name': emp.get('Associate', 'Unknown'),
                    'id': emp.get('Associate ID', ''),
                    'job': emp.get('Current Job Profile', '')
                })

        # Convert to counts for chart rendering
        talent_matrix_counts = {
            'future_talent_yes': [len(talent_matrix['future_talent_yes'][level]) for level in perf_levels],
            'future_talent_no': [len(talent_matrix['future_talent_no'][level]) for level in perf_levels],
            'labels': ['Low', 'Evolving', 'Successful', 'High Impact']
        }

        talent_calibration = {
            'total': total_talent,
            'performance_data': talent_calibration_data,
            'future_talent': {
                'count': future_talent_count,
                'percentage': ft_pct,
                'suggested_min': ft_min,
                'suggested_max': ft_max,
                'status': ft_status
            },
            'movement_data': movement_data,
            'talent_matrix': talent_matrix_counts
        }

    # Detect potential inconsistencies between performance ratings and talent data
    inconsistencies = {
        'high_bonus_low_talent': [],    # Rating >90% but Low/Evolving talent
        'low_bonus_high_talent': [],    # Rating <90% but High Impact talent
        'future_talent_low_bonus': [],  # Future Talent but rating <90%
        'promotion_ready_low_rating': [],  # Ready Now but rating <100%
        'promotion_ready_not_high': [],   # Ready Now but not High Impact (talent measured in current role)
        'high_performer_not_future': [],  # High Impact but not Future Talent
        'bonus_only': [],               # Has performance rating but no talent data
        'talent_only': [],              # Has talent data but no performance rating
        'mentoring_mismatch': [],       # Mentor/mentees differ between bonus and talent cycles
        'tenet_mismatch': []            # Tenets differ between bonus and talent cycles
    }

    for emp in team_data:
        rating = emp.get('performance_rating_percent')
        talent_perf = emp.get('talent_overall_perf')
        is_future = emp.get('talent_identified_future', False)
        movement = emp.get('talent_movement_readiness') or ''

        emp_info = {
            'name': emp.get('Associate', 'Unknown'),
            'id': emp.get('Associate ID', ''),
            'job': emp.get('Current Job Profile', ''),
            'rating': rating,
            'talent': talent_perf,
            'is_future': is_future,
            'movement': movement
        }

        # High Bonus + Low Talent (rating >90% but Low/Evolving)
        if rating and rating > 90 and talent_perf in ['Low Performer', 'Evolving Performer']:
            inconsistencies['high_bonus_low_talent'].append(emp_info)

        # Low Bonus + High Talent (rating <90% but High Impact)
        if rating and rating < 90 and talent_perf == 'High Impact Performer':
            inconsistencies['low_bonus_high_talent'].append(emp_info)

        # Future Talent + Low Bonus (rating <90%)
        if is_future and rating and rating < 90:
            inconsistencies['future_talent_low_bonus'].append(emp_info)

        # Ready for Promotion + Low Rating (<100%)
        if 'Ready Now' in movement and rating and rating < 100:
            inconsistencies['promotion_ready_low_rating'].append(emp_info)

        # Ready for Promotion + Not High Performer (talent measured in current role)
        if 'Ready Now' in movement and talent_perf and talent_perf != 'High Impact Performer':
            inconsistencies['promotion_ready_not_high'].append(emp_info)

        # High Performer + Not Future Talent
        if talent_perf == 'High Impact Performer' and not is_future:
            inconsistencies['high_performer_not_future'].append(emp_info)

        # Data completeness checks
        if rating and not talent_perf:
            inconsistencies['bonus_only'].append(emp_info)
        elif talent_perf and not rating:
            inconsistencies['talent_only'].append(emp_info)

        # Mentoring mismatch between cycles
        bonus_mentor = (emp.get('mentor') or '').strip()
        bonus_mentees = (emp.get('mentees') or '').strip()
        talent_mentor = (emp.get('talent_mentor') or '').strip()
        talent_mentees = (emp.get('talent_mentees') or '').strip()

        # Check if there's any mentoring data and if it differs between cycles
        has_any_mentoring = any([bonus_mentor, bonus_mentees, talent_mentor, talent_mentees])
        if has_any_mentoring:
            mentor_differs = (bool(bonus_mentor) != bool(talent_mentor)) or \
                           (bonus_mentor and talent_mentor and bonus_mentor.lower() != talent_mentor.lower())
            mentees_differs = (bool(bonus_mentees) != bool(talent_mentees)) or \
                            (bonus_mentees and talent_mentees and bonus_mentees.lower() != talent_mentees.lower())

            if mentor_differs or mentees_differs:
                mentoring_info = {
                    'name': emp.get('Associate', 'Unknown'),
                    'id': emp.get('Associate ID', ''),
                    'job': emp.get('Current Job Profile', ''),
                    'bonus_mentor': bonus_mentor or '-',
                    'bonus_mentees': bonus_mentees or '-',
                    'talent_mentor': talent_mentor or '-',
                    'talent_mentees': talent_mentees or '-',
                    'mentor_differs': mentor_differs,
                    'mentees_differs': mentees_differs
                }
                inconsistencies['mentoring_mismatch'].append(mentoring_info)

        # Tenet mismatch between cycles (compare same categories: strengths→strengths, improvements→improvements)
        bonus_strengths = set()
        bonus_improvements = set()
        talent_strengths = set()
        talent_improvements = set()

        # Parse bonus cycle tenets
        if emp.get('tenets_strengths'):
            try:
                bonus_strengths = set(json.loads(emp['tenets_strengths']))
            except json.JSONDecodeError:
                pass
        if emp.get('tenets_improvements'):
            try:
                bonus_improvements = set(json.loads(emp['tenets_improvements']))
            except json.JSONDecodeError:
                pass

        # Parse talent cycle tenets
        if emp.get('talent_tenets_strengths'):
            try:
                talent_strengths = set(json.loads(emp['talent_tenets_strengths']))
            except json.JSONDecodeError:
                pass
        if emp.get('talent_tenets_improvements'):
            try:
                talent_improvements = set(json.loads(emp['talent_tenets_improvements']))
            except json.JSONDecodeError:
                pass

        # Check if there's any tenet data and if it differs between cycles
        has_any_tenets = any([bonus_strengths, bonus_improvements, talent_strengths, talent_improvements])
        if has_any_tenets:
            strengths_differ = bonus_strengths != talent_strengths
            improvements_differ = bonus_improvements != talent_improvements

            if strengths_differ or improvements_differ:
                # Convert IDs to names for display
                def tenet_names(tenet_ids):
                    return [tenets_map.get(tid, {}).get('name', tid) for tid in sorted(tenet_ids)]

                tenet_info = {
                    'name': emp.get('Associate', 'Unknown'),
                    'id': emp.get('Associate ID', ''),
                    'job': emp.get('Current Job Profile', ''),
                    'bonus_strengths': tenet_names(bonus_strengths) if bonus_strengths else [],
                    'bonus_improvements': tenet_names(bonus_improvements) if bonus_improvements else [],
                    'talent_strengths': tenet_names(talent_strengths) if talent_strengths else [],
                    'talent_improvements': tenet_names(talent_improvements) if talent_improvements else [],
                    'strengths_differ': strengths_differ,
                    'improvements_differ': improvements_differ
                }
                inconsistencies['tenet_mismatch'].append(tenet_info)

    # Calculate total count
    total_inconsistencies = sum(len(v) for v in inconsistencies.values())

    return render_template('analytics.html',
                         team=sorted_team,
                         chart_data=chart_data,
                         dept_averages=dept_averages,
                         job_averages=job_averages,
                         calibration_data=calibration_data,
                         total_rated=total_rated,
                         total_employees=len(team_data),
                         tenets_summary=tenets_summary,
                         employees_with_tenets=employees_with_tenets,
                         org_tenets_summary=org_tenets_summary,
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
                         filter_info=filter_info)


def calculate_bonus_for_employees(employees, params, budget_override=0.0, workday_pool=None, all_targets_sum=None):
    """
    Calculate bonuses for a given set of employees.
    Returns dict with results, normalization factor, and metadata.

    Args:
        employees: List of employee dicts (typically only rated employees)
        params: Dict with upside_exponent and downside_exponent
        budget_override: Additional budget (can be negative) to add to total pool
        workday_pool: Total pool from Workday metadata (authoritative budget).
        all_targets_sum: Sum of ALL employee bonus targets (for proportional calculation
                         when only a subset of employees are rated).
    """
    # Calculate sum of bonus targets for the employees being calculated
    sum_of_targets = 0
    for emp in employees:
        bonus_target = emp.get('Bonus Target Manager Currency') or emp.get('Bonus Target - Local Currency')
        if bonus_target:
            try:
                sum_of_targets += float(bonus_target)
            except (ValueError, TypeError):
                pass

    # Determine the base pool:
    # - If workday_pool is set (authoritative), use it or a proportional share
    # - Otherwise fall back to sum of targets
    if workday_pool is not None and workday_pool > 0:
        if all_targets_sum and all_targets_sum > 0 and sum_of_targets < all_targets_sum:
            # Partial rating: use proportional share of Workday pool
            proportion = sum_of_targets / all_targets_sum
            base_pool = workday_pool * proportion
        else:
            # All employees rated (or no all_targets_sum provided): use full Workday pool
            base_pool = workday_pool
    else:
        # No Workday pool: fall back to sum of targets
        base_pool = sum_of_targets

    # Calculate bonuses
    bonus_results = []
    total_raw_shares = 0
    employees_without_bonus_target = 0

    for emp in employees:
        try:
            rating = float(emp.get('performance_rating_percent', 100))
            bonus_target = float((emp.get('Bonus Target Manager Currency') or emp.get('Bonus Target - Local Currency')) or 0)
            base_pay = float((emp.get('Current Base Pay Manager Currency') or emp.get('Current Base Pay All Countries')) or 0)
        except (ValueError, TypeError):
            continue

        if bonus_target <= 0:
            employees_without_bonus_target += 1
            continue

        # Calculate Performance Multiplier (Split Curve)
        if rating < 100:
            perf_multiplier = (rating / 100) ** params['downside_exponent']
        else:
            perf_multiplier = (rating / 100) ** params['upside_exponent']

        # Calculate Raw Share
        raw_share = bonus_target * perf_multiplier
        total_raw_shares += raw_share

        bonus_results.append({
            'employee': emp,
            'rating': rating,
            'bonus_target': bonus_target,
            'base_pay': base_pay,
            'perf_multiplier': perf_multiplier,
            'raw_share': raw_share
        })

    # Apply budget override to create adjusted pool
    adjusted_pool = base_pool + budget_override

    # Normalization: Calculate value per share using adjusted pool
    value_per_share = adjusted_pool / total_raw_shares if total_raw_shares > 0 else 0

    # Calculate final bonuses
    total_allocated = 0
    for result in bonus_results:
        result['final_bonus'] = result['raw_share'] * value_per_share
        result['bonus_percent_of_target'] = (result['final_bonus'] / result['bonus_target'] * 100) if result['bonus_target'] > 0 else 0
        total_allocated += result['final_bonus']

    # Create lookup by Associate ID for easy access
    results_by_id = {r['employee']['Associate ID']: r for r in bonus_results}

    return {
        'results': bonus_results,
        'results_by_id': results_by_id,
        'workday_pool': workday_pool,        # From Workday metadata (may be None)
        'sum_of_targets': sum_of_targets,    # Calculated from employee targets
        'base_pool': base_pool,              # What we're using (workday_pool or sum_of_targets)
        'budget_override': budget_override,
        'total_pool': adjusted_pool,         # base_pool + budget_override
        'total_allocated': total_allocated,
        'value_per_share': value_per_share,
        'employees_without_bonus_target': employees_without_bonus_target
    }


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

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Filter to only rated employees
    rated_employees = [emp for emp in team_data if emp.get('performance_rating_percent')]

    # Calculate sum of ALL employee bonus targets (for proportional pool calculation)
    all_targets_sum = 0
    for emp in team_data:
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
                             filter_info=filter_info)

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

            # Calculate average rating for this team
            team_ratings = [float(e.get('performance_rating_percent', 100)) for e in team_employees]
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
                             filter_info=filter_info)

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
                         filter_info=filter_info)


@app.route('/export')
def export_page():
    """Export page for Workday bonus and talent data."""
    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Detect which data types are available
    rated_employees = [emp for emp in team_data if emp.get('performance_rating_percent')]
    calibrated_employees = [emp for emp in team_data if is_employee_calibrated(emp)]

    # has_bonus_data: true only if rated employees have actual bonus target data from Workday
    # (not just ratings without bonus targets)
    rated_with_bonus_targets = [
        emp for emp in rated_employees
        if emp.get('Bonus Target Manager Currency') or emp.get('Bonus Target - Local Currency')
    ]
    has_bonus_data = len(rated_with_bonus_targets) > 0
    has_talent_data = len(calibrated_employees) > 0

    # Determine default mode: prefer bonus if available (ratings + targets), else talent
    export_mode = request.args.get('mode', 'bonus' if has_bonus_data else 'talent')

    # If no data at all, show empty state
    if not has_bonus_data and not has_talent_data:
        return render_template('export.html',
                             export_data=[],
                             talent_export_data=[],
                             has_data=False,
                             has_bonus_data=False,
                             has_talent_data=False,
                             export_mode='bonus',
                             filter_info=filter_info)

    # Get bonus calculation settings
    params = {
        'upside_exponent': float(request.args.get('upside_exponent', 1.35)),
        'downside_exponent': float(request.args.get('downside_exponent', 1.9))
    }

    # Get bonus settings (pool and override)
    settings = get_bonus_settings()
    budget_override = settings.budget_override if settings else 0.0
    workday_pool = settings.workday_pool if settings else None

    # Calculate sum of ALL employee bonus targets (for proportional pool calculation)
    all_targets_sum = 0
    for emp in team_data:
        bonus_target = emp.get('Bonus Target Manager Currency') or emp.get('Bonus Target - Local Currency')
        if bonus_target:
            try:
                all_targets_sum += float(bonus_target)
            except (ValueError, TypeError):
                pass

    # Calculate bonuses for all rated employees
    bonus_calc = calculate_bonus_for_employees(rated_employees, params, budget_override, workday_pool, all_targets_sum)

    # Load tenets configuration
    _, tenets_map = load_tenets_config()

    # Format export data
    export_data = []
    for result in bonus_calc['results']:
        employee = result['employee']

        # Parse tenets
        strengths = []
        improvements = []
        try:
            if employee.get('tenets_strengths'):
                strength_ids = json.loads(employee['tenets_strengths']) if isinstance(employee['tenets_strengths'], str) else employee['tenets_strengths']
                strengths = [tenets_map.get(tid, tid) for tid in strength_ids if tid in tenets_map]
            if employee.get('tenets_improvements'):
                improvement_ids = json.loads(employee['tenets_improvements']) if isinstance(employee['tenets_improvements'], str) else employee['tenets_improvements']
                improvements = [tenets_map.get(tid, tid) for tid in improvement_ids if tid in tenets_map]
        except Exception as e:
            print(f"Error parsing tenets for {employee.get('Associate')}: {e}")

        # Build structured description text (human-readable and machine-parseable)
        description_lines = []

        # Performance rating
        if employee.get('performance_rating_percent'):
            description_lines.append(f"Performance Rating: {employee['performance_rating_percent']}%")

        # Justification
        if employee.get('justification'):
            description_lines.append(f"Justification: {employee['justification']}")

        # Mentor/Mentee
        if employee.get('mentor'):
            description_lines.append(f"Mentor: {employee['mentor']}")
        if employee.get('mentees'):
            description_lines.append(f"Mentees: {employee['mentees']}")

        # Tenets
        if strengths:
            description_lines.append(f"Strengths: {', '.join(strengths)}")
        if improvements:
            description_lines.append(f"Areas for Improvement: {', '.join(improvements)}")

        description_text = '\n'.join(description_lines)

        # Calculate bonus percent of target
        bonus_percent_of_target = result['bonus_percent_of_target']

        export_data.append({
            'employee': employee,
            'bonus_percent': round(bonus_percent_of_target, 1),
            'description': description_text,
            'final_bonus': result['final_bonus'],
            'rating': result['rating']
        })

    # Sort by employee name
    export_data.sort(key=lambda x: x['employee']['Associate'])

    # Build talent export data
    talent_export_data = []
    for emp in calibrated_employees:
        # Parse talent tenets
        talent_strengths = []
        talent_improvements = []
        try:
            if emp.get('talent_tenets_strengths'):
                strength_ids = json.loads(emp['talent_tenets_strengths']) if isinstance(emp['talent_tenets_strengths'], str) else emp['talent_tenets_strengths']
                talent_strengths = [tenets_map.get(tid, tid) for tid in strength_ids if tid in tenets_map]
            if emp.get('talent_tenets_improvements'):
                improvement_ids = json.loads(emp['talent_tenets_improvements']) if isinstance(emp['talent_tenets_improvements'], str) else emp['talent_tenets_improvements']
                talent_improvements = [tenets_map.get(tid, tid) for tid in improvement_ids if tid in tenets_map]
        except Exception as e:
            print(f"Error parsing talent tenets for {emp.get('Associate')}: {e}")

        # Build proposed actions text (includes embedded tenets for Workday)
        proposed_actions_parts = []
        if emp.get('talent_proposed_actions'):
            proposed_actions_parts.append(emp['talent_proposed_actions'])
        if talent_strengths:
            proposed_actions_parts.append(f"[Strengths: {', '.join(talent_strengths)}]")
        if talent_improvements:
            proposed_actions_parts.append(f"[Improvements: {', '.join(talent_improvements)}]")
        proposed_actions_text = ' '.join(proposed_actions_parts)

        talent_export_data.append({
            'employee': emp,
            'overall_perf': emp.get('talent_overall_perf', ''),
            'perf_what': emp.get('talent_perf_what', ''),
            'perf_how': emp.get('talent_perf_how', ''),
            'growth_agility': emp.get('talent_growth_agility', ''),
            'change_agility': emp.get('talent_change_agility', ''),
            'identified_future': emp.get('talent_identified_future', False),
            'movement_readiness': emp.get('talent_movement_readiness', ''),
            'proposed_actions': proposed_actions_text,
            'promo_job_profile': emp.get('talent_promo_job_profile', ''),
        })

    # Sort talent export data by employee name
    talent_export_data.sort(key=lambda x: x['employee']['Associate'])

    return render_template('export.html',
                         export_data=export_data,
                         talent_export_data=talent_export_data,
                         has_data=True,
                         has_bonus_data=has_bonus_data,
                         has_talent_data=has_talent_data,
                         export_mode=export_mode,
                         total_employees=len(export_data),
                         total_calibrated=len(talent_export_data),
                         filter_info=filter_info)


@app.route('/export/csv')
def export_csv():
    """Export employee data as CSV (same content as Excel)."""
    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Load tenets for description
    _, tenets_map = load_tenets_config()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Add demo mode warning header if in demo mode
    if DEMO_MODE:
        writer.writerow(['*** DEMO MODE - FICTITIOUS DATA ONLY ***'])
        writer.writerow(['This export contains sample data for demonstration purposes.'])
        writer.writerow(['Do NOT use this data for any real business decisions.'])
        writer.writerow([])

    # Write header (matching to_dict() keys for data access)
    writer.writerow([
        'Associate ID',
        'Associate',
        'Supervisory Organization',
        'Current Job Profile',
        'Photo',
        'Errors',
        'Current Base Pay All Countries',
        'Current Base Pay Manager Currency',
        'Currency',
        'Grade',
        'Annual Bonus Target Percent',
        'Last Bonus Allocation Percent',
        'Bonus Target - Local Currency',
        'Bonus Target Manager Currency',
        'Proposed Bonus Amount',
        'Proposed Bonus Amount Manager Currency',
        'Proposed Percent of Target Bonus',
        'Notes',
        'Zero Bonus Allocated',
        'Performance Rating Percent',
        'Justification',
        'Mentor',
        'Mentees',
        'Tenets Strengths',
        'Tenets Improvements',
        'Description'
    ])

    # Write data rows
    for employee in team_data:
        # Parse tenets
        strengths_text = ''
        improvements_text = ''
        description_parts = []

        try:
            if employee.get('tenets_strengths'):
                strength_ids = json.loads(employee['tenets_strengths']) if isinstance(employee['tenets_strengths'], str) else employee['tenets_strengths']
                strengths = [tenets_map.get(tid, tid) for tid in strength_ids if tid in tenets_map]
                strengths_text = ', '.join(strengths)

            if employee.get('tenets_improvements'):
                improvement_ids = json.loads(employee['tenets_improvements']) if isinstance(employee['tenets_improvements'], str) else employee['tenets_improvements']
                improvements = [tenets_map.get(tid, tid) for tid in improvement_ids if tid in tenets_map]
                improvements_text = ', '.join(improvements)
        except Exception as e:
            print(f"Error parsing tenets: {e}")

        # Build description
        if employee.get('performance_rating_percent'):
            description_parts.append(f"Performance Rating: {employee['performance_rating_percent']}%")
        if employee.get('justification'):
            description_parts.append(f"Justification: {employee['justification']}")
        if employee.get('mentor'):
            description_parts.append(f"Mentor: {employee['mentor']}")
        if employee.get('mentees'):
            description_parts.append(f"Mentees: {employee['mentees']}")
        if strengths_text:
            description_parts.append(f"Strengths: {strengths_text}")
        if improvements_text:
            description_parts.append(f"Areas for Improvement: {improvements_text}")

        description = '\n'.join(description_parts)

        writer.writerow([
            employee.get('Associate ID', ''),
            employee.get('Associate', ''),
            employee.get('Supervisory Organization', ''),
            employee.get('Current Job Profile', ''),
            employee.get('Photo', ''),
            employee.get('Errors', ''),
            employee.get('Current Base Pay All Countries', ''),
            employee.get('Current Base Pay Manager Currency', ''),
            employee.get('Currency', ''),
            employee.get('Grade', ''),
            employee.get('Annual Bonus Target Percent', ''),
            employee.get('Last Bonus Allocation Percent', ''),
            employee.get('Bonus Target - Local Currency', ''),
            employee.get('Bonus Target Manager Currency', ''),
            employee.get('Proposed Bonus Amount', ''),
            employee.get('Proposed Bonus Amount Manager Currency', ''),
            employee.get('Proposed Percent of Target Bonus', ''),
            employee.get('Notes', ''),
            employee.get('Zero Bonus Allocated', ''),
            employee.get('performance_rating_percent', ''),
            employee.get('justification', ''),
            employee.get('mentor', ''),
            employee.get('mentees', ''),
            strengths_text,
            improvements_text,
            description
        ])

    # Create response
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment; filename=performance_export.csv'
    return response


@app.route('/export/xlsx')
def export_xlsx():
    """Export employee data as Excel file with all fields."""
    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Employee Data"

    # Add demo mode warning if in demo mode
    demo_row_offset = 0
    if DEMO_MODE:
        demo_warning_fill = PatternFill(start_color='FF6B6B', end_color='FF6B6B', fill_type='solid')
        demo_warning_font = Font(bold=True, color='FFFFFF', size=14)

        ws.merge_cells('A1:Z1')
        demo_cell = ws.cell(row=1, column=1, value='*** DEMO MODE - FICTITIOUS DATA ONLY - DO NOT USE FOR BUSINESS DECISIONS ***')
        demo_cell.fill = demo_warning_fill
        demo_cell.font = demo_warning_font
        demo_cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 30

        demo_row_offset = 2  # Skip 2 rows for demo header

    # Define headers (matching to_dict() keys for data access)
    headers = [
        'Associate ID',
        'Associate',
        'Supervisory Organization',
        'Current Job Profile',
        'Photo',
        'Errors',
        'Current Base Pay All Countries',
        'Current Base Pay Manager Currency',
        'Currency',
        'Grade',
        'Annual Bonus Target Percent',
        'Last Bonus Allocation Percent',
        'Bonus Target - Local Currency',
        'Bonus Target Manager Currency',
        'Proposed Bonus Amount',
        'Proposed Bonus Amount Manager Currency',
        'Proposed Percent of Target Bonus',
        'Notes',
        'Zero Bonus Allocated',
        # Our custom fields
        'Performance Rating Percent',
        'Justification',
        'Mentor',
        'Mentees',
        'Tenets Strengths',
        'Tenets Improvements',
        'Description'  # Combined description field
    ]

    # Style header row
    header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')

    header_row = 1 + demo_row_offset
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Load tenets for description
    _, tenets_map = load_tenets_config()

    # Write data rows
    data_start_row = 2 + demo_row_offset
    for row_num, employee in enumerate(team_data, data_start_row):
        # Parse tenets
        strengths_text = ''
        improvements_text = ''
        description_parts = []

        try:
            if employee.get('tenets_strengths'):
                strength_ids = json.loads(employee['tenets_strengths']) if isinstance(employee['tenets_strengths'], str) else employee['tenets_strengths']
                strengths = [tenets_map.get(tid, tid) for tid in strength_ids if tid in tenets_map]
                strengths_text = ', '.join(strengths)

            if employee.get('tenets_improvements'):
                improvement_ids = json.loads(employee['tenets_improvements']) if isinstance(employee['tenets_improvements'], str) else employee['tenets_improvements']
                improvements = [tenets_map.get(tid, tid) for tid in improvement_ids if tid in tenets_map]
                improvements_text = ', '.join(improvements)
        except Exception as e:
            print(f"Error parsing tenets: {e}")

        # Build description
        if employee.get('performance_rating_percent'):
            description_parts.append(f"Performance Rating: {employee['performance_rating_percent']}%")
        if employee.get('justification'):
            description_parts.append(f"Justification: {employee['justification']}")
        if employee.get('mentor'):
            description_parts.append(f"Mentor: {employee['mentor']}")
        if employee.get('mentees'):
            description_parts.append(f"Mentees: {employee['mentees']}")
        if strengths_text:
            description_parts.append(f"Strengths: {strengths_text}")
        if improvements_text:
            description_parts.append(f"Areas for Improvement: {improvements_text}")

        description = '\n'.join(description_parts)

        row_data = [
            employee.get('Associate ID', ''),
            employee.get('Associate', ''),
            employee.get('Supervisory Organization', ''),
            employee.get('Current Job Profile', ''),
            employee.get('Photo', ''),
            employee.get('Errors', ''),
            employee.get('Current Base Pay All Countries', ''),
            employee.get('Current Base Pay Manager Currency', ''),
            employee.get('Currency', ''),
            employee.get('Grade', ''),
            employee.get('Annual Bonus Target Percent', ''),
            employee.get('Last Bonus Allocation Percent', ''),
            employee.get('Bonus Target - Local Currency', ''),
            employee.get('Bonus Target Manager Currency', ''),
            employee.get('Proposed Bonus Amount', ''),
            employee.get('Proposed Bonus Amount Manager Currency', ''),
            employee.get('Proposed Percent of Target Bonus', ''),
            employee.get('Notes', ''),
            employee.get('Zero Bonus Allocated', ''),
            # Our custom fields
            employee.get('performance_rating_percent', ''),
            employee.get('justification', ''),
            employee.get('mentor', ''),
            employee.get('mentees', ''),
            strengths_text,
            improvements_text,
            description
        ]

        for col_num, value in enumerate(row_data, 1):
            ws.cell(row=row_num, column=col_num, value=value)

    # Auto-adjust column widths (skip merged cells which don't have column_letter)
    from openpyxl.utils import get_column_letter
    for col_idx, column in enumerate(ws.columns, 1):
        max_length = 0
        for cell in column:
            try:
                if cell.value and hasattr(cell, 'column_letter'):
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        if max_length > 0:
            adjusted_width = min(max_length + 2, 50)  # Cap at 50
            ws.column_dimensions[get_column_letter(col_idx)].width = adjusted_width

    # Save to BytesIO
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='performance_export.xlsx'
    )


@app.route('/export/talent')
def export_talent_xlsx():
    """Export talent calibration data as Excel file.

    Embeds tenets in the Proposed Actions field using a parseable format
    so that Workday becomes the source of truth and re-imports preserve data.

    Format: [Strengths: Tenet1, Tenet2] [Improvements: Tenet3]
    """
    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Talent Calibration"

    # Add demo mode warning if in demo mode
    demo_row_offset = 0
    if DEMO_MODE:
        demo_warning_fill = PatternFill(start_color='FF6B6B', end_color='FF6B6B', fill_type='solid')
        demo_warning_font = Font(bold=True, color='FFFFFF', size=14)

        ws.merge_cells('A1:Z1')
        demo_cell = ws.cell(row=1, column=1, value='*** DEMO MODE - FICTITIOUS DATA ONLY - DO NOT USE FOR BUSINESS DECISIONS ***')
        demo_cell.fill = demo_warning_fill
        demo_cell.font = demo_warning_font
        demo_cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 30

        demo_row_offset = 2

    # Define headers matching Workday talent calibration format
    headers = [
        'Associate ID',
        'Worker',  # Workday uses 'Worker' not 'Associate'
        'Supervisory Organization',
        'Current Job Profile',
        'Performance: What',
        'Performance: How',
        'Overall Performance',
        'Future Talent: Growth Agility',
        'Future Talent: Change Agility',
        'Identified Future Talent',
        'Movement Readiness',
        'Proposed Talent Actions',  # Contains embedded tenets (matches import column map)
        'Promotions: Proposed Job Profile & Code',
        'Promotions: Business Need',
        'Promotions: Expanded Role Scope',
        'Promotions: Associate Readiness',
    ]

    # Style header row
    header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')

    header_row = 1 + demo_row_offset
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Load tenets for name lookup
    _, tenets_map = load_tenets_config()

    # Write data rows
    data_start_row = 2 + demo_row_offset
    for row_num, employee in enumerate(team_data, data_start_row):
        # Build Proposed Actions with embedded tenets
        proposed_actions = employee.get('talent_proposed_actions') or ''

        # Parse and format tenets
        strengths_text = ''
        improvements_text = ''

        try:
            if employee.get('talent_tenets_strengths'):
                strength_ids = json.loads(employee['talent_tenets_strengths']) if isinstance(employee['talent_tenets_strengths'], str) else employee['talent_tenets_strengths']
                strengths = [tenets_map.get(tid, tid) for tid in strength_ids if tid in tenets_map]
                if strengths:
                    strengths_text = '; '.join(strengths)  # Use semicolon (tenet names may contain commas)

            if employee.get('talent_tenets_improvements'):
                improvement_ids = json.loads(employee['talent_tenets_improvements']) if isinstance(employee['talent_tenets_improvements'], str) else employee['talent_tenets_improvements']
                improvements = [tenets_map.get(tid, tid) for tid in improvement_ids if tid in tenets_map]
                if improvements:
                    improvements_text = '; '.join(improvements)  # Use semicolon
        except Exception as e:
            print(f"Error parsing talent tenets: {e}")

        # Embed tenets and mentor/mentees in Proposed Actions using parseable format
        metadata_markers = []
        if strengths_text:
            metadata_markers.append(f"[Strengths: {strengths_text}]")
        if improvements_text:
            metadata_markers.append(f"[Improvements: {improvements_text}]")

        # Embed mentor/mentees
        talent_mentor = employee.get('talent_mentor', '')
        talent_mentees = employee.get('talent_mentees', '')
        if talent_mentor:
            metadata_markers.append(f"[Mentor: {talent_mentor}]")
        if talent_mentees:
            metadata_markers.append(f"[Mentees: {talent_mentees}]")

        if metadata_markers:
            # Append to proposed actions with separator
            if proposed_actions:
                proposed_actions = proposed_actions.rstrip() + '\n\n' + ' '.join(metadata_markers)
            else:
                proposed_actions = ' '.join(metadata_markers)

        row_data = [
            employee.get('Associate ID', ''),
            employee.get('Associate', ''),  # Export as Worker column
            employee.get('Supervisory Organization', ''),
            employee.get('Current Job Profile', ''),
            employee.get('talent_perf_what', ''),
            employee.get('talent_perf_how', ''),
            employee.get('talent_overall_perf', ''),
            employee.get('talent_growth_agility', ''),
            employee.get('talent_change_agility', ''),
            'Yes' if employee.get('talent_identified_future') else 'No' if employee.get('talent_identified_future') is False else '',
            employee.get('talent_movement_readiness', ''),
            proposed_actions,
            employee.get('talent_promo_job_profile', ''),
            employee.get('talent_promo_business_need', ''),
            employee.get('talent_promo_role_scope', ''),
            employee.get('talent_promo_readiness', ''),
        ]

        for col_num, value in enumerate(row_data, 1):
            ws.cell(row=row_num, column=col_num, value=value)

    # Auto-adjust column widths
    from openpyxl.utils import get_column_letter
    for col_idx, column in enumerate(ws.columns, 1):
        max_length = 0
        for cell in column:
            try:
                if cell.value and hasattr(cell, 'column_letter'):
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        if max_length > 0:
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[get_column_letter(col_idx)].width = adjusted_width

    # Save to BytesIO
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='talent_calibration_export.xlsx'
    )


@app.route('/export/talent/csv')
def export_talent_csv():
    """Export talent calibration data as CSV."""
    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Load tenets for name lookup
    _, tenets_map = load_tenets_config()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Add demo mode warning header if in demo mode
    if DEMO_MODE:
        writer.writerow(['*** DEMO MODE - FICTITIOUS DATA ONLY ***'])
        writer.writerow(['This export contains sample data for demonstration purposes.'])
        writer.writerow(['Do NOT use this data for any real business decisions.'])
        writer.writerow([])

    # Write header (matching Workday talent calibration format)
    writer.writerow([
        'Associate ID',
        'Worker',
        'Supervisory Organization',
        'Current Job Profile',
        'Performance: What',
        'Performance: How',
        'Overall Performance',
        'Future Talent: Growth Agility',
        'Future Talent: Change Agility',
        'Identified Future Talent',
        'Movement Readiness',
        'Proposed Talent Actions',
        'Promotions: Proposed Job Profile & Code',
        'Promotions: Business Need',
        'Promotions: Expanded Role Scope',
        'Promotions: Associate Readiness',
    ])

    # Write data rows
    for employee in team_data:
        # Build Proposed Actions with embedded tenets
        proposed_actions = employee.get('talent_proposed_actions') or ''

        # Parse and format tenets
        strengths_text = ''
        improvements_text = ''

        try:
            if employee.get('talent_tenets_strengths'):
                strength_ids = json.loads(employee['talent_tenets_strengths']) if isinstance(employee['talent_tenets_strengths'], str) else employee['talent_tenets_strengths']
                strengths = [tenets_map.get(tid, tid) for tid in strength_ids if tid in tenets_map]
                if strengths:
                    strengths_text = '; '.join(strengths)

            if employee.get('talent_tenets_improvements'):
                improvement_ids = json.loads(employee['talent_tenets_improvements']) if isinstance(employee['talent_tenets_improvements'], str) else employee['talent_tenets_improvements']
                improvements = [tenets_map.get(tid, tid) for tid in improvement_ids if tid in tenets_map]
                if improvements:
                    improvements_text = '; '.join(improvements)
        except Exception as e:
            print(f"Error parsing talent tenets: {e}")

        # Embed tenets and mentor/mentees in Proposed Actions
        metadata_markers = []
        if strengths_text:
            metadata_markers.append(f"[Strengths: {strengths_text}]")
        if improvements_text:
            metadata_markers.append(f"[Improvements: {improvements_text}]")

        # Embed mentor/mentees
        talent_mentor = employee.get('talent_mentor', '')
        talent_mentees = employee.get('talent_mentees', '')
        if talent_mentor:
            metadata_markers.append(f"[Mentor: {talent_mentor}]")
        if talent_mentees:
            metadata_markers.append(f"[Mentees: {talent_mentees}]")

        if metadata_markers:
            if proposed_actions:
                proposed_actions = proposed_actions.rstrip() + ' ' + ' '.join(metadata_markers)
            else:
                proposed_actions = ' '.join(metadata_markers)

        writer.writerow([
            employee.get('Associate ID', ''),
            employee.get('Associate', ''),
            employee.get('Supervisory Organization', ''),
            employee.get('Current Job Profile', ''),
            employee.get('talent_perf_what', ''),
            employee.get('talent_perf_how', ''),
            employee.get('talent_overall_perf', ''),
            employee.get('talent_growth_agility', ''),
            employee.get('talent_change_agility', ''),
            'Yes' if employee.get('talent_identified_future') else 'No' if employee.get('talent_identified_future') is False else '',
            employee.get('talent_movement_readiness', ''),
            proposed_actions,
            employee.get('talent_promo_job_profile', ''),
            employee.get('talent_promo_business_need', ''),
            employee.get('talent_promo_role_scope', ''),
            employee.get('talent_promo_readiness', ''),
        ])

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': 'attachment; filename=talent_calibration_export.csv'
        }
    )


@app.route('/import')
def import_page():
    """Import data page."""
    # Get filter info so the filter panel can be populated (for pre-navigation filtering)
    filter_params = get_filter_params()
    all_employees = get_all_employees()
    _, filter_info = apply_employee_filters(all_employees, filter_params)

    return render_template('import.html', demo_mode=DEMO_MODE, filter_info=filter_info)


@app.route('/history')
def history_page():
    """Period history browser page."""
    db = get_db()
    try:
        periods = db.query(Period).order_by(Period.archived_at.desc()).all()

        period_data = []
        for period in periods:
            # Get snapshots for this period
            snapshots = db.query(RatingSnapshot).filter(
                RatingSnapshot.period_id == period.id
            ).all()

            # Calculate stats
            ratings = [s.performance_rating for s in snapshots if s.performance_rating is not None]
            avg_rating = sum(ratings) / len(ratings) if ratings else None
            full_details_count = sum(1 for s in snapshots if s.has_full_details)

            period_data.append({
                'id': period.id,
                'period_id': period.id,
                'name': period.name,
                'archived_at': period.archived_at.strftime('%Y-%m-%d') if period.archived_at else 'Unknown',
                'snapshot_count': len(snapshots),
                'avg_rating': avg_rating,
                'full_details_count': full_details_count
            })

        return render_template('history.html', periods=period_data)

    finally:
        db.close()


@app.route('/api/import/analyze', methods=['POST'])
def analyze_import():
    """
    Analyze an uploaded XLSX file and return metadata.

    Returns counts of employees, whether bonus column exists,
    and checks if the period already exists (for historical imports).
    """
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

    temp_path = os.path.join(temp_dir, f'import_analyze_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
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
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    clear_existing = request.form.get('clear_existing', '').lower() == 'true'

    # Save to temp file
    temp_dir = os.path.expanduser('~/tmp')
    os.makedirs(temp_dir, exist_ok=True)

    temp_path = os.path.join(temp_dir, f'import_current_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
    try:
        file.save(temp_path)

        # Analyze the file to get metadata and spreadsheet type
        analysis = analyze_xlsx(temp_path)
        if not analysis.get('success'):
            return jsonify({'success': False, 'error': analysis.get('error', 'Analysis failed')}), 400

        spreadsheet_type = analysis.get('spreadsheet_type', 'bonus')
        workday_pool = None
        if analysis.get('metadata'):
            workday_pool = analysis['metadata'].get('total_pool')

        # Parse the file using appropriate parser based on type
        if spreadsheet_type == 'talent':
            from xlsx_utils import parse_talent_xlsx_employees
            success, employees, error = parse_talent_xlsx_employees(temp_path)
        else:
            success, employees, error = parse_xlsx_employees(temp_path)

        if not success:
            return jsonify({'success': False, 'error': error}), 400

        # Validate Overall Performance derivation for talent imports
        derivation_mismatches = []
        if spreadsheet_type == 'talent':
            from models import derive_overall_performance
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

            # Store Workday pool in BonusSettings if extracted from metadata
            if workday_pool is not None:
                settings = db.query(BonusSettings).first()
                if not settings:
                    settings = BonusSettings()
                    db.add(settings)
                settings.workday_pool = workday_pool
                settings.last_updated = datetime.now()

            imported = 0
            updated = 0

            for emp_data in employees:
                associate_id = emp_data['associate_id']

                # Check if employee exists
                existing = db.query(Employee).filter(Employee.associate_id == associate_id).first()

                if existing:
                    employee = existing
                    updated += 1
                else:
                    employee = Employee(associate_id=associate_id)
                    imported += 1

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
                        # Performance Assessment (manager-entered)
                        employee.talent_perf_what = emp_data.get('talent_perf_what')
                        employee.talent_perf_how = emp_data.get('talent_perf_how')
                        employee.talent_overall_perf = emp_data.get('talent_overall_perf')

                        # Future Talent (manager-entered)
                        employee.talent_growth_agility = emp_data.get('talent_growth_agility')
                        employee.talent_change_agility = emp_data.get('talent_change_agility')
                        employee.talent_identified_future = emp_data.get('talent_identified_future')

                        # Movement & Career (manager-entered)
                        employee.talent_movement_readiness = emp_data.get('talent_movement_readiness')

                        # Parse tenets and mentor/mentees from Proposed Actions if present
                        # Format: [Strengths: Tenet1; Tenet2] [Improvements: Tenet3] [Mentor: Name] [Mentees: A; B]
                        raw_proposed_actions = emp_data.get('talent_proposed_actions') or ''
                        tenets_config, _ = load_tenets_config()

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

                        # Promotion (manager-entered)
                        employee.talent_promo_job_profile = emp_data.get('talent_promo_job_profile')
                        employee.talent_promo_business_need = emp_data.get('talent_promo_business_need')
                        employee.talent_promo_role_scope = emp_data.get('talent_promo_role_scope')
                        employee.talent_promo_readiness = emp_data.get('talent_promo_readiness')
                else:
                    # Update bonus-specific fields
                    employee.photo = emp_data['photo']
                    employee.errors = emp_data['errors']
                    employee.current_base_pay_all_countries = emp_data['current_base_pay_all_countries']
                    employee.current_base_pay_manager_currency = emp_data['current_base_pay_manager_currency']
                    employee.currency = emp_data['currency']
                    employee.grade = emp_data['grade']
                    employee.annual_bonus_target_percent = emp_data['annual_bonus_target_percent']
                    employee.last_bonus_allocation_percent = emp_data['last_bonus_allocation_percent']
                    employee.bonus_target_local_currency = emp_data['bonus_target_local_currency']
                    employee.bonus_target_manager_currency = emp_data['bonus_target_manager_currency']
                    employee.proposed_bonus_amount = emp_data['proposed_bonus_amount']
                    employee.proposed_bonus_amount_manager_currency = emp_data['proposed_bonus_amount_manager_currency']
                    employee.proposed_percent_of_target_bonus = emp_data['proposed_percent_of_target_bonus']
                    employee.notes = emp_data['notes']
                    employee.zero_bonus_allocated = emp_data['zero_bonus_allocated']

                # Initialize manager input fields as empty if new employee
                if not existing:
                    employee.performance_rating_percent = None
                    employee.tenets_strengths = None
                    employee.tenets_improvements = None
                    employee.justification = ''
                    employee.mentor = ''
                    employee.mentees = ''
                    employee.last_updated = None
                    db.add(employee)

            db.commit()

            result = {
                'success': True,
                'imported': imported,
                'updated': updated
            }
            if clear_existing:
                result['cleared'] = cleared
            if derivation_mismatches:
                result['derivation_mismatches'] = derivation_mismatches
                result['derivation_mismatch_count'] = len(derivation_mismatches)
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

    temp_path = os.path.join(temp_dir, f'import_historical_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
    try:
        file.save(temp_path)

        # Parse the file
        success, employees, error = parse_xlsx_employees(temp_path)
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

                # Check if snapshot exists
                existing = db.query(RatingSnapshot).filter(
                    RatingSnapshot.period_id == period_id,
                    RatingSnapshot.associate_id == associate_id
                ).first()

                if existing:
                    snapshot = existing
                    updated += 1
                else:
                    snapshot = RatingSnapshot(
                        period_id=period_id,
                        associate_id=associate_id
                    )
                    imported += 1

                # Update snapshot fields
                snapshot.performance_rating = notes_data.get('performance_rating')
                snapshot.bonus_allocation = bonus_allocation
                snapshot.justification = notes_data.get('justification')
                snapshot.tenets_strengths = notes_data.get('tenets_strengths')
                snapshot.tenets_improvements = notes_data.get('tenets_improvements')
                snapshot.mentors = notes_data.get('mentors')
                snapshot.mentees = notes_data.get('mentees')

                # Snapshot employee context
                snapshot.snapshot_name = emp_data['associate']
                snapshot.snapshot_org = emp_data['supervisory_organization']
                snapshot.snapshot_job_profile = emp_data['current_job_profile']
                # Use manager currency for international, fall back to local for domestic employees
                snapshot.snapshot_bonus_target_manager_currency = emp_data.get('bonus_target_manager_currency') or emp_data.get('bonus_target_local_currency')

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


@app.route('/api/archive-period', methods=['POST'])
def archive_period():
    """
    Archive the current period's ratings to historical snapshots.

    Creates a Period record and RatingSnapshot for each rated employee.
    Clears all ratings after successful archive.
    """
    data = request.get_json()
    period_id = data.get('period_id', '').strip()
    period_name = data.get('period_name', '').strip()
    notes = data.get('notes', '').strip()

    if not period_id or not period_name:
        return jsonify({'success': False, 'error': 'Period ID and name are required'}), 400

    # Load tenets config for converting IDs to names
    _, tenets_map = load_tenets_config()

    db = get_db()
    try:
        # Check if period already exists
        existing_period = db.query(Period).filter(Period.id == period_id).first()
        if existing_period:
            return jsonify({
                'success': False,
                'error': f'Period "{period_id}" already exists. Choose a different ID or delete the existing period first.'
            }), 400

        # Create period
        period = Period(
            id=period_id,
            name=period_name,
            notes=notes if notes else None,
            archived_at=datetime.now()
        )
        db.add(period)

        # Get all employees
        employees = db.query(Employee).all()
        archived_count = 0
        skipped_unrated = 0

        for emp in employees:
            # Skip unrated employees
            if emp.performance_rating_percent is None:
                skipped_unrated += 1
                continue

            # Convert tenet IDs to human-readable names
            strengths_names = None
            improvements_names = None

            if emp.tenets_strengths:
                try:
                    strength_ids = json.loads(emp.tenets_strengths)
                    strength_names_list = [tenets_map.get(tid, tid) for tid in strength_ids]
                    strengths_names = ', '.join(strength_names_list)
                except (json.JSONDecodeError, TypeError):
                    strengths_names = emp.tenets_strengths  # Keep as-is if not valid JSON

            if emp.tenets_improvements:
                try:
                    improvement_ids = json.loads(emp.tenets_improvements)
                    improvement_names_list = [tenets_map.get(tid, tid) for tid in improvement_ids]
                    improvements_names = ', '.join(improvement_names_list)
                except (json.JSONDecodeError, TypeError):
                    improvements_names = emp.tenets_improvements  # Keep as-is if not valid JSON

            # Create snapshot
            snapshot = RatingSnapshot(
                period_id=period_id,
                associate_id=emp.associate_id,
                performance_rating=emp.performance_rating_percent,
                bonus_allocation=None,  # Could calculate if needed
                justification=emp.justification,
                tenets_strengths=strengths_names,
                tenets_improvements=improvements_names,
                mentors=emp.mentor,
                mentees=emp.mentees,
                snapshot_name=emp.associate,
                snapshot_org=emp.supervisory_organization,
                snapshot_job_profile=emp.current_job_profile,
                snapshot_bonus_target_manager_currency=emp.bonus_target_manager_currency or emp.bonus_target_local_currency,
                archived_at=datetime.now(),
                has_full_details=True
            )
            db.add(snapshot)
            archived_count += 1

        # Clear ratings from all employees
        for emp in employees:
            emp.performance_rating_percent = None
            emp.justification = ''
            emp.mentor = ''
            emp.mentees = ''
            emp.tenets_strengths = None
            emp.tenets_improvements = None
            emp.last_updated = None

        db.commit()

        return jsonify({
            'success': True,
            'archived_count': archived_count,
            'skipped_unrated': skipped_unrated,
            'period_id': period_id
        })

    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/periods')
def list_periods():
    """
    List all archived periods.

    Returns list of periods with basic stats.
    """
    db = get_db()
    try:
        periods = db.query(Period).order_by(Period.archived_at.desc()).all()

        result = []
        for period in periods:
            # Count snapshots for this period
            snapshot_count = db.query(RatingSnapshot).filter(
                RatingSnapshot.period_id == period.id
            ).count()

            result.append({
                'id': period.id,
                'name': period.name,
                'notes': period.notes,
                'archived_at': period.archived_at.isoformat() if period.archived_at else None,
                'snapshot_count': snapshot_count
            })

        return jsonify({
            'success': True,
            'periods': result
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/period/<period_id>')
def get_period_detail(period_id):
    """
    Get detailed information about a specific archived period.

    Returns period info, all snapshots, and statistics.
    """
    db = get_db()
    try:
        # Get period
        period = db.query(Period).filter(Period.id == period_id).first()
        if not period:
            return jsonify({'success': False, 'error': f'Period "{period_id}" not found'}), 404

        # Get all snapshots for this period
        snapshots = db.query(RatingSnapshot).filter(
            RatingSnapshot.period_id == period_id
        ).order_by(RatingSnapshot.performance_rating.desc().nullslast()).all()

        # Build snapshot data
        snapshot_data = []
        ratings = []
        full_details_count = 0
        partial_count = 0

        for snap in snapshots:
            snapshot_data.append({
                'associate_id': snap.associate_id,
                'snapshot_name': snap.snapshot_name,
                'snapshot_job_profile': snap.snapshot_job_profile,
                'snapshot_org': snap.snapshot_org,
                'performance_rating': snap.performance_rating,
                'bonus_allocation': snap.bonus_allocation,
                'justification': snap.justification,
                'tenets_strengths': snap.tenets_strengths,
                'tenets_improvements': snap.tenets_improvements,
                'has_full_details': snap.has_full_details
            })

            if snap.performance_rating is not None:
                ratings.append(snap.performance_rating)

            if snap.has_full_details:
                full_details_count += 1
            else:
                partial_count += 1

        # Calculate statistics
        stats = {
            'total_employees': len(snapshots),
            'avg_rating': round(sum(ratings) / len(ratings), 1) if ratings else None,
            'min_rating': min(ratings) if ratings else None,
            'max_rating': max(ratings) if ratings else None,
            'full_details': full_details_count,
            'partial': partial_count
        }

        return jsonify({
            'success': True,
            'period': {
                'id': period.id,
                'period_id': period.id,
                'name': period.name,
                'notes': period.notes,
                'archived_at': period.archived_at.isoformat() if period.archived_at else None
            },
            'snapshots': snapshot_data,
            'stats': stats
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/period-comparison/<period_id>')
def period_comparison(period_id):
    """
    Compare current ratings with a historical period.

    Returns employees with both current and historical ratings,
    showing who improved, declined, or stayed stable.
    """
    db = get_db()
    try:
        # Verify period exists
        period = db.query(Period).filter(Period.id == period_id).first()
        if not period:
            return jsonify({'success': False, 'error': f'Period "{period_id}" not found'}), 404

        # Get all current employees with ratings
        employees = db.query(Employee).all()
        current_ratings = {
            emp.associate_id: {
                'name': emp.associate,
                'rating': emp.performance_rating_percent,
                'job_profile': emp.current_job_profile,
                'org': emp.supervisory_organization
            }
            for emp in employees
        }

        # Get historical snapshots for this period
        snapshots = db.query(RatingSnapshot).filter(
            RatingSnapshot.period_id == period_id
        ).all()
        historical_ratings = {
            snap.associate_id: {
                'rating': snap.performance_rating,
                'name': snap.snapshot_name,
                'job_profile': snap.snapshot_job_profile,
                'org': snap.snapshot_org
            }
            for snap in snapshots
        }

        # Build comparison data
        comparison = []
        improved_count = 0
        declined_count = 0
        stable_count = 0
        new_employees = 0
        departed_employees = 0

        # Employees who exist in current data
        for assoc_id, current in current_ratings.items():
            historical = historical_ratings.get(assoc_id)

            if historical and historical.get('rating') is not None:
                current_rating = current.get('rating')
                historical_rating = historical.get('rating')

                if current_rating is not None:
                    change = current_rating - historical_rating
                    change_pct = round((change / historical_rating * 100), 1) if historical_rating else 0

                    if change > 5:
                        trend = 'improved'
                        improved_count += 1
                    elif change < -5:
                        trend = 'declined'
                        declined_count += 1
                    else:
                        trend = 'stable'
                        stable_count += 1

                    comparison.append({
                        'associate_id': assoc_id,
                        'name': current.get('name'),
                        'job_profile': current.get('job_profile'),
                        'current_rating': current_rating,
                        'historical_rating': historical_rating,
                        'change': round(change, 1),
                        'change_pct': change_pct,
                        'trend': trend
                    })
            else:
                # New employee (not in historical period)
                if current.get('rating') is not None:
                    new_employees += 1
                    comparison.append({
                        'associate_id': assoc_id,
                        'name': current.get('name'),
                        'job_profile': current.get('job_profile'),
                        'current_rating': current.get('rating'),
                        'historical_rating': None,
                        'change': None,
                        'change_pct': None,
                        'trend': 'new'
                    })

        # Employees who left (in historical but not current)
        for assoc_id, historical in historical_ratings.items():
            if assoc_id not in current_ratings:
                departed_employees += 1
                comparison.append({
                    'associate_id': assoc_id,
                    'name': historical.get('name'),
                    'job_profile': historical.get('job_profile'),
                    'current_rating': None,
                    'historical_rating': historical.get('rating'),
                    'change': None,
                    'change_pct': None,
                    'trend': 'departed'
                })

        # Sort by change (largest improvement first), with None values at end
        comparison.sort(key=lambda x: (
            x['change'] is None,
            -(x['change'] or 0)
        ))

        # Calculate summary stats
        current_avg = None
        historical_avg = None
        current_ratings_list = [c['current_rating'] for c in comparison if c['current_rating'] is not None and c['trend'] != 'new']
        historical_ratings_list = [c['historical_rating'] for c in comparison if c['historical_rating'] is not None and c['trend'] != 'departed']

        if current_ratings_list:
            current_avg = round(sum(current_ratings_list) / len(current_ratings_list), 1)
        if historical_ratings_list:
            historical_avg = round(sum(historical_ratings_list) / len(historical_ratings_list), 1)

        return jsonify({
            'success': True,
            'period': {
                'id': period.id,
                'name': period.name,
                'archived_at': period.archived_at.isoformat() if period.archived_at else None
            },
            'comparison': comparison,
            'summary': {
                'improved': improved_count,
                'declined': declined_count,
                'stable': stable_count,
                'new_employees': new_employees,
                'departed_employees': departed_employees,
                'current_avg': current_avg,
                'historical_avg': historical_avg,
                'avg_change': round(current_avg - historical_avg, 1) if current_avg and historical_avg else None
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


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
