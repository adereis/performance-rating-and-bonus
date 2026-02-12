"""Analytics sub-computations extracted from the analytics() route.

Pure computation functions that operate on employee dicts (from to_dict()).
No Flask or database dependencies -- callables are passed in where needed
to avoid circular imports.
"""
import json
import re
from collections import defaultdict

from services.employee_utils import (
    has_direct_reports,
    parse_tenure_to_months,
    get_tenure_band,
    _parse_mentee_set,
    is_employee_calibrated,
)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def format_months_display(months):
    """Format a month count as a human-readable string (e.g. '2y 3m')."""
    if months is None:
        return 'N/A'
    years = int(months // 12)
    remaining_months = int(months % 12)
    if years > 0 and remaining_months > 0:
        return f"{years}y {remaining_months}m"
    elif years > 0:
        return f"{years} years"
    else:
        return f"{remaining_months} months"


def categorize_job_level(emp, all_emps):
    """Categorize employee into job level for tenet analysis.

    Categories: Manager (has direct reports), Senior IC
    (Senior/Principal/Staff/Lead), Others.
    """
    if has_direct_reports(emp, all_emps):
        return 'Manager'
    job_title = (emp.get('Current Job Profile') or '').lower()
    senior_keywords = ['senior', 'principal', 'staff', 'lead']
    if any(keyword in job_title for keyword in senior_keywords):
        return 'Senior IC'
    return 'Others'


# ---------------------------------------------------------------------------
# Analytics functions
# ---------------------------------------------------------------------------

def calculate_rating_distribution(team_data):
    """Calculate rating buckets, department averages, job averages.

    Returns:
        tuple: (rating_buckets, dept_averages, job_averages, sorted_team,
                special_case_count, rated_employees, total_rated,
                has_bonus_data, job_profile_distribution)
    """
    rating_buckets = {
        '0-50%': 0,
        '51-80%': 0,
        '81-100%': 0,
        '101-130%': 0,
        '131-200%': 0
    }

    department_ratings = defaultdict(list)
    job_ratings = defaultdict(list)

    # Track special case employees for reporting
    special_case_count = 0

    for emp in team_data:
        # Skip special case employees (bonus override) from rating analytics
        # These employees have pro-rata bonuses (leave, etc.) and shouldn't
        # be counted in performance distribution charts
        if emp.get('bonus_override_percent') is not None:
            special_case_count += 1
            continue

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

    # Only count rated employees for calibration (exclude special cases with bonus override)
    rated_employees = [
        emp for emp in team_data
        if emp.get('performance_rating_percent') and emp.get('bonus_override_percent') is None
    ]
    total_rated = len(rated_employees)

    # has_bonus_data: true only if rated employees have actual bonus target data from Workday
    rated_with_bonus_targets = [
        emp for emp in rated_employees
        if emp.get('Bonus Target Manager Currency') or emp.get('Bonus Target - Local Currency')
    ]
    has_bonus_data = len(rated_with_bonus_targets) > 0

    # Job profile distribution for Team Overview
    job_profile_counts = {}
    for emp in team_data:
        job = emp.get('Current Job Profile', 'Unknown') or 'Unknown'
        job_profile_counts[job] = job_profile_counts.get(job, 0) + 1

    # Sort by count descending for display
    job_profile_distribution = sorted(
        [{'job': job, 'count': count} for job, count in job_profile_counts.items()],
        key=lambda x: x['count'],
        reverse=True
    )

    # Seniority composition for Team Overview
    seniority_counts = {'Manager': 0, 'Senior IC': 0, 'Others': 0}
    seniority_roles = {'Manager': {}, 'Senior IC': {}, 'Others': {}}
    for emp in team_data:
        level = categorize_job_level(emp, team_data)
        seniority_counts[level] += 1
        job = emp.get('Current Job Profile', 'Unknown') or 'Unknown'
        seniority_roles[level][job] = seniority_roles[level].get(job, 0) + 1

    seniority_composition = []
    for level in ['Manager', 'Senior IC', 'Others']:
        count = seniority_counts[level]
        if count == 0:
            continue
        roles = sorted(
            [{'job': j, 'count': c} for j, c in seniority_roles[level].items()],
            key=lambda x: x['count'],
            reverse=True
        )
        seniority_composition.append({
            'level': level,
            'count': count,
            'roles': roles
        })

    return (
        rating_buckets, dept_averages, job_averages, sorted_team,
        special_case_count, rated_employees, total_rated,
        has_bonus_data, job_profile_distribution, seniority_composition,
    )


def calculate_tenets_analytics(team_data, tenets_map):
    """Calculate tenet distributions: overall, per-org, per-job-level.

    Args:
        team_data: List of employee dicts.
        tenets_map: Dict mapping tenet ID to tenet info dict.

    Returns:
        tuple: (tenets_summary, employees_with_tenets,
                org_tenets_summary, job_level_tenets_summary)
    """
    # ---- Overall tenet counts ----
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

    # ---- Per-Organization tenet counts ----
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

    # ---- Per-Job-Level tenet counts ----
    job_level_tenets = {}
    for emp in team_data:
        level = categorize_job_level(emp, team_data)
        if level not in job_level_tenets:
            job_level_tenets[level] = {
                'strength_counts': defaultdict(float),
                'improvement_counts': defaultdict(float),
                'employees_with_tenets': 0
            }

        has_tenets = False

        # Count strengths per job level (combine bonus + talent cycle fields, deduplicate)
        all_strengths = set()
        for field in ['tenets_strengths', 'talent_tenets_strengths']:
            if emp.get(field):
                try:
                    strengths = json.loads(emp[field])
                    all_strengths.update(strengths)
                except json.JSONDecodeError:
                    pass
        if all_strengths:
            weight = 3.0 / len(all_strengths)
            for tenet_id in all_strengths:
                job_level_tenets[level]['strength_counts'][tenet_id] += weight
            has_tenets = True

        # Count improvements per job level (combine bonus + talent cycle fields, deduplicate)
        all_improvements = set()
        for field in ['tenets_improvements', 'talent_tenets_improvements']:
            if emp.get(field):
                try:
                    improvements = json.loads(emp[field])
                    all_improvements.update(improvements)
                except json.JSONDecodeError:
                    pass
        if all_improvements:
            weight = 3.0 / len(all_improvements)
            for tenet_id in all_improvements:
                job_level_tenets[level]['improvement_counts'][tenet_id] += weight
            has_tenets = True

        if has_tenets:
            job_level_tenets[level]['employees_with_tenets'] += 1

    # Build per-job-level tenets summary
    job_level_tenets_summary = {}
    # Define display order for job levels
    job_level_order = ['Manager', 'Senior IC', 'Others']
    for level in job_level_order:
        if level not in job_level_tenets:
            continue
        data = job_level_tenets[level]
        level_all_tenet_ids = set(data['strength_counts'].keys()) | set(data['improvement_counts'].keys())
        level_summary = []

        for tenet_id in level_all_tenet_ids:
            tenet_info = tenets_map.get(tenet_id, {})
            level_summary.append({
                'id': tenet_id,
                'name': tenet_info.get('name', tenet_id),
                'category': tenet_info.get('category', 'Unknown'),
                'strength_count': data['strength_counts'].get(tenet_id, 0),
                'improvement_count': data['improvement_counts'].get(tenet_id, 0),
                'total_mentions': data['strength_counts'].get(tenet_id, 0) + data['improvement_counts'].get(tenet_id, 0)
            })

        # Sort by net score (strengths - improvements) descending
        level_summary.sort(key=lambda x: x['strength_count'] - x['improvement_count'], reverse=True)

        job_level_tenets_summary[level] = {
            'tenets': level_summary,
            'employees_with_tenets': data['employees_with_tenets']
        }

    return (tenets_summary, employees_with_tenets,
            org_tenets_summary, job_level_tenets_summary)


def calculate_talent_calibration_analytics(team_data):
    """Calculate talent calibration distributions (Spec 7.3).

    Returns:
        dict or None: talent_calibration dict with performance_data,
        future_talent, movement_data, and talent_matrix; or None if
        no talent data exists.
    """
    employees_with_talent = [emp for emp in team_data if emp.get('talent_overall_perf')]

    if not employees_with_talent:
        return None

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
        'Ready for lateral move': 0,
        'Ready to be promoted outside of current role': 0,
        'Not well placed': 0,
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

    return talent_calibration


def detect_inconsistencies(team_data, tenets_map, rated_employees,
                           has_bonus_data, all_employees,
                           get_bonus_settings_fn, calculate_bonus_fn):
    """Detect inconsistencies between performance ratings and talent data.

    Args:
        team_data: List of employee dicts (filtered).
        tenets_map: Dict mapping tenet ID to tenet info dict.
        rated_employees: List of rated employee dicts (no overrides).
        has_bonus_data: Whether rated employees have bonus target data.
        all_employees: List of *all* employee dicts (unfiltered).
        get_bonus_settings_fn: Callable returning BonusSettings ORM object.
        calculate_bonus_fn: Callable ``calculate_bonus_for_employees``.

    Returns:
        tuple: (inconsistencies dict, total_inconsistencies int)
    """
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
        'tenet_mismatch': [],           # Tenets differ between bonus and talent cycles
        # Tenure-based inconsistencies
        'new_hire_low_rating': [],      # < 6 months total tenure but rated Low/Evolving
        'promotion_ready_short_tenure': [],  # Ready Now but < 2 years in role
        'new_hire_mentoring': [],     # < 1 year total tenure but mentoring others
        # Prior cycle bonus changes (populated after bonus calculation)
        'bonus_increase_from_prior': [],   # Calculated bonus >15pp higher than prior cycle
        'bonus_decrease_from_prior': []    # Calculated bonus >15pp lower than prior cycle
    }

    for emp in team_data:
        # Skip special case employees (bonus override) from inconsistency detection
        # These employees have pro-rata bonuses and shouldn't be flagged for rating mismatches
        if emp.get('bonus_override_percent') is not None:
            continue

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

        # Tenure-based inconsistency checks
        los_months = parse_tenure_to_months(emp.get('length_of_service'))
        tijp_months = parse_tenure_to_months(emp.get('time_in_job_profile'))

        tenure_emp_info = {
            'name': emp.get('Associate', 'Unknown'),
            'id': emp.get('Associate ID', ''),
            'job': emp.get('Current Job Profile', ''),
            'rating': rating,
            'talent': talent_perf,
            'movement': movement,
            'length_of_service': emp.get('length_of_service') or 'N/A',
            'time_in_job_profile': emp.get('time_in_job_profile') or 'N/A'
        }

        # New hire rated Low: < 6 months total tenure but rated Low/Evolving
        if los_months is not None and los_months < 6:
            if talent_perf in ['Low Performer', 'Evolving Performer']:
                inconsistencies['new_hire_low_rating'].append(tenure_emp_info)

        # Ready Now but < 2 years in role
        if 'Ready Now' in movement and tijp_months is not None and tijp_months < 24:
            inconsistencies['promotion_ready_short_tenure'].append(tenure_emp_info)

        # New hire (< 1 year total tenure) but mentoring others
        if los_months is not None and los_months < 12:
            mentees = (emp.get('mentees') or emp.get('talent_mentees') or '').strip()
            if mentees:
                tenure_emp_info['mentees'] = mentees
                inconsistencies['new_hire_mentoring'].append(tenure_emp_info)

        # Mentoring mismatch between cycles
        # Only check if employee is both rated AND calibrated (otherwise empty fields are expected)
        if rating and talent_perf:
            bonus_mentor = (emp.get('mentor') or '').strip()
            bonus_mentees = (emp.get('mentees') or '').strip()
            talent_mentor = (emp.get('talent_mentor') or '').strip()
            talent_mentees = (emp.get('talent_mentees') or '').strip()

            # Check if mentoring data CONFLICTS between cycles (both have values but differ)
            # Don't flag changes from/to empty - that's just progressive data entry, not a mismatch
            mentor_differs = bonus_mentor and talent_mentor and bonus_mentor.lower() != talent_mentor.lower()
            # Compare mentee sets (delimiter-agnostic) to avoid false positives from ";" vs ","
            mentees_differs = bonus_mentees and talent_mentees and _parse_mentee_set(bonus_mentees) != _parse_mentee_set(talent_mentees)

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

        # Tenet mismatch between cycles (compare same categories: strengths->strengths, improvements->improvements)
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

    # Prior cycle bonus change detection (+/-15pp threshold)
    # Uses calculated bonus vs last_bonus_allocation_percent from Workday
    if has_bonus_data and rated_employees:
        params = {
            'upside_exponent': 1.35,
            'downside_exponent': 1.9
        }
        bonus_settings = get_bonus_settings_fn()
        budget_override = bonus_settings.budget_override if bonus_settings else 0.0
        workday_pool = bonus_settings.workday_pool if bonus_settings else None

        # Calculate all_targets_sum from ALL employees (not filtered team_data)
        # This ensures the budget pool is scaled proportionally when filters are applied
        all_targets_sum = 0
        for emp in all_employees:
            bonus_target = emp.get('Bonus Target Manager Currency') or emp.get('Bonus Target - Local Currency')
            if bonus_target:
                try:
                    all_targets_sum += float(bonus_target)
                except (ValueError, TypeError):
                    pass

        bonus_calc = calculate_bonus_fn(rated_employees, params, budget_override, workday_pool, all_targets_sum)
        results_by_id = bonus_calc.get('results_by_id', {})

        BONUS_CHANGE_THRESHOLD = 15  # percentage points
        for emp in rated_employees:
            emp_id = emp.get('Associate ID')
            prior_bonus = emp.get('Last Bonus Allocation Percent')

            # Skip if no historical data or no calculated bonus
            if prior_bonus is None or emp_id not in results_by_id:
                continue

            # Skip special case employees (bonus override)
            if emp.get('bonus_override_percent') is not None:
                continue

            calc_result = results_by_id[emp_id]
            current_bonus = calc_result.get('bonus_percent_of_target')
            if current_bonus is None:
                continue

            delta = current_bonus - prior_bonus
            if abs(delta) >= BONUS_CHANGE_THRESHOLD:
                change_info = {
                    'name': emp.get('Associate', 'Unknown'),
                    'id': emp_id,
                    'job': emp.get('Current Job Profile', ''),
                    'prior_bonus': round(prior_bonus, 1),
                    'current_bonus': round(current_bonus, 1),
                    'delta': round(delta, 1)
                }
                if delta > 0:
                    inconsistencies['bonus_increase_from_prior'].append(change_info)
                else:
                    inconsistencies['bonus_decrease_from_prior'].append(change_info)

        # Recalculate total after adding prior cycle entries
        total_inconsistencies = sum(len(v) for v in inconsistencies.values())

    return (inconsistencies, total_inconsistencies)


def calculate_mentorship_analysis(team_data):
    """Calculate mentorship analysis -- identify patterns worth reviewing.

    Returns:
        tuple: (mentorship_analysis dict, total_mentorship_flags int)
    """
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

    return (mentorship_analysis, total_mentorship_flags)


def calculate_tenure_analytics(team_data):
    """Calculate tenure analytics.

    Returns:
        dict: tenure_analytics with distributions, averages, long-tenure
        employees, and per-role breakdowns.
    """
    tenure_bands = ['< 1 year', '1-2 years', '2-5 years', '5-10 years', '10+ years']

    # Length of Service distribution
    los_distribution = {band: 0 for band in tenure_bands}
    los_distribution['Unknown'] = 0

    # Time in Job Profile distribution
    tijp_distribution = {band: 0 for band in tenure_bands}
    tijp_distribution['Unknown'] = 0

    # For averages and performance quadrant
    los_values = []
    tijp_values = []
    performance_tenure_data = []

    for emp in team_data:
        # Parse tenure values
        los_months = parse_tenure_to_months(emp.get('length_of_service'))
        tijp_months = parse_tenure_to_months(emp.get('time_in_job_profile'))

        # Distribution counts
        los_distribution[get_tenure_band(los_months)] += 1
        tijp_distribution[get_tenure_band(tijp_months)] += 1

        # Collect for averages
        if los_months is not None:
            los_values.append(los_months)
        if tijp_months is not None:
            tijp_values.append(tijp_months)

        # Collect tenure data for employees with performance info
        rating = emp.get('performance_rating_percent')
        talent_perf = emp.get('talent_overall_perf')

        if tijp_months is not None:
            performance_tenure_data.append({
                'name': emp.get('Associate', 'Unknown'),
                'id': emp.get('Associate ID', ''),
                'job': emp.get('Current Job Profile', ''),
                'time_in_role': emp.get('time_in_job_profile', 'N/A'),
                'time_in_role_months': tijp_months,
                'performance_rating': rating,
                'talent_perf': talent_perf
            })

    # Calculate averages
    avg_los_months = round(sum(los_values) / len(los_values), 1) if los_values else None
    avg_tijp_months = round(sum(tijp_values) / len(tijp_values), 1) if tijp_values else None

    # Employees with long tenure (3+ years in role)
    long_tenure_employees = [
        emp for emp in performance_tenure_data
        if emp['time_in_role_months'] >= 36
    ]
    long_tenure_employees.sort(key=lambda x: x['time_in_role_months'], reverse=True)

    # Tenure by Job Profile (role)
    tenure_by_role = defaultdict(lambda: {'los_values': [], 'tijp_values': [], 'count': 0})
    for emp in team_data:
        job = emp.get('Current Job Profile', 'Unknown')
        los_months = parse_tenure_to_months(emp.get('length_of_service'))
        tijp_months = parse_tenure_to_months(emp.get('time_in_job_profile'))

        tenure_by_role[job]['count'] += 1
        if los_months is not None:
            tenure_by_role[job]['los_values'].append(los_months)
        if tijp_months is not None:
            tenure_by_role[job]['tijp_values'].append(tijp_months)

    # Calculate averages per role
    tenure_by_role_summary = []
    for job, data in tenure_by_role.items():
        if data['tijp_values'] or data['los_values']:
            avg_los = sum(data['los_values']) / len(data['los_values']) if data['los_values'] else None
            avg_tijp = sum(data['tijp_values']) / len(data['tijp_values']) if data['tijp_values'] else None
            tenure_by_role_summary.append({
                'job': job,
                'count': data['count'],
                'avg_length_of_service': format_months_display(avg_los),
                'avg_time_in_role': format_months_display(avg_tijp),
                'avg_los_months': avg_los,
                'avg_tijp_months': avg_tijp
            })

    # Sort by avg time in role descending
    tenure_by_role_summary.sort(
        key=lambda x: x['avg_tijp_months'] if x['avg_tijp_months'] else 0,
        reverse=True
    )

    # Tenure analytics summary
    tenure_analytics = {
        'los_distribution': los_distribution,
        'tijp_distribution': tijp_distribution,
        'avg_length_of_service': format_months_display(avg_los_months),
        'avg_time_in_role': format_months_display(avg_tijp_months),
        'avg_los_months': avg_los_months,
        'avg_tijp_months': avg_tijp_months,
        'employees_with_tenure_data': len(tijp_values),
        'total_employees': len(team_data),
        'long_tenure_employees': long_tenure_employees[:10],  # Top 10
        'pct_long_tenure': round(len([v for v in tijp_values if v >= 36]) / len(tijp_values) * 100, 1) if tijp_values else 0,
        'tenure_by_role': tenure_by_role_summary
    }

    return tenure_analytics
