"""Employee utility functions: constants, status checks, formatting.

Pure functions with no Flask or database dependencies. These operate
on employee dicts (from to_dict()) or ORM objects.
"""
import re


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

# Placeholder values that should be normalized to empty for mentor/mentee fields
# These are common entries managers use when they haven't filled in actual names
MENTOR_FIELD_PLACEHOLDERS = frozenset({
    'none', 'n/a', 'na', 'tbd', 'tbc', 'tba', '-', '?', 'null', 'nil', 'unknown',
    'not applicable', 'not assigned', 'pending', 'to be determined', 'to be confirmed',
})


def normalize_mentor_field(value):
    """Normalize mentor/mentee field values, converting placeholders to empty string.

    Returns a tuple of (normalized_value, was_placeholder) so the API can inform
    the client when a value was treated as a placeholder.
    """
    if not value:
        return ('', False)
    cleaned = value.strip()
    if not cleaned:
        return ('', False)
    if cleaned.lower() in MENTOR_FIELD_PLACEHOLDERS:
        return ('', True)
    return (cleaned, False)


def _parse_mentee_set(value):
    """Parse a mentee string into a normalized set of names for comparison.

    Handles both comma and semicolon delimiters. Returns a frozenset of
    lowercase stripped names, allowing delimiter-agnostic comparison.
    """
    if not value:
        return frozenset()
    # Treat semicolons as commas to handle both delimiters uniformly
    names = frozenset(
        name.strip().lower()
        for name in value.replace(';', ',').split(',')
        if name.strip()
    )
    return names


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

    return rating is not None and bool(justification) and _has_tenets(tenets_s, tenets_i)


def is_employee_complete(emp):
    """Check if employee is complete for the bonus cycle workflow.

    Complete = fully rated (rating + justification + tenets) OR has a bonus
    override set. Use for UI completion indicators (sidebar dots, progress
    counts). For bonus calculation filtering, use is_employee_rated() instead.
    """
    if isinstance(emp, dict):
        has_override = emp.get('bonus_override_percent') is not None
    else:
        has_override = emp.bonus_override_percent is not None
    return is_employee_rated(emp) or has_override


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


def get_manager_names(all_employees):
    """Return the set of names that manage at least one supervisory org.

    Handles both Workday formats: legacy "Org Name (Manager Name)" (parse out
    the parenthesized name) and the report format's "Direct Manager" column
    (the value is already the bare manager name). Matching against this set is
    then exact, so a short name like "Lee" is no longer wrongly flagged as
    managing "Engineering (Ashley Lee)". Build this once and pass it to
    has_direct_reports() to avoid rescanning all employees per call.
    """
    names = set()
    for emp in all_employees:
        org = (emp.get('Supervisory Organization') or '').strip()
        if not org:
            continue
        # Parens form -> parsed manager; otherwise the value is the manager name.
        names.add(parse_manager_name_from_org(org) or org)
    return names


def has_direct_reports(employee, all_employees, manager_names=None):
    """
    Check if an employee has direct reports (is a manager).

    Detection methods (OR logic):
    1. Management level: employee's management_level contains "Manager"
       or "Director" (works for talent calibration files)
    2. Supervisory org lookup: the employee is the parsed manager of some
       other employee's "Supervisory Organization" (works for bonus files)

    Args:
        employee: Employee dict to check
        all_employees: List of all employee dicts
        manager_names: Optional precomputed set from get_manager_names(); pass
            it when calling in a loop to avoid an O(n^2) rescan.

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

    # Method 2: Is this employee the parsed manager of some supervisory org?
    employee_name = employee.get('Associate', '')
    if employee_name:
        if manager_names is None:
            manager_names = get_manager_names(all_employees)
        if employee_name in manager_names:
            return True

    return False


def normalize_movement_readiness(value: str | None) -> str | None:
    """Normalize Workday movement readiness values to canonical form.

    Workday exports longer variants like:
    - 'Ready Now to be promoted in current role (upcoming cycle)'
    - 'Ready for a lateral move outside of current role'

    This normalizes them to the canonical TALENT_MOVEMENT_VALUES.
    """
    if not value:
        return None

    # Pattern matching: find which canonical value is contained in the input
    # Order matters: check more specific patterns first
    patterns = [
        ('Continue growing', 'Continue growing in current role'),
        ('Ready Now', 'Ready Now to be promoted in current role'),
        ('lateral move', 'Ready for lateral move'),
        ('promoted outside', 'Ready to be promoted outside of current role'),
        ('Not well placed', 'Not well placed'),
    ]
    for pattern, canonical in patterns:
        if pattern in value:
            return canonical

    # If no pattern matches, return original (may be a new Workday value)
    return value


def parse_tenure_to_months(tenure_str: str | None) -> int | None:
    """Parse Workday tenure strings like '2 years, 3 months' to total months.

    Handles various formats:
    - '2 years, 3 months'
    - '1 year, 6 months'
    - '8 months'
    - '3 years'

    Returns None if unparseable or empty.
    """
    if not tenure_str or not isinstance(tenure_str, str):
        return None

    tenure_str = tenure_str.lower().strip()
    total_months = 0

    # Extract years
    years_match = re.search(r'(\d+)\s*year', tenure_str)
    if years_match:
        total_months += int(years_match.group(1)) * 12

    # Extract months
    months_match = re.search(r'(\d+)\s*month', tenure_str)
    if months_match:
        total_months += int(months_match.group(1))

    return total_months if total_months > 0 else None


def get_tenure_band(months: int | None) -> str:
    """Convert months to a tenure band for histogram bucketing."""
    if months is None:
        return 'Unknown'
    elif months < 12:
        return '< 1 year'
    elif months < 24:
        return '1-2 years'
    elif months < 60:
        return '2-5 years'
    elif months < 120:
        return '5-10 years'
    else:
        return '10+ years'


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


def parse_manager_name_from_org(supervisory_org):
    """Extract manager name from 'Supervisory Organization (Manager Name)' format.

    Args:
        supervisory_org: String like "Engineering (John Smith)"

    Returns:
        Manager name if found, otherwise empty string
    """
    if not supervisory_org:
        return ''
    match = re.search(r'\(([^)]+)\)\s*$', supervisory_org)
    return match.group(1) if match else ''


def get_rating_category(rating_percent):
    """Derive rating category from performance rating percentage.

    Args:
        rating_percent: Performance rating (0-200%)

    Returns:
        'High', 'Solid', 'Below', or '' if no rating
    """
    if rating_percent is None:
        return ''
    if rating_percent >= 110:
        return 'High'
    if rating_percent >= 90:
        return 'Solid'
    return 'Below'


def is_manager(employee):
    """Check if employee has direct reports based on management level.

    Args:
        employee: Employee dict

    Returns:
        'Yes', 'No', or '' if unknown
    """
    mgmt_level = employee.get('management_level', '')
    if not mgmt_level:
        return ''
    level_lower = mgmt_level.lower()
    if 'manager' in level_lower or 'director' in level_lower or 'vp' in level_lower:
        return 'Yes'
    if 'ic' in level_lower:
        return 'No'
    return ''
