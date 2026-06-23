"""Bonus blueprint: the /bonus-calculation page (read-only)."""
from flask import Blueprint, render_template, request

from services.db_helpers import (
    get_filter_params, get_all_employees, apply_employee_filters,
    get_bonus_settings,
)
from services.bonus import calculate_bonus_for_employees

bonus_bp = Blueprint('bonus', __name__)


@bonus_bp.route('/bonus-calculation')
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

