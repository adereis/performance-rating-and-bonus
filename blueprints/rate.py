"""Rate blueprint: the /rate page, rating API, bonus-settings, tenets, and
per-employee detail/history endpoints.

Moved verbatim from app.py (docs/REFACTOR_APP_SPLIT.md, Phase 6). get_db is
resolved via the models module and load_tenets_config via the db_helpers
module so test fixtures patching them are honored.
"""
import json
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify

import models
from models import Employee, BonusSettings, Period, RatingSnapshot

from services import db_helpers
from services.db_helpers import (
    get_filter_params, get_all_employees, apply_employee_filters,
    get_bonus_settings, update_bonus_settings, get_employee_by_id,
)
from services.employee_utils import normalize_mentor_field

rate_bp = Blueprint('rate', __name__)


@rate_bp.route('/rate')
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


@rate_bp.route('/api/rate', methods=['POST'])
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

    db = models.get_db()
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


@rate_bp.route('/api/tenets', methods=['GET'])
def get_tenets():
    """API endpoint to serve tenets configuration."""
    tenets_config, _ = db_helpers.load_tenets_config()
    if tenets_config is None:
        return jsonify({
            'error': 'No tenets.json found. Copy samples/tenets-sample.json '
                     'to tenets.json and customize it for your organization.'
        }), 404
    return jsonify(tenets_config)


@rate_bp.route('/api/bonus-settings', methods=['GET', 'POST'])
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


@rate_bp.route('/api/bonus-settings/verify-pool', methods=['POST'])
def verify_pool_api():
    """Mark the calculated bonus pool as verified by the user."""
    try:
        db = models.get_db()
        settings = db.query(BonusSettings).first()
        if not settings:
            return jsonify({'success': False, 'error': 'No bonus settings found'}), 404

        settings.pool_verified = True
        db.commit()
        return jsonify({'success': True, 'message': 'Pool verified'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@rate_bp.route('/api/employee/<associate_id>', methods=['GET'])
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


@rate_bp.route('/api/employee/<associate_id>/history', methods=['GET'])
def get_employee_history(associate_id):
    """API endpoint to get historical rating snapshots for an employee."""
    db = models.get_db()
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

