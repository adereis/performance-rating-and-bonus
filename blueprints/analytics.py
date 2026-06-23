"""Analytics blueprint: the /analytics dashboard (read-only)."""
from flask import Blueprint, render_template, request

from services import db_helpers
from services.db_helpers import (
    get_filter_params, get_all_employees, apply_employee_filters,
    get_bonus_settings,
)
from services.bonus import (
    calculate_bonus_for_employees, calculate_calibration_for_employees,
    calculate_mentorship_stats,
)
from services.employee_utils import is_employee_calibrated

analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route('/analytics')
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

