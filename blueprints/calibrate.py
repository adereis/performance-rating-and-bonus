"""Calibrate blueprint: the /calibrate page and talent-calibration API.

Moved verbatim from app.py (docs/REFACTOR_APP_SPLIT.md, Phase 6). get_db is
resolved via the models module so test fixtures patching it are honored.
"""
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify

import models
from models import Employee

from services.db_helpers import (
    get_filter_params, get_all_employees, apply_employee_filters,
)
from services.employee_utils import is_employee_calibrated, _has_tenets, normalize_mentor_field

calibrate_bp = Blueprint('calibrate', __name__)


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


@calibrate_bp.route('/calibrate')
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


@calibrate_bp.route('/api/calibrate', methods=['POST'])
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

    db = models.get_db()
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


@calibrate_bp.route('/api/calibrate/status', methods=['GET'])
def calibrate_status():
    """API endpoint to get talent calibration progress."""
    db = models.get_db()
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

