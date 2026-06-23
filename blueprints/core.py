"""Core blueprint: dashboard, health check, and demo session routes.

Routes: / (index), /health, /demo/<type>, /api/demo/reset.

Moved verbatim from app.py (docs/REFACTOR_APP_SPLIT.md, Phase 7). The demo
flag is read as demo_mode.DEMO_MODE and get_db via the models module so test
fixtures patching them are honored; no module imports `app`.
"""
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import text

import demo_mode
from demo_mode import get_session_id, initialize_session_from_template
import models
from models import Period, RatingSnapshot

from services.db_helpers import (
    get_filter_params, get_all_employees, apply_employee_filters,
)
from services.employee_utils import is_employee_rated, is_employee_calibrated

core_bp = Blueprint('core', __name__)


@core_bp.route('/health')
def health_check():
    """Health check endpoint for load balancers and monitoring.

    In demo mode, checks template availability without creating a session.
    In production mode, checks actual database connectivity.
    """
    status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'demo_mode': demo_mode.DEMO_MODE
    }

    if demo_mode.DEMO_MODE:
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
            db = models.get_db()
            db.execute(text('SELECT 1'))
            db.close()
            status['database'] = 'connected'
        except Exception as e:
            status['database'] = 'error'
            status['database_error'] = str(e)
            return jsonify(status), 503

    return jsonify(status)


@core_bp.route('/demo/<demo_type>')
def demo_init(demo_type):
    """Initialize demo with specified dataset type."""
    from flask import redirect, url_for

    if not demo_mode.DEMO_MODE:
        return redirect(url_for('core.index'))

    if demo_type not in ('small', 'large'):
        demo_type = 'small'

    session_id = get_session_id()
    success = initialize_session_from_template(session_id, demo_type)

    if success:
        return redirect(url_for('rate.rate_page'))
    else:
        return redirect(url_for('core.index'))


@core_bp.route('/api/demo/reset', methods=['POST'])
def demo_reset():
    """Reset demo data to a fresh template."""
    if not demo_mode.DEMO_MODE:
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


@core_bp.route('/')
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
        db = models.get_db()
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
                         demo_mode=demo_mode.DEMO_MODE, historical_info=historical_info,
                         alignment_data=alignment_data, alignment_stats=alignment_stats,
                         calibrated_count=calibrated_count, promotion_ready=promotion_ready)

