"""Database access helpers and filtering logic.

Functions that access the database take a `get_db` callable to avoid
importing Flask application context directly. Pure filtering functions
operate on employee dicts.
"""
import json
import os
from collections import Counter
from datetime import datetime

from models import Employee, BonusSettings, RatingSnapshot, Period
from services.employee_utils import CURRENCY_SYMBOLS, has_direct_reports


def get_all_employees(get_db_fn):
    """Get all employees from database.

    Args:
        get_db_fn: Callable that returns a database session
    """
    db = get_db_fn()
    try:
        employees = db.query(Employee).all()
        return [emp.to_dict() for emp in employees]
    finally:
        db.close()


def get_employee_by_id(associate_id, get_db_fn):
    """Get a single employee by ID.

    Args:
        associate_id: The employee's associate ID
        get_db_fn: Callable that returns a database session
    """
    db = get_db_fn()
    try:
        return db.query(Employee).filter(Employee.associate_id == associate_id).first()
    finally:
        db.close()


def get_bonus_settings(get_db_fn):
    """Get bonus settings from database, creating default if needed.

    Args:
        get_db_fn: Callable that returns a database session
    """
    db = get_db_fn()
    try:
        settings = db.query(BonusSettings).first()
        if not settings:
            # Create default settings
            settings = BonusSettings(budget_override=0.0, last_updated=datetime.now())
            db.add(settings)
            db.commit()
            db.refresh(settings)
        return settings
    finally:
        db.close()


def update_bonus_settings(budget_override, get_db_fn):
    """Update bonus settings in database.

    Args:
        budget_override: New budget override value
        get_db_fn: Callable that returns a database session
    """
    db = get_db_fn()
    try:
        settings = db.query(BonusSettings).first()
        if not settings:
            settings = BonusSettings()
            db.add(settings)

        settings.budget_override = budget_override
        settings.last_updated = datetime.now()
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_manager_currency(get_db_fn, cache_get=None, cache_set=None):
    """Detect the manager's currency.

    Priority order:
    1. BonusSettings.manager_currency - extracted from column headers during import
    2. Domestic employee detection - employees with NULL bonus_target_manager_currency
    3. Majority currency fallback - most common currency among employees
    4. Default to USD

    Args:
        get_db_fn: Callable that returns a database session
        cache_get: Optional callable that returns cached value or None
        cache_set: Optional callable to store result in cache

    Returns:
        tuple: (currency_code, currency_symbol) e.g., ('AUD', 'A$')
    """
    # Return cached result if available
    if cache_get:
        cached = cache_get()
        if cached is not None:
            return cached

    db = get_db_fn()
    try:
        # Priority 1: Check BonusSettings for currency extracted from column headers
        settings = db.query(BonusSettings).first()
        if settings and settings.manager_currency:
            currency = settings.manager_currency
            symbol = CURRENCY_SYMBOLS.get(currency, currency)
            result = (currency, symbol)
        else:
            # Priority 2: Domestic employees have NULL in bonus_target_manager_currency
            domestic = db.query(Employee).filter(
                Employee.bonus_target_manager_currency.is_(None),
                Employee.currency.isnot(None)
            ).first()

            if domestic and domestic.currency:
                currency = domestic.currency
                symbol = CURRENCY_SYMBOLS.get(currency, currency)
                result = (currency, symbol)
            elif db.query(Employee).filter(Employee.currency.isnot(None)).first():
                # Priority 3: Majority currency fallback
                all_employees = db.query(Employee).filter(
                    Employee.currency.isnot(None)
                ).all()
                currencies = [e.currency for e in all_employees]
                if currencies:
                    most_common = Counter(currencies).most_common(1)[0][0]
                    symbol = CURRENCY_SYMBOLS.get(most_common, most_common)
                    result = (most_common, symbol)
                else:
                    result = ('USD', '$')
            else:
                # Priority 4: Default to USD
                result = ('USD', '$')

        # Cache result
        if cache_set:
            cache_set(result)

        return result
    finally:
        db.close()


def load_tenets_config():
    """
    Load tenets configuration from tenets.json.

    Returns:
        tuple: (tenets_config dict, tenets_map dict mapping id->name)
               Returns (None, {}) if no config found
    """
    tenets_file = 'tenets.json'
    if os.path.exists(tenets_file):
        try:
            with open(tenets_file, 'r') as f:
                tenets_config = json.load(f)
                tenets_map = {t['id']: t['name'] for t in tenets_config.get('tenets', [])}
                return tenets_config, tenets_map
        except Exception as e:
            print(f"Error loading tenets from {tenets_file}: {e}")
    return None, {}


def convert_tenet_names_to_ids(names_str: str, tenets_config: dict) -> str:
    """
    Convert comma-separated tenet names to JSON array of tenet IDs.

    Used when importing from Notes field which stores human-readable names
    like "We Serve Our Customers, We Champion Ownership" but the database
    expects JSON arrays of IDs like '["ownership-1", "ownership-2"]'.

    Args:
        names_str: Comma-separated tenet names (or semicolon-separated)
        tenets_config: Tenets configuration dict with 'tenets' list

    Returns:
        JSON string of tenet IDs, or None if no valid tenets found
    """
    if not names_str or not tenets_config:
        return None

    # Build name-to-id mapping (case-insensitive)
    name_to_id = {}
    for t in tenets_config.get('tenets', []):
        name_to_id[t['name'].lower().strip()] = t['id']

    # Parse the names (handle both comma and semicolon separators)
    separator = ';' if ';' in names_str else ','
    names = [n.strip() for n in names_str.split(separator) if n.strip()]

    # Convert to IDs
    ids = []
    for name in names:
        tenet_id = name_to_id.get(name.lower())
        if tenet_id:
            ids.append(tenet_id)

    return json.dumps(ids) if ids else None


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
            'active': bool,                     # Any exclusion filters active?
            'total_count': int,                 # Original count
            'filtered_count': int,              # After filtering
            'hidden_count': int,                # How many hidden by exclusions
            'params': filter_params,            # For UI state
            'available_titles': [str],          # All unique job titles
            'available_employees': [dict],      # All employees [{id, name}]
            'manager_ids': [str],               # IDs of managers
            'employee_titles': {id: title},     # ID -> job title mapping
            'available_teams': [dict],          # Teams for sidebar [{org, manager_name, count}]
        }
    """
    filtered = employees.copy()

    # Build team data BEFORE any filtering (for sidebar display)
    teams_by_org = {}
    for emp in employees:
        org = emp.get('Supervisory Organization', '')
        if org:
            if org not in teams_by_org:
                teams_by_org[org] = []
            teams_by_org[org].append(emp)

    # Extract manager name from org string: "Org Name (Manager Name)" -> "Manager Name"
    def extract_manager_name(org_string):
        if '(' in org_string and org_string.endswith(')'):
            return org_string[org_string.rfind('(') + 1:-1]
        return org_string

    available_teams = sorted([
        {
            'org': org,
            'manager_name': extract_manager_name(org),
            'count': len(team_employees)
        }
        for org, team_employees in teams_by_org.items()
    ], key=lambda x: x['manager_name'])

    # Apply org inclusion filter FIRST (scoping)
    if filter_params.get('include_orgs'):
        include_orgs = filter_params['include_orgs']
        filtered = [emp for emp in filtered
                   if emp.get('Supervisory Organization') in include_orgs]

    # Apply manager exclusion (within scope)
    if filter_params.get('exclude_managers'):
        filtered = [emp for emp in filtered if not has_direct_reports(emp, employees)]

    # Apply title exclusion (within scope)
    if filter_params.get('exclude_titles'):
        exclude_titles = filter_params['exclude_titles']
        filtered = [emp for emp in filtered
                   if emp.get('Current Job Profile') not in exclude_titles]

    # Apply ID exclusion (within scope)
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

    # Calculate hidden count (by exclusion filters only, not org scoping)
    if filter_params.get('include_orgs'):
        scope_count = sum(len(teams_by_org.get(org, [])) for org in filter_params['include_orgs'])
    else:
        scope_count = len(employees)
    hidden_by_exclusions = scope_count - len(filtered)

    # Build filter info
    filter_info = {
        'active': any([
            filter_params.get('exclude_managers'),
            filter_params.get('exclude_titles'),
            filter_params.get('exclude_ids')
        ]),
        'total_count': len(employees),
        'filtered_count': len(filtered),
        'hidden_count': hidden_by_exclusions,
        'params': filter_params,
        'available_titles': available_titles,
        'available_employees': available_employees,
        'manager_ids': manager_ids,
        'employee_titles': employee_titles,
        'available_teams': available_teams,
    }

    return filtered, filter_info


def get_all_history_snapshots(get_db_fn):
    """Query all RatingSnapshot records joined with Period data.

    Args:
        get_db_fn: Callable that returns a database session

    Returns:
        List of dicts with snapshot and period information, ordered by
        period date descending, then employee name ascending.
    """
    db = get_db_fn()
    try:
        snapshots = db.query(RatingSnapshot, Period).join(
            Period, RatingSnapshot.period_id == Period.id
        ).order_by(
            Period.archived_at.desc(),
            RatingSnapshot.snapshot_name
        ).all()

        results = []
        for snapshot, period in snapshots:
            results.append({
                'period_id': period.id,
                'period_name': period.name,
                'cycle_type': period.cycle_type or 'bonus',
                'archived_at': period.archived_at.strftime('%Y-%m-%d') if period.archived_at else '',
                'associate_id': snapshot.associate_id,
                'snapshot_name': snapshot.snapshot_name or '',
                'snapshot_org': snapshot.snapshot_org or '',
                'snapshot_job_profile': snapshot.snapshot_job_profile or '',
                'performance_rating': snapshot.performance_rating,
                'bonus_allocation': snapshot.bonus_allocation,
                'snapshot_bonus_target_manager_currency': snapshot.snapshot_bonus_target_manager_currency,
                'justification': snapshot.justification or '',
                'tenets_strengths': snapshot.tenets_strengths or '',
                'tenets_improvements': snapshot.tenets_improvements or '',
                'mentors': snapshot.mentors or '',
                'mentees': snapshot.mentees or '',
                'snapshot_talent_overall_perf': snapshot.snapshot_talent_overall_perf or '',
                'snapshot_talent_perf_what': snapshot.snapshot_talent_perf_what or '',
                'snapshot_talent_perf_how': snapshot.snapshot_talent_perf_how or '',
                'snapshot_talent_growth_agility': snapshot.snapshot_talent_growth_agility or '',
                'snapshot_talent_change_agility': snapshot.snapshot_talent_change_agility or '',
                'snapshot_talent_movement_readiness': snapshot.snapshot_talent_movement_readiness or '',
            })
        return results
    finally:
        db.close()
