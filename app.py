#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify
import csv
import os
import json
from datetime import datetime
from collections import defaultdict
from models import Employee, init_db, get_db

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


def get_employee_by_name(associate_name):
    """Get a single employee by name."""
    db = get_db()
    try:
        return db.query(Employee).filter(Employee.associate == associate_name).first()
    finally:
        db.close()


@app.route('/')
def index():
    """Main dashboard page."""
    team_data = get_all_employees()

    total_employees = len(team_data)
    rated_employees = sum(1 for emp in team_data if emp.get('performance_rating_percent'))
    unrated_employees = total_employees - rated_employees

    stats = {
        'total': total_employees,
        'rated': rated_employees,
        'unrated': unrated_employees
    }

    return render_template('index.html', team=team_data, stats=stats)


@app.route('/rate')
def rate_page():
    """Rating form page."""
    team_data = get_all_employees()
    return render_template('rate.html', team=team_data)


@app.route('/api/rate', methods=['POST'])
def rate_employee():
    """API endpoint to rate an employee and save additional manager inputs."""
    data = request.get_json()
    associate_name = data.get('associate_name')
    rating_percent = data.get('rating_percent')
    justification = data.get('justification', '')
    mentor = data.get('mentor', '')
    mentees = data.get('mentees', '')
    tenets_strengths = data.get('tenets_strengths', [])
    tenets_improvements = data.get('tenets_improvements', [])

    if not associate_name:
        return jsonify({'error': 'Missing associate name'}), 400

    # Validate rating percent
    if rating_percent is not None and rating_percent != '':
        try:
            rating_percent = float(rating_percent)
            if rating_percent < 0 or rating_percent > 200:
                return jsonify({'error': 'Rating must be between 0 and 200'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid rating value'}), 400
    else:
        rating_percent = None

    # Validate tenets data
    if tenets_strengths and not isinstance(tenets_strengths, list):
        return jsonify({'error': 'Tenets strengths must be an array'}), 400
    if tenets_improvements and not isinstance(tenets_improvements, list):
        return jsonify({'error': 'Tenets improvements must be an array'}), 400

    # Validate count (exactly 3 of each if provided, or empty)
    if tenets_strengths and len(tenets_strengths) != 3:
        return jsonify({'error': 'Must select exactly 3 strength tenets'}), 400
    if tenets_improvements and len(tenets_improvements) != 3:
        return jsonify({'error': 'Must select exactly 3 improvement tenets'}), 400

    # Validate no duplicates between lists
    if tenets_strengths and tenets_improvements:
        if set(tenets_strengths) & set(tenets_improvements):
            return jsonify({'error': 'Cannot select the same tenet as both strength and improvement'}), 400

    db = get_db()
    try:
        employee = db.query(Employee).filter(Employee.associate == associate_name).first()

        if not employee:
            return jsonify({'error': 'Employee not found'}), 404

        # Update employee fields
        employee.performance_rating_percent = rating_percent
        employee.justification = justification
        employee.mentor = mentor
        employee.mentees = mentees
        employee.tenets_strengths = json.dumps(tenets_strengths) if tenets_strengths else None
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
    tenets_file = 'tenets.json'

    # Fallback to sample file if organization-specific file doesn't exist
    if not os.path.exists(tenets_file):
        tenets_file = 'tenets-sample.json'

    try:
        with open(tenets_file, 'r') as f:
            tenets_data = json.load(f)
        return jsonify(tenets_data)
    except FileNotFoundError:
        return jsonify({'error': 'Tenets configuration file not found'}), 404
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON in tenets configuration file'}), 500


@app.route('/analytics')
def analytics():
    """Analytics and reports page."""
    team_data = get_all_employees()

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

    calibration_buckets = {
        'above_120': {'count': 0, 'suggested_min': 10, 'suggested_max': 20},
        '90_to_120': {'count': 0, 'suggested_min': 60, 'suggested_max': 80},
        '60_to_90': {'count': 0, 'suggested_min': 5, 'suggested_max': 15},
        'below_60': {'count': 0, 'suggested_min': 2, 'suggested_max': 5}
    }

    for emp in rated_employees:
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

        # Determine if within range
        within_range = suggested_min <= percentage <= suggested_max

        # Calculate delta from midpoint of suggested range
        delta = percentage - suggested_mid

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
            'delta': delta,
            'within_range': within_range,
            'status': status
        })

    # Load tenets configuration
    tenets_file = 'tenets.json' if os.path.exists('tenets.json') else 'tenets-sample.json'
    tenets_config = {}
    tenets_map = {}
    try:
        with open(tenets_file, 'r') as f:
            tenets_config = json.load(f)
            # Create a map of tenet ID to tenet data
            for tenet in tenets_config.get('tenets', []):
                tenets_map[tenet['id']] = tenet
    except (FileNotFoundError, json.JSONDecodeError):
        pass

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
                         org_tenets_summary=org_tenets_summary)


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

    team_data = get_all_employees()

    # Filter to only rated employees
    rated_employees = [emp for emp in team_data if emp.get('performance_rating_percent')]

    if not rated_employees:
        return render_template('bonus_calculation.html',
                             team=[],
                             params=params,
                             total_pool=0,
                             total_allocated=0,
                             has_data=False,
                             missing_bonus_data=False)

    # Calculate total bonus pool (sum of all bonus targets in USD)
    total_pool = 0
    for emp in rated_employees:
        # Prefer USD version if it exists (for non-US employees), otherwise use local currency (already in USD for US employees)
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

    for emp in rated_employees:
        try:
            rating = float(emp.get('performance_rating_percent', 100))

            # CRITICAL: Fallback logic for USD vs International employees
            # USD employees: Have values ONLY in "Local Currency" column (which is USD)
            # International: Have values in BOTH "Local Currency" AND "USD" columns
            # Always prefer USD column if present, fallback to local (works for both cases)
            # See tests/test_workday_format.py for detailed documentation
            bonus_target_usd = float((emp.get('Bonus Target - Local Currency (USD)') or emp.get('Bonus Target - Local Currency')) or 0)
            base_pay_usd = float((emp.get('Current Base Pay All Countries (USD)') or emp.get('Current Base Pay All Countries')) or 0)
        except (ValueError, TypeError):
            # Skip employees with invalid data
            continue

        # Track employees without bonus target
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

    # Normalization: Calculate value per share
    value_per_share = total_pool / total_raw_shares if total_raw_shares > 0 else 0

    # Calculate final bonuses
    total_allocated = 0
    for result in bonus_results:
        result['final_bonus'] = result['raw_share'] * value_per_share
        result['bonus_percent_of_target'] = (result['final_bonus'] / result['bonus_target_usd'] * 100) if result['bonus_target_usd'] > 0 else 0
        total_allocated += result['final_bonus']

    # Check if we have any valid bonus data
    if not bonus_results or total_pool == 0:
        return render_template('bonus_calculation.html',
                             team=[],
                             params=params,
                             total_pool=0,
                             total_allocated=0,
                             has_data=False,
                             missing_bonus_data=True)

    # Sort by final bonus descending
    bonus_results.sort(key=lambda x: x['final_bonus'], reverse=True)

    return render_template('bonus_calculation.html',
                         team=bonus_results,
                         params=params,
                         total_pool=total_pool,
                         total_allocated=total_allocated,
                         value_per_share=value_per_share,
                         has_data=True,
                         missing_bonus_data=False,
                         total_rated=len(rated_employees),
                         employees_without_bonus_target=employees_without_bonus_target)


@app.route('/export')
def export():
    """Export ratings to timestamped CSV file."""
    team_data = get_all_employees()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_file = f"ratings_export_{timestamp}.csv"

    if not team_data:
        return jsonify({'error': 'No data to export'}), 400

    fieldnames = list(team_data[0].keys())

    with open(export_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(team_data)

    return jsonify({
        'success': True,
        'message': f'Ratings exported to {export_file}',
        'filename': export_file
    })


if __name__ == '__main__':
    print("\n" + "="*60)
    print("Quarterly Performance Rating System")
    print("="*60)
    print(f"Database: {os.getenv('DATABASE_URL', 'sqlite:///ratings.db')}")
    print(f"Starting web server at http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("="*60 + "\n")

    app.run(debug=True, host='127.0.0.1', port=5000)
