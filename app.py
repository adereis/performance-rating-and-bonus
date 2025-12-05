#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify, send_file, make_response
import os
import json
import csv
import io
from datetime import datetime
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from models import Employee, BonusSettings, Period, RatingSnapshot, init_db, get_db
from xlsx_utils import analyze_xlsx, parse_xlsx_employees
from notes_parser import parse_notes_field
import tempfile

app = Flask(__name__)

# Initialize database on startup
init_db()


def get_all_employees():
    """Get all employees from database."""
    db = get_db()
    try:
        employees = db.query(Employee).all()
        return [emp.to_dict() for emp in employees]
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
            settings = BonusSettings(budget_override_usd=0.0, last_updated=datetime.now())
            db.add(settings)
            db.commit()
            db.refresh(settings)
        return settings
    finally:
        db.close()


def update_bonus_settings(budget_override_usd):
    """Update bonus settings in database."""
    db = get_db()
    try:
        settings = db.query(BonusSettings).first()
        if not settings:
            settings = BonusSettings()
            db.add(settings)

        settings.budget_override_usd = budget_override_usd
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
    Load tenets configuration from file.
    Prefers tenets.json, falls back to tenets-sample.json.

    Returns:
        tuple: (tenets_config dict, tenets_map dict mapping id->name)
               Returns (None, {}) if no config found
    """
    tenets_file = 'tenets.json' if os.path.exists('tenets.json') else 'samples/tenets-sample.json'

    if not os.path.exists(tenets_file):
        return None, {}

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

    A manager is someone whose name appears in other employees'
    "Supervisory Organization" field.

    Args:
        employee: Employee dict to check
        all_employees: List of all employee dicts

    Returns:
        bool: True if employee has direct reports
    """
    employee_name = employee.get('Associate', '')
    if not employee_name:
        return False

    # Check if this employee's name appears in any other employee's supervisory org
    for other_emp in all_employees:
        if other_emp.get('Associate ID') == employee.get('Associate ID'):
            continue  # Skip self

        supervisory_org = other_emp.get('Supervisory Organization', '')
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
    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    total_employees = len(team_data)
    rated_employees = sum(1 for emp in team_data if emp.get('performance_rating_percent'))
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

    return render_template('index.html', team=team_data, stats=stats, filter_info=filter_info)


@app.route('/rate')
def rate_page():
    """Rating form page."""
    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    return render_template('rate.html', team=team_data, filter_info=filter_info)


@app.route('/api/rate', methods=['POST'])
def rate_employee():
    """API endpoint to rate an employee and save additional manager inputs.

    Only updates fields that are explicitly provided in the request.
    This allows partial updates (e.g., compact view only sends rating).
    """
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
        budget_override_usd = data.get('budget_override_usd')

        if budget_override_usd is None:
            return jsonify({'error': 'Missing budget_override_usd'}), 400

        try:
            budget_override_usd = float(budget_override_usd)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid budget_override_usd value'}), 400

        try:
            update_bonus_settings(budget_override_usd)
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
                if rating > 120:
                    calibration_buckets['above_120']['count'] += 1
                elif rating >= 90:
                    calibration_buckets['90_to_120']['count'] += 1
                elif rating >= 60:
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

        # Count strengths
        if emp.get('tenets_strengths'):
            try:
                strengths = json.loads(emp['tenets_strengths'])
                for tenet_id in strengths:
                    strength_counts[tenet_id] += 1
                    has_tenets = True
            except json.JSONDecodeError:
                pass

        # Count improvements
        if emp.get('tenets_improvements'):
            try:
                improvements = json.loads(emp['tenets_improvements'])
                for tenet_id in improvements:
                    improvement_counts[tenet_id] += 1
                    has_tenets = True
            except json.JSONDecodeError:
                pass

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
                         filter_info=filter_info)


def calculate_bonus_for_employees(employees, params, budget_override_usd=0.0):
    """
    Calculate bonuses for a given set of employees.
    Returns dict with results, normalization factor, and metadata.

    Args:
        employees: List of employee dicts
        params: Dict with upside_exponent and downside_exponent
        budget_override_usd: Additional budget (can be negative) to add to total pool
    """
    # Calculate total bonus pool (sum of all bonus targets in USD)
    total_pool = 0
    for emp in employees:
        bonus_target_usd = emp.get('Bonus Target - Local Currency (USD)') or emp.get('Bonus Target - Local Currency')
        if bonus_target_usd:
            try:
                total_pool += float(bonus_target_usd)
            except (ValueError, TypeError):
                pass

    # Calculate bonuses
    bonus_results = []
    total_raw_shares = 0
    employees_without_bonus_target = 0

    for emp in employees:
        try:
            rating = float(emp.get('performance_rating_percent', 100))
            bonus_target_usd = float((emp.get('Bonus Target - Local Currency (USD)') or emp.get('Bonus Target - Local Currency')) or 0)
            base_pay_usd = float((emp.get('Current Base Pay All Countries (USD)') or emp.get('Current Base Pay All Countries')) or 0)
        except (ValueError, TypeError):
            continue

        if bonus_target_usd <= 0:
            employees_without_bonus_target += 1
            continue

        # Calculate Performance Multiplier (Split Curve)
        if rating < 100:
            perf_multiplier = (rating / 100) ** params['downside_exponent']
        else:
            perf_multiplier = (rating / 100) ** params['upside_exponent']

        # Calculate Raw Share
        raw_share = bonus_target_usd * perf_multiplier
        total_raw_shares += raw_share

        bonus_results.append({
            'employee': emp,
            'rating': rating,
            'bonus_target_usd': bonus_target_usd,
            'base_pay_usd': base_pay_usd,
            'perf_multiplier': perf_multiplier,
            'raw_share': raw_share
        })

    # Apply budget override to create adjusted pool
    adjusted_pool = total_pool + budget_override_usd

    # Normalization: Calculate value per share using adjusted pool
    value_per_share = adjusted_pool / total_raw_shares if total_raw_shares > 0 else 0

    # Calculate final bonuses
    total_allocated = 0
    for result in bonus_results:
        result['final_bonus'] = result['raw_share'] * value_per_share
        result['bonus_percent_of_target'] = (result['final_bonus'] / result['bonus_target_usd'] * 100) if result['bonus_target_usd'] > 0 else 0
        total_allocated += result['final_bonus']

    # Create lookup by Associate ID for easy access
    results_by_id = {r['employee']['Associate ID']: r for r in bonus_results}

    return {
        'results': bonus_results,
        'results_by_id': results_by_id,
        'base_pool': total_pool,
        'budget_override_usd': budget_override_usd,
        'total_pool': adjusted_pool,
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

    # Get budget override from database
    settings = get_bonus_settings()
    budget_override_usd = settings.budget_override_usd

    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Filter to only rated employees
    rated_employees = [emp for emp in team_data if emp.get('performance_rating_percent')]

    if not rated_employees:
        return render_template('bonus_calculation.html',
                             team=[],
                             params=params,
                             base_pool=0,
                             budget_override_usd=budget_override_usd,
                             total_pool=0,
                             total_allocated=0,
                             value_per_share=1.0,
                             has_data=False,
                             missing_bonus_data=False,
                             is_multi_team=False)

    # Detect multi-team scenario by checking unique supervisory organizations
    unique_orgs = set()
    for emp in rated_employees:
        org = emp.get('Supervisory Organization')
        if org:
            unique_orgs.add(org)

    is_multi_team = len(unique_orgs) > 1

    # Calculate organization-level bonuses (always) with budget override
    org_level_calc = calculate_bonus_for_employees(rated_employees, params, budget_override_usd)

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
                             budget_override_usd=budget_override_usd,
                             total_pool=0,
                             total_allocated=0,
                             value_per_share=1.0,
                             has_data=False,
                             missing_bonus_data=True,
                             is_multi_team=False)

    # Sort by final bonus descending
    org_level_calc['results'].sort(key=lambda x: x['final_bonus'], reverse=True)

    return render_template('bonus_calculation.html',
                         team=org_level_calc['results'],
                         params=params,
                         base_pool=org_level_calc['base_pool'],
                         budget_override_usd=org_level_calc['budget_override_usd'],
                         total_pool=org_level_calc['total_pool'],
                         total_allocated=org_level_calc['total_allocated'],
                         value_per_share=org_level_calc['value_per_share'],
                         has_data=True,
                         missing_bonus_data=False,
                         total_rated=len(rated_employees),
                         employees_without_bonus_target=org_level_calc['employees_without_bonus_target'],
                         is_multi_team=is_multi_team,
                         team_comparisons=team_comparisons,
                         teams_data=teams_data,
                         filter_info=filter_info)


@app.route('/export')
def export_page():
    """Export page for Workday bonus allocation."""
    # Get filter params from URL
    filter_params = get_filter_params()

    # Get all employees
    all_employees = get_all_employees()

    # Apply filters
    team_data, filter_info = apply_employee_filters(all_employees, filter_params)

    # Filter to rated employees only
    rated_employees = [emp for emp in team_data if emp.get('performance_rating_percent')]

    if not rated_employees:
        return render_template('export.html',
                             export_data=[],
                             has_data=False,
                             filter_info=filter_info)

    # Get bonus calculation settings
    params = {
        'upside_exponent': float(request.args.get('upside_exponent', 1.35)),
        'downside_exponent': float(request.args.get('downside_exponent', 1.9))
    }

    # Get budget override
    settings = get_bonus_settings()
    budget_override_usd = settings.budget_override_usd if settings else 0.0

    # Calculate bonuses for all rated employees
    bonus_calc = calculate_bonus_for_employees(rated_employees, params, budget_override_usd)

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

    return render_template('export.html',
                         export_data=export_data,
                         has_data=True,
                         total_employees=len(export_data),
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

    # Write header (matching Excel export)
    writer.writerow([
        'Associate ID',
        'Associate',
        'Supervisory Organization',
        'Current Job Profile',
        'Photo',
        'Errors',
        'Current Base Pay - All Countries',
        'Current Base Pay - All Countries (USD)',
        'Currency',
        'Grade',
        'Annual Bonus Target %',
        'Last Bonus Allocation %',
        'Bonus Target - Local Currency',
        'Bonus Target - Local Currency (USD)',
        'Proposed Bonus Amount',
        'Proposed Bonus Amount (USD)',
        'Proposed % of Target Bonus',
        'Notes',
        'Zero Bonus Allocated',
        'Performance Rating %',
        'Justification',
        'Mentor',
        'Mentees',
        'Tenets - Strengths',
        'Tenets - Improvements',
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
            employee.get('Current Base Pay - All Countries', ''),
            employee.get('Current Base Pay - All Countries (USD)', ''),
            employee.get('Currency', ''),
            employee.get('Grade', ''),
            employee.get('Annual Bonus Target %', ''),
            employee.get('Last Bonus Allocation %', ''),
            employee.get('Bonus Target - Local Currency', ''),
            employee.get('Bonus Target - Local Currency (USD)', ''),
            employee.get('Proposed Bonus Amount', ''),
            employee.get('Proposed Bonus Amount (USD)', ''),
            employee.get('Proposed % of Target Bonus', ''),
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

    # Define headers (matching import format plus our custom fields)
    headers = [
        'Associate ID',
        'Associate',
        'Supervisory Organization',
        'Current Job Profile',
        'Photo',
        'Errors',
        'Current Base Pay - All Countries',
        'Current Base Pay - All Countries (USD)',
        'Currency',
        'Grade',
        'Annual Bonus Target %',
        'Last Bonus Allocation %',
        'Bonus Target - Local Currency',
        'Bonus Target - Local Currency (USD)',
        'Proposed Bonus Amount',
        'Proposed Bonus Amount (USD)',
        'Proposed % of Target Bonus',
        'Notes',
        'Zero Bonus Allocated',
        # Our custom fields
        'Performance Rating %',
        'Justification',
        'Mentor',
        'Mentees',
        'Tenets - Strengths',
        'Tenets - Improvements',
        'Description'  # Combined description field
    ]

    # Style header row
    header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Load tenets for description
    _, tenets_map = load_tenets_config()

    # Write data rows
    for row_num, employee in enumerate(team_data, 2):
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
            employee.get('Current Base Pay - All Countries', ''),
            employee.get('Current Base Pay - All Countries (USD)', ''),
            employee.get('Currency', ''),
            employee.get('Grade', ''),
            employee.get('Annual Bonus Target %', ''),
            employee.get('Last Bonus Allocation %', ''),
            employee.get('Bonus Target - Local Currency', ''),
            employee.get('Bonus Target - Local Currency (USD)', ''),
            employee.get('Proposed Bonus Amount', ''),
            employee.get('Proposed Bonus Amount (USD)', ''),
            employee.get('Proposed % of Target Bonus', ''),
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

    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)  # Cap at 50
        ws.column_dimensions[column_letter].width = adjusted_width

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


@app.route('/import')
def import_page():
    """Import data page."""
    return render_template('import.html')


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
            'has_bonus_column': analysis['has_bonus_column'],
            'notes_count': analysis['notes_count'],
            'partial_count': analysis['partial_count'],
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

        # Parse the file
        success, employees, error = parse_xlsx_employees(temp_path)
        if not success:
            return jsonify({'success': False, 'error': error}), 400

        db = get_db()
        try:
            # Clear existing employees if requested
            cleared = 0
            if clear_existing:
                cleared = db.query(Employee).count()
                db.query(Employee).delete()

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

                # Update Workday fields
                employee.associate = emp_data['associate']
                employee.supervisory_organization = emp_data['supervisory_organization']
                employee.current_job_profile = emp_data['current_job_profile']
                employee.photo = emp_data['photo']
                employee.errors = emp_data['errors']
                employee.current_base_pay_all_countries = emp_data['current_base_pay_all_countries']
                employee.current_base_pay_all_countries_usd = emp_data['current_base_pay_all_countries_usd']
                employee.currency = emp_data['currency']
                employee.grade = emp_data['grade']
                employee.annual_bonus_target_percent = emp_data['annual_bonus_target_percent']
                employee.last_bonus_allocation_percent = emp_data['last_bonus_allocation_percent']
                employee.bonus_target_local_currency = emp_data['bonus_target_local_currency']
                employee.bonus_target_local_currency_usd = emp_data['bonus_target_local_currency_usd']
                employee.proposed_bonus_amount = emp_data['proposed_bonus_amount']
                employee.proposed_bonus_amount_usd = emp_data['proposed_bonus_amount_usd']
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
                snapshot.snapshot_bonus_target_usd = emp_data.get('bonus_target_local_currency_usd')

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
                snapshot_bonus_target_usd=emp.bonus_target_local_currency_usd or emp.bonus_target_local_currency,
                archived_at=datetime.now(),
                has_full_details=True
            )
            db.add(snapshot)
            archived_count += 1

        # Clear ratings from all employees
        for emp in employees:
            emp.performance_rating_percent = None
            emp.justification = None
            emp.mentor = None
            emp.mentees = None
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
    print(f"Database: {os.getenv('DATABASE_URL', 'sqlite:///ratings.db')}")
    print(f"Starting web server at http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("="*60 + "\n")

    app.run(debug=True, host='127.0.0.1', port=5000)
