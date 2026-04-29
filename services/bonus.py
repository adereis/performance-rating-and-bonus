"""Bonus calculation, calibration distribution, and mentorship statistics.

Pure computation functions with no Flask or database dependencies.
Operates on employee dicts (from to_dict()).
"""
from services.employee_utils import (
    RATING_THRESHOLD_HIGH,
    RATING_THRESHOLD_MID,
    RATING_THRESHOLD_LOW,
)


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
        if rating is not None:
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

        # Calculate delta from range limits (for status determination)
        if percentage < suggested_min:
            delta_from_range = percentage - suggested_min  # Negative
        elif percentage > suggested_max:
            delta_from_range = percentage - suggested_max  # Positive
        else:
            delta_from_range = 0  # Within range

        # Determine status: green (within), yellow (slightly off), orange (significantly off)
        if within_range:
            status = 'good'
        elif abs(delta_from_range) <= 10:
            status = 'warning'
        else:
            status = 'alert'

        # Delta for display (distance from midpoint, consistent with talent calibration)
        delta = percentage - suggested_mid

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


def calculate_bonus_for_employees(employees, params, budget_override=0.0, workday_pool=None, all_targets_sum=None):
    """
    Calculate bonuses for a given set of employees.
    Returns dict with results, normalization factor, and metadata.

    Handles special case employees (pro-rata leave, etc.) using Option B pool handling:
    - Override employees get a fixed % of their bonus target
    - Their bonus comes from the same pool (unused portion redistributed to others)
    - Normal employees compete for the remaining pool

    Args:
        employees: List of employee dicts (typically only rated employees)
        params: Dict with upside_exponent and downside_exponent
        budget_override: Additional budget (can be negative) to add to total pool
        workday_pool: Total pool from Workday metadata (authoritative budget).
        all_targets_sum: Sum of ALL employee bonus targets (for proportional calculation
                         when only a subset of employees are rated).
    """
    # Separate employees into override and normal groups
    override_employees = []
    normal_employees = []
    for emp in employees:
        if emp.get('bonus_override_percent') is not None:
            override_employees.append(emp)
        else:
            normal_employees.append(emp)

    # Calculate sum of bonus targets for ALL employees being calculated
    sum_of_targets = 0
    for emp in employees:
        bonus_target = emp.get('Bonus Target Manager Currency') or emp.get('Bonus Target - Local Currency')
        if bonus_target:
            try:
                sum_of_targets += float(bonus_target)
            except (ValueError, TypeError):
                pass

    # Determine base pool from Workday (or sum of targets if no Workday pool)
    workday_base = workday_pool if (workday_pool is not None and workday_pool > 0) else sum_of_targets

    # budget_override: if set (>0), replaces workday_base entirely
    effective_pool = budget_override if budget_override > 0 else workday_base

    # Calculate proportion for filtered employees
    if all_targets_sum and all_targets_sum > 0 and sum_of_targets < all_targets_sum:
        proportion = sum_of_targets / all_targets_sum
    else:
        proportion = 1.0

    # base_pool = proportional share of Workday pool (for "This calc" display)
    base_pool = workday_base * proportion

    # adjusted_pool = what's used for calculation (effective pool, scaled)
    adjusted_pool = effective_pool * proportion

    # --- Step 1: Calculate override employee bonuses (fixed % of target) ---
    override_results = []
    override_total = 0
    override_count = 0

    for emp in override_employees:
        try:
            override_pct = float(emp.get('bonus_override_percent', 0))
            bonus_target = float((emp.get('Bonus Target Manager Currency') or emp.get('Bonus Target - Local Currency')) or 0)
            base_pay = float((emp.get('Current Base Pay Manager Currency') or emp.get('Current Base Pay All Countries')) or 0)
        except (ValueError, TypeError):
            continue

        if bonus_target <= 0:
            continue

        # Fixed bonus based on override percentage
        final_bonus = bonus_target * (override_pct / 100)
        override_total += final_bonus
        override_count += 1

        override_results.append({
            'employee': emp,
            'rating': None,  # Not applicable for override employees
            'bonus_target': bonus_target,
            'base_pay': base_pay,
            'perf_multiplier': None,  # Not applicable
            'raw_share': None,  # Not applicable
            'final_bonus': final_bonus,
            'bonus_percent_of_target': round(override_pct),
            'is_override': True,
            'special_case_notes': emp.get('special_case_notes')
        })

    # --- Step 2: Calculate remaining pool for normal employees ---
    remaining_pool = adjusted_pool - override_total

    # --- Step 3: Calculate normal employee bonuses using curve ---
    bonus_results = []
    total_raw_shares = 0
    employees_without_bonus_target = 0

    for emp in normal_employees:
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
            'raw_share': raw_share,
            'is_override': False
        })

    # Normalization: Calculate value per share using remaining pool
    value_per_share = remaining_pool / total_raw_shares if total_raw_shares > 0 else 0

    # Calculate final bonuses for normal employees
    normal_total_allocated = 0
    for result in bonus_results:
        result['final_bonus'] = result['raw_share'] * value_per_share
        # Round to integer - decimals are unnecessary and error-prone
        result['bonus_percent_of_target'] = round(result['final_bonus'] / result['bonus_target'] * 100) if result['bonus_target'] > 0 else 0
        normal_total_allocated += result['final_bonus']

    # --- Step 4: Combine results ---
    all_results = override_results + bonus_results
    total_allocated = override_total + normal_total_allocated

    # Create lookup by Associate ID for easy access
    results_by_id = {r['employee']['Associate ID']: r for r in all_results}

    return {
        'results': all_results,
        'results_by_id': results_by_id,
        'workday_pool': workday_pool,        # From Workday metadata (may be None)
        'sum_of_targets': sum_of_targets,    # Calculated from employee targets
        'base_pool': base_pool,              # What we're using (workday_pool or sum_of_targets)
        'budget_override': budget_override,  # Absolute pool replacement (if >0, replaces base_pool)
        'total_pool': adjusted_pool,         # Final pool for calculation
        'total_allocated': total_allocated,
        'value_per_share': value_per_share,
        'employees_without_bonus_target': employees_without_bonus_target,
        # New fields for special case tracking
        'override_count': override_count,
        'override_total': override_total,
        'remaining_pool': remaining_pool,
    }
