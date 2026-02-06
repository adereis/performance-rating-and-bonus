"""Import field update logic for Workday re-imports.

Handles the preserve-or-update pattern for manager-entered fields when
re-importing Workday data. Fields modified locally by the manager are
preserved; unmodified fields are updated from Workday.

These functions operate on SQLAlchemy ORM Employee objects directly.
"""
import json

from models import derive_overall_performance, derive_future_talent
from services.employee_utils import (
    normalize_mentor_field,
    _parse_mentee_set,
    normalize_movement_readiness,
)


# ═══════════════════════════════════════════════════════════════════════════
# Comparison helpers
# ═══════════════════════════════════════════════════════════════════════════


def text_unmodified(current, original):
    """Check if a text field is unmodified (handles None vs empty string).

    Used to determine whether a manager changed a field locally.
    If current matches original (treating None and '' as equal), the
    field is unmodified and safe to overwrite from Workday.
    """
    return (current or '') == (original or '')


def json_string_unmodified(current, original):
    """Check if a JSON string field is unmodified.

    Parses both values as JSON arrays and compares sorted contents,
    so order differences don't count as modifications. Falls back to
    string comparison if JSON parsing fails.
    """
    try:
        curr_parsed = json.loads(current) if current else []
        orig_parsed = json.loads(original) if original else []
        return sorted(curr_parsed) == sorted(orig_parsed)
    except (json.JSONDecodeError, TypeError):
        # If not valid JSON, fall back to string comparison
        return (current or '') == (original or '')


def mentor_fields_equal(val1, val2):
    """Compare mentor/mentee fields, normalizing placeholders.

    Uses normalize_mentor_field to treat placeholder values like
    "None", "TBD", "N/A" as empty, so they compare equal to empty
    strings or None.
    """
    norm1, _ = normalize_mentor_field(val1)
    norm2, _ = normalize_mentor_field(val2)
    return norm1 == norm2


def tenets_unmodified(current, original):
    """Compare tenet fields as JSON strings for equality.

    Serializes both values with sorted keys and compares the JSON
    strings. Treats None and empty arrays as equivalent.
    """
    curr_str = json.dumps(current, sort_keys=True) if current else '[]'
    orig_str = json.dumps(original, sort_keys=True) if original else '[]'
    return curr_str == orig_str


# ═══════════════════════════════════════════════════════════════════════════
# Change log formatting
# ═══════════════════════════════════════════════════════════════════════════


def format_change_value(value, field_name):
    """Format a value for display in the import change log.

    Handles numeric formatting (percentages, currency amounts),
    JSON array summarization, and string truncation for readability.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if 'percent' in field_name or 'rating' in field_name:
            return f'{value}%'
        if 'currency' in field_name or 'pay' in field_name or 'target' in field_name:
            return f'{value:,.0f}'
    if isinstance(value, str):
        if value.startswith('[') and value.endswith(']'):
            try:
                items = json.loads(value)
                return f'{len(items)} items' if items else None
            except (json.JSONDecodeError, TypeError):
                pass
        if len(value) > 60:
            return value[:57] + '...'
    return str(value) if value else None


# ═══════════════════════════════════════════════════════════════════════════
# Field update with preservation
# ═══════════════════════════════════════════════════════════════════════════


def update_text_field(emp, field_name, new_value, preserved_list, updates_list):
    """Update a text field with local-modification preservation.

    If the field is unmodified locally (current == original), update
    from Workday and record the change. If modified locally, preserve
    the local value and record the conflict.

    Always updates the _original field to reflect latest Workday data.

    Args:
        emp: SQLAlchemy Employee ORM object
        field_name: Base field name (e.g. 'talent_perf_what')
        new_value: New value from Workday import
        preserved_list: List to append conflict dicts to
        updates_list: List to append change dicts to
    """
    original_field = f'{field_name}_original'
    current_val = getattr(emp, field_name)
    original_val = getattr(emp, original_field)

    if text_unmodified(current_val, original_val):
        # Unmodified locally - update from Workday
        setattr(emp, field_name, new_value)
        if (current_val or '') != (new_value or ''):
            updates_list.append({
                'field': field_name,
                'old': format_change_value(current_val, field_name),
                'new': format_change_value(new_value, field_name),
            })
    else:
        # Modified locally - only show conflict if local differs from workday
        if (current_val or '') != (new_value or ''):
            preserved_list.append({
                'field': field_name,
                'local': format_change_value(current_val, field_name),
                'workday': format_change_value(new_value, field_name),
            })
    # Always update _original to reflect latest Workday data
    setattr(emp, original_field, new_value)


def update_mentor_field(emp, field_name, new_value, preserved_list, updates_list):
    """Update a mentor/mentee field with local-modification preservation.

    Same as update_text_field but uses mentor_fields_equal for change
    detection, which normalizes placeholder values like "None" and "TBD".

    Args:
        emp: SQLAlchemy Employee ORM object
        field_name: Base field name (e.g. 'mentor', 'talent_mentor')
        new_value: New value from Workday import
        preserved_list: List to append conflict dicts to
        updates_list: List to append change dicts to
    """
    original_field = f'{field_name}_original'
    current_val = getattr(emp, field_name)
    original_val = getattr(emp, original_field)

    if text_unmodified(current_val, original_val):
        # Unmodified locally - update from Workday
        setattr(emp, field_name, new_value)
        if not mentor_fields_equal(current_val, new_value):
            updates_list.append({
                'field': field_name,
                'old': format_change_value(current_val, field_name),
                'new': format_change_value(new_value, field_name),
            })
    else:
        # Modified locally - only show conflict if local differs from workday
        if not mentor_fields_equal(current_val, new_value):
            preserved_list.append({
                'field': field_name,
                'local': format_change_value(current_val, field_name),
                'workday': format_change_value(new_value, field_name),
            })
    # Always update _original to reflect latest Workday data
    setattr(emp, original_field, new_value)


def update_json_field(emp, field_name, new_value, preserved_list, updates_list):
    """Update a JSON string field with local-modification preservation.

    Same as update_text_field but uses json_string_unmodified for
    comparison, which parses and sorts JSON arrays before comparing.

    Args:
        emp: SQLAlchemy Employee ORM object
        field_name: Base field name (e.g. 'talent_tenets_strengths')
        new_value: New JSON string value from Workday import
        preserved_list: List to append conflict dicts to
        updates_list: List to append change dicts to
    """
    original_field = f'{field_name}_original'
    current_val = getattr(emp, field_name)
    original_val = getattr(emp, original_field)

    if json_string_unmodified(current_val, original_val):
        # Unmodified locally - update from Workday
        setattr(emp, field_name, new_value)
        if (current_val or '') != (new_value or ''):
            updates_list.append({
                'field': field_name,
                'old': format_change_value(current_val, field_name),
                'new': format_change_value(new_value, field_name),
            })
    else:
        # Modified locally - only show conflict if local differs from workday
        if not json_string_unmodified(current_val, new_value):
            preserved_list.append({
                'field': field_name,
                'local': format_change_value(current_val, field_name),
                'workday': format_change_value(new_value, field_name),
            })
    # Always update _original to reflect latest Workday data
    setattr(emp, original_field, new_value)


# ═══════════════════════════════════════════════════════════════════════════
# Talent import: apply fields for existing employee
# ═══════════════════════════════════════════════════════════════════════════


def apply_talent_import(employee, emp_data, tenets_config, load_tenets_config_fn):
    """Apply talent import data to an existing employee with preservation.

    Updates manager-entered talent fields using the preserve-or-update
    pattern: fields unmodified locally are updated from Workday; fields
    modified locally are preserved and conflicts recorded.

    Workday-sourced fields (extended identity, historical, calibration
    status) are always overwritten.

    Args:
        employee: SQLAlchemy Employee ORM object (existing)
        emp_data: Dict of parsed row data from Workday XLSX
        tenets_config: Tenets configuration dict (or None)
        load_tenets_config_fn: Callable that returns (tenets_config, tenets_map)
            tuple. Used as fallback if tenets_config is None.

    Returns:
        tuple: (preserved_fields, updated_fields) where each is a list
        of dicts suitable for the import change log.
    """
    emp_updates = []
    emp_preserved = []

    # ─── Workday-sourced fields (always overwrite) ─────────────────────
    # Extended identity
    employee.management_level = emp_data.get('management_level')
    employee.job_category = emp_data.get('job_category')
    employee.hire_date = emp_data.get('hire_date')
    employee.length_of_service = emp_data.get('length_of_service')
    employee.time_in_job_profile = emp_data.get('time_in_job_profile')
    employee.region = emp_data.get('region')
    employee.country = emp_data.get('country')

    # Historical/last-cycle fields (from Workday, always overwrite)
    employee.talent_last_overall_perf = emp_data.get('talent_last_overall_perf')
    employee.talent_last_identified_future = emp_data.get('talent_last_identified_future')
    employee.talent_last_movement_readiness = emp_data.get('talent_last_movement_readiness')

    # Calibration status (from Workday)
    employee.talent_calibration_status = emp_data.get('talent_calibration_status')

    # Set _original fields from Workday data for modification tracking
    employee.talent_perf_what_original = emp_data.get('talent_perf_what')
    employee.talent_perf_how_original = emp_data.get('talent_perf_how')
    employee.talent_growth_agility_original = emp_data.get('talent_growth_agility')
    employee.talent_change_agility_original = emp_data.get('talent_change_agility')
    employee.talent_movement_readiness_original = emp_data.get('talent_movement_readiness')
    employee.talent_proposed_actions_original = emp_data.get('talent_proposed_actions')

    # ─── Manager-input fields (preserve if modified locally) ───────────

    # Performance What
    update_text_field(
        employee, 'talent_perf_what',
        emp_data.get('talent_perf_what'),
        emp_preserved, emp_updates,
    )

    # Performance How
    update_text_field(
        employee, 'talent_perf_how',
        emp_data.get('talent_perf_how'),
        emp_preserved, emp_updates,
    )

    # Growth Agility
    update_text_field(
        employee, 'talent_growth_agility',
        emp_data.get('talent_growth_agility'),
        emp_preserved, emp_updates,
    )

    # Change Agility
    update_text_field(
        employee, 'talent_change_agility',
        emp_data.get('talent_change_agility'),
        emp_preserved, emp_updates,
    )

    # Movement Readiness (uses normalize function)
    new_movement = normalize_movement_readiness(emp_data.get('talent_movement_readiness'))
    update_text_field(
        employee, 'talent_movement_readiness',
        new_movement,
        emp_preserved, emp_updates,
    )

    # ─── Tool additions: parse from Workday's proposed_actions ─────────
    raw_proposed_actions = emp_data.get('talent_proposed_actions') or ''
    if not tenets_config:
        tenets_config, _ = load_tenets_config_fn()

    if tenets_config and raw_proposed_actions:
        from xlsx_utils import parse_proposed_actions_metadata
        metadata = parse_proposed_actions_metadata(raw_proposed_actions, tenets_config)
        new_actions = metadata['clean_actions'] if metadata['clean_actions'] else None
        new_strengths = json.dumps(metadata['strength_ids']) if metadata['strength_ids'] else None
        new_improvements = json.dumps(metadata['improvement_ids']) if metadata['improvement_ids'] else None
        new_mentor = metadata['mentor'] if metadata['mentor'] else None
        new_mentees = metadata['mentees'] if metadata['mentees'] else None
    else:
        # No tenets config or empty proposed_actions
        new_actions = raw_proposed_actions if raw_proposed_actions else None
        new_strengths = None
        new_improvements = None
        new_mentor = None
        new_mentees = None

    # Proposed Actions
    update_text_field(
        employee, 'talent_proposed_actions',
        new_actions,
        emp_preserved, emp_updates,
    )

    # Talent Tenets Strengths (JSON string)
    update_json_field(
        employee, 'talent_tenets_strengths',
        new_strengths,
        emp_preserved, emp_updates,
    )

    # Talent Tenets Improvements (JSON string)
    update_json_field(
        employee, 'talent_tenets_improvements',
        new_improvements,
        emp_preserved, emp_updates,
    )

    # Talent Mentor
    update_mentor_field(
        employee, 'talent_mentor',
        new_mentor,
        emp_preserved, emp_updates,
    )

    # Talent Mentees
    update_mentor_field(
        employee, 'talent_mentees',
        new_mentees,
        emp_preserved, emp_updates,
    )

    return emp_preserved, emp_updates


def apply_talent_import_new(employee, emp_data, tenets_config, load_tenets_config_fn):
    """Apply talent import data to a NEW employee (first import).

    Sets all talent fields directly from import data without
    preservation logic. Also parses proposed actions for embedded
    tenets and mentor/mentee metadata.

    Args:
        employee: SQLAlchemy Employee ORM object (new, not yet in DB)
        emp_data: Dict of parsed row data from Workday XLSX
        tenets_config: Tenets configuration dict (or None)
        load_tenets_config_fn: Callable that returns (tenets_config, tenets_map)
    """
    # ─── Workday-sourced fields (always set) ───────────────────────────
    # Extended identity
    employee.management_level = emp_data.get('management_level')
    employee.job_category = emp_data.get('job_category')
    employee.hire_date = emp_data.get('hire_date')
    employee.length_of_service = emp_data.get('length_of_service')
    employee.time_in_job_profile = emp_data.get('time_in_job_profile')
    employee.region = emp_data.get('region')
    employee.country = emp_data.get('country')

    # Historical/last-cycle fields (from Workday, always set)
    employee.talent_last_overall_perf = emp_data.get('talent_last_overall_perf')
    employee.talent_last_identified_future = emp_data.get('talent_last_identified_future')
    employee.talent_last_movement_readiness = emp_data.get('talent_last_movement_readiness')

    # Calibration status (from Workday)
    employee.talent_calibration_status = emp_data.get('talent_calibration_status')

    # Set _original fields from Workday data for modification tracking
    employee.talent_perf_what_original = emp_data.get('talent_perf_what')
    employee.talent_perf_how_original = emp_data.get('talent_perf_how')
    employee.talent_growth_agility_original = emp_data.get('talent_growth_agility')
    employee.talent_change_agility_original = emp_data.get('talent_change_agility')
    employee.talent_movement_readiness_original = emp_data.get('talent_movement_readiness')
    employee.talent_proposed_actions_original = emp_data.get('talent_proposed_actions')

    # ─── Manager-input fields (set directly for new employees) ─────────
    # Performance Assessment
    employee.talent_perf_what = emp_data.get('talent_perf_what')
    employee.talent_perf_how = emp_data.get('talent_perf_how')
    employee.talent_overall_perf = emp_data.get('talent_overall_perf')

    # Future Talent
    employee.talent_growth_agility = emp_data.get('talent_growth_agility')
    employee.talent_change_agility = emp_data.get('talent_change_agility')
    employee.talent_identified_future = emp_data.get('talent_identified_future')

    # Movement & Career
    employee.talent_movement_readiness = emp_data.get('talent_movement_readiness')

    # Parse tenets and mentor/mentees from Proposed Actions if present
    raw_proposed_actions = emp_data.get('talent_proposed_actions') or ''
    if not tenets_config:
        tenets_config, _ = load_tenets_config_fn()

    if tenets_config and raw_proposed_actions:
        from xlsx_utils import parse_proposed_actions_metadata
        metadata = parse_proposed_actions_metadata(
            raw_proposed_actions, tenets_config
        )
        employee.talent_proposed_actions = metadata['clean_actions'] if metadata['clean_actions'] else None
        if metadata['strength_ids']:
            employee.talent_tenets_strengths = json.dumps(metadata['strength_ids'])
        if metadata['improvement_ids']:
            employee.talent_tenets_improvements = json.dumps(metadata['improvement_ids'])
        if metadata['mentor']:
            employee.talent_mentor = metadata['mentor']
        if metadata['mentees']:
            employee.talent_mentees = metadata['mentees']
    else:
        employee.talent_proposed_actions = raw_proposed_actions if raw_proposed_actions else None

    # Promotion fields - handle [MODIFIED] marker for our exports
    from xlsx_utils import parse_modified_text_field

    raw_job_profile = emp_data.get('talent_promo_job_profile') or ''
    employee.talent_promo_job_profile = raw_job_profile if raw_job_profile else None
    # Job profile doesn't have [MODIFIED] in text, store as original
    employee.talent_promo_job_profile_original = employee.talent_promo_job_profile

    raw_business_need = emp_data.get('talent_promo_business_need') or ''
    parsed_bn = parse_modified_text_field(raw_business_need)
    employee.talent_promo_business_need = parsed_bn['content'] if parsed_bn['content'] else None
    if not parsed_bn['is_modified']:
        employee.talent_promo_business_need_original = employee.talent_promo_business_need

    raw_role_scope = emp_data.get('talent_promo_role_scope') or ''
    parsed_rs = parse_modified_text_field(raw_role_scope)
    employee.talent_promo_role_scope = parsed_rs['content'] if parsed_rs['content'] else None
    if not parsed_rs['is_modified']:
        employee.talent_promo_role_scope_original = employee.talent_promo_role_scope

    raw_readiness = emp_data.get('talent_promo_readiness') or ''
    parsed_pr = parse_modified_text_field(raw_readiness)
    employee.talent_promo_readiness = parsed_pr['content'] if parsed_pr['content'] else None
    if not parsed_pr['is_modified']:
        employee.talent_promo_readiness_original = employee.talent_promo_readiness


# ═══════════════════════════════════════════════════════════════════════════
# Bonus import: apply fields for existing employee
# ═══════════════════════════════════════════════════════════════════════════


def apply_bonus_import(employee, emp_data, notes_data, tenets_config,
                       convert_tenet_names_to_ids_fn):
    """Apply bonus import data to an existing employee with preservation.

    Updates Workday-sourced fields (salary, targets, etc.) directly.
    Updates manager-entered fields (rating, justification, tenets, mentors)
    using the preserve-or-update pattern.

    Args:
        employee: SQLAlchemy Employee ORM object (existing)
        emp_data: Dict of parsed row data from Workday XLSX
        notes_data: Dict from parse_notes_field() with extracted fields
        tenets_config: Tenets configuration dict (or None)
        convert_tenet_names_to_ids_fn: Callable(names_str, tenets_config)
            that converts tenet name strings to JSON ID arrays.

    Returns:
        tuple: (preserved_fields, updated_fields) where each is a list
        of dicts suitable for the import change log.
    """
    emp_updates = []
    emp_preserved = []

    # ─── Workday-sourced fields (always overwrite) ─────────────────────
    employee.photo = emp_data.get('photo', '')
    employee.errors = emp_data.get('errors', '')
    employee.current_base_pay_all_countries = emp_data.get('current_base_pay_all_countries')
    employee.current_base_pay_manager_currency = emp_data.get('current_base_pay_manager_currency')
    employee.currency = emp_data.get('currency', '')
    employee.grade = emp_data.get('grade', '')
    employee.annual_bonus_target_percent = emp_data.get('annual_bonus_target_percent')
    employee.last_bonus_allocation_percent = emp_data.get('last_bonus_allocation_percent')
    employee.bonus_target_local_currency = emp_data.get('bonus_target_local_currency')
    employee.bonus_target_manager_currency = emp_data.get('bonus_target_manager_currency')
    employee.proposed_bonus_amount = emp_data.get('proposed_bonus_amount')
    employee.proposed_bonus_amount_manager_currency = emp_data.get('proposed_bonus_amount_manager_currency')
    employee.proposed_percent_of_target_bonus = emp_data.get('proposed_percent_of_target_bonus')
    employee.notes = emp_data.get('notes', '')
    employee.zero_bonus_allocated = emp_data.get('zero_bonus_allocated', '')

    # New fields from 2025 Workday format (only set if present)
    if emp_data.get('management_level'):
        employee.management_level = emp_data['management_level']
    if emp_data.get('country'):
        employee.country = emp_data['country']
    if emp_data.get('hire_date'):
        employee.hire_date = emp_data['hire_date']
    if emp_data.get('time_in_job_profile'):
        employee.time_in_job_profile = emp_data['time_in_job_profile']
    if emp_data.get('last_perf_review_name'):
        employee.last_perf_review_name = emp_data['last_perf_review_name']
    if emp_data.get('last_perf_review_rating'):
        employee.last_perf_review_rating = emp_data['last_perf_review_rating']

    # ─── Manager-input fields (preserve if modified locally) ───────────

    # Convert tenet names to JSON IDs for storage
    imported_strengths = convert_tenet_names_to_ids_fn(
        notes_data.get('tenets_strengths'), tenets_config
    )
    imported_improvements = convert_tenet_names_to_ids_fn(
        notes_data.get('tenets_improvements'), tenets_config
    )

    # Performance rating: unmodified means current == original
    new_rating = notes_data.get('performance_rating')
    old_rating = employee.performance_rating_percent
    if employee.performance_rating_percent == employee.performance_rating_percent_original:
        # Unmodified locally - update from Workday
        if new_rating is not None:
            employee.performance_rating_percent = new_rating
        if old_rating != new_rating:
            emp_updates.append({
                'field': 'performance_rating_percent',
                'old': format_change_value(old_rating, 'performance_rating_percent'),
                'new': format_change_value(new_rating, 'performance_rating_percent'),
            })
        employee.performance_rating_percent_original = new_rating
    else:
        # Modified locally - only show conflict if local differs from workday
        if employee.performance_rating_percent != new_rating:
            emp_preserved.append({
                'field': 'performance_rating_percent',
                'local': format_change_value(employee.performance_rating_percent, 'performance_rating_percent'),
                'workday': format_change_value(new_rating, 'performance_rating_percent'),
            })
        employee.performance_rating_percent_original = new_rating

    # Justification
    new_justification = notes_data.get('justification') or ''
    old_justification = employee.justification
    if text_unmodified(employee.justification, employee.justification_original):
        employee.justification = new_justification
        employee.justification_original = new_justification
        if (old_justification or '') != (new_justification or ''):
            emp_updates.append({
                'field': 'justification',
                'old': format_change_value(old_justification, 'justification'),
                'new': format_change_value(new_justification, 'justification'),
            })
    else:
        # Only show conflict if local differs from workday
        if (employee.justification or '') != (new_justification or ''):
            emp_preserved.append({
                'field': 'justification',
                'local': format_change_value(employee.justification, 'justification'),
                'workday': format_change_value(new_justification, 'justification'),
            })
        employee.justification_original = new_justification

    # Mentor (use mentor_fields_equal to handle placeholders)
    new_mentor = notes_data.get('mentors') or ''
    old_mentor_b = employee.mentor
    if text_unmodified(employee.mentor, employee.mentor_original):
        employee.mentor = new_mentor
        employee.mentor_original = new_mentor
        if not mentor_fields_equal(old_mentor_b, new_mentor):
            emp_updates.append({
                'field': 'mentor',
                'old': format_change_value(old_mentor_b, 'mentor'),
                'new': format_change_value(new_mentor, 'mentor'),
            })
    else:
        # Only show conflict if local differs from workday (considering placeholders)
        if not mentor_fields_equal(employee.mentor, new_mentor):
            emp_preserved.append({
                'field': 'mentor',
                'local': format_change_value(employee.mentor, 'mentor'),
                'workday': format_change_value(new_mentor, 'mentor'),
            })
        employee.mentor_original = new_mentor

    # Mentees (use mentor_fields_equal to handle placeholders)
    new_mentees = notes_data.get('mentees') or ''
    old_mentees_b = employee.mentees
    if text_unmodified(employee.mentees, employee.mentees_original):
        employee.mentees = new_mentees
        employee.mentees_original = new_mentees
        if not mentor_fields_equal(old_mentees_b, new_mentees):
            emp_updates.append({
                'field': 'mentees',
                'old': format_change_value(old_mentees_b, 'mentees'),
                'new': format_change_value(new_mentees, 'mentees'),
            })
    else:
        # Only show conflict if local differs from workday (considering placeholders)
        if not mentor_fields_equal(employee.mentees, new_mentees):
            emp_preserved.append({
                'field': 'mentees',
                'local': format_change_value(employee.mentees, 'mentees'),
                'workday': format_change_value(new_mentees, 'mentees'),
            })
        employee.mentees_original = new_mentees

    # Tenets Strengths (JSON arrays)
    old_strengths_b = employee.tenets_strengths
    if tenets_unmodified(employee.tenets_strengths, employee.tenets_strengths_original):
        employee.tenets_strengths = imported_strengths
        employee.tenets_strengths_original = imported_strengths
        if not tenets_unmodified(old_strengths_b, imported_strengths):
            emp_updates.append({
                'field': 'tenets_strengths',
                'old': format_change_value(
                    json.dumps(old_strengths_b) if old_strengths_b else None,
                    'tenets_strengths',
                ),
                'new': format_change_value(
                    json.dumps(imported_strengths) if imported_strengths else None,
                    'tenets_strengths',
                ),
            })
    else:
        # Only show conflict if local differs from workday
        if not tenets_unmodified(employee.tenets_strengths, imported_strengths):
            emp_preserved.append({
                'field': 'tenets_strengths',
                'local': format_change_value(
                    json.dumps(employee.tenets_strengths) if employee.tenets_strengths else None,
                    'tenets_strengths',
                ),
                'workday': format_change_value(
                    json.dumps(imported_strengths) if imported_strengths else None,
                    'tenets_strengths',
                ),
            })
        employee.tenets_strengths_original = imported_strengths

    # Tenets Improvements (JSON arrays)
    old_improvements_b = employee.tenets_improvements
    if tenets_unmodified(employee.tenets_improvements, employee.tenets_improvements_original):
        employee.tenets_improvements = imported_improvements
        employee.tenets_improvements_original = imported_improvements
        if not tenets_unmodified(old_improvements_b, imported_improvements):
            emp_updates.append({
                'field': 'tenets_improvements',
                'old': format_change_value(
                    json.dumps(old_improvements_b) if old_improvements_b else None,
                    'tenets_improvements',
                ),
                'new': format_change_value(
                    json.dumps(imported_improvements) if imported_improvements else None,
                    'tenets_improvements',
                ),
            })
    else:
        # Only show conflict if local differs from workday
        if not tenets_unmodified(employee.tenets_improvements, imported_improvements):
            emp_preserved.append({
                'field': 'tenets_improvements',
                'local': format_change_value(
                    json.dumps(employee.tenets_improvements) if employee.tenets_improvements else None,
                    'tenets_improvements',
                ),
                'workday': format_change_value(
                    json.dumps(imported_improvements) if imported_improvements else None,
                    'tenets_improvements',
                ),
            })
        employee.tenets_improvements_original = imported_improvements

    # Bonus override (special case) - only update if currently not set locally
    new_override = notes_data.get('bonus_override_percent')
    new_notes = notes_data.get('special_case_notes')
    if employee.bonus_override_percent is None and new_override is not None:
        employee.bonus_override_percent = new_override
    if employee.special_case_notes is None and new_notes:
        employee.special_case_notes = new_notes

    return emp_preserved, emp_updates


def apply_bonus_import_new(employee, emp_data, notes_data, tenets_config,
                           convert_tenet_names_to_ids_fn):
    """Apply bonus import data to a NEW employee (first import).

    Sets all bonus fields directly from import data without
    preservation logic. Handles both Workday-sourced fields and
    manager-entered fields parsed from the Notes column.

    Args:
        employee: SQLAlchemy Employee ORM object (new, not yet in DB)
        emp_data: Dict of parsed row data from Workday XLSX
        notes_data: Dict from parse_notes_field() with extracted fields
        tenets_config: Tenets configuration dict (or None)
        convert_tenet_names_to_ids_fn: Callable(names_str, tenets_config)
    """
    # ─── Workday-sourced fields ────────────────────────────────────────
    employee.photo = emp_data.get('photo', '')
    employee.errors = emp_data.get('errors', '')
    employee.current_base_pay_all_countries = emp_data.get('current_base_pay_all_countries')
    employee.current_base_pay_manager_currency = emp_data.get('current_base_pay_manager_currency')
    employee.currency = emp_data.get('currency', '')
    employee.grade = emp_data.get('grade', '')
    employee.annual_bonus_target_percent = emp_data.get('annual_bonus_target_percent')
    employee.last_bonus_allocation_percent = emp_data.get('last_bonus_allocation_percent')
    employee.bonus_target_local_currency = emp_data.get('bonus_target_local_currency')
    employee.bonus_target_manager_currency = emp_data.get('bonus_target_manager_currency')
    employee.proposed_bonus_amount = emp_data.get('proposed_bonus_amount')
    employee.proposed_bonus_amount_manager_currency = emp_data.get('proposed_bonus_amount_manager_currency')
    employee.proposed_percent_of_target_bonus = emp_data.get('proposed_percent_of_target_bonus')
    employee.notes = emp_data.get('notes', '')
    employee.zero_bonus_allocated = emp_data.get('zero_bonus_allocated', '')

    # New fields from 2025 Workday format (only set if present)
    if emp_data.get('management_level'):
        employee.management_level = emp_data['management_level']
    if emp_data.get('country'):
        employee.country = emp_data['country']
    if emp_data.get('hire_date'):
        employee.hire_date = emp_data['hire_date']
    if emp_data.get('time_in_job_profile'):
        employee.time_in_job_profile = emp_data['time_in_job_profile']
    if emp_data.get('last_perf_review_name'):
        employee.last_perf_review_name = emp_data['last_perf_review_name']
    if emp_data.get('last_perf_review_rating'):
        employee.last_perf_review_rating = emp_data['last_perf_review_rating']

    # ─── Manager-input fields (from Notes) ─────────────────────────────
    imported_strengths = convert_tenet_names_to_ids_fn(
        notes_data.get('tenets_strengths'), tenets_config
    )
    imported_improvements = convert_tenet_names_to_ids_fn(
        notes_data.get('tenets_improvements'), tenets_config
    )

    # Set _original fields from Workday data for modification tracking
    employee.performance_rating_percent_original = notes_data.get('performance_rating')
    employee.justification_original = notes_data.get('justification') or None
    employee.mentor_original = notes_data.get('mentors') or None
    employee.mentees_original = notes_data.get('mentees') or None
    employee.tenets_strengths_original = imported_strengths
    employee.tenets_improvements_original = imported_improvements

    if notes_data.get('performance_rating') is not None:
        employee.performance_rating_percent = notes_data.get('performance_rating')
        employee.justification = notes_data.get('justification') or ''
        employee.mentor = notes_data.get('mentors') or ''
        employee.mentees = notes_data.get('mentees') or ''
        employee.tenets_strengths = imported_strengths
        employee.tenets_improvements = imported_improvements
    else:
        employee.performance_rating_percent = None
        employee.tenets_strengths = None
        employee.tenets_improvements = None
        employee.justification = ''
        employee.mentor = ''
        employee.mentees = ''

    # Bonus override (special case) for new employees
    employee.bonus_override_percent = notes_data.get('bonus_override_percent')
    employee.special_case_notes = notes_data.get('special_case_notes')

    employee.last_updated = None
