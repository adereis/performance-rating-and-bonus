"""Import blueprint: Workday XLSX upload, analysis, and apply.

Routes: /import, /api/import/analyze, /api/import/current, /api/import/historical.

Moved verbatim from app.py (docs/REFACTOR_APP_SPLIT.md, Phase 4). The demo
flag is read as demo_mode.DEMO_MODE, get_db via the models module, and
load_tenets_config via the db_helpers module (all resolved at call time so
test fixtures patching them are honored, and no module imports `app`).
"""
import os
import json
import tempfile
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify

import demo_mode
import models
from models import Employee, BonusSettings, Period, RatingSnapshot

from xlsx_utils import analyze_xlsx, parse_xlsx_employees
from notes_parser import parse_notes_field

from services import db_helpers
from services.db_helpers import (
    get_all_employees, get_filter_params, apply_employee_filters,
    convert_tenet_names_to_ids,
)
from services.employee_utils import (
    normalize_mentor_field, normalize_movement_readiness,
)
from services.import_handler import (
    text_unmodified, json_string_unmodified, mentor_fields_equal,
    update_text_field, update_mentor_field, update_json_field,
)

import_bp = Blueprint('import_', __name__)


# Maps database field names to user-friendly labels
BONUS_FIELD_DISPLAY_NAMES = {
    'performance_rating_percent': 'Performance Rating',
    'justification': 'Justification',
    'mentor': 'Mentor',
    'mentees': 'Mentees',
    'tenets_strengths': 'Tenet Strengths',
    'tenets_improvements': 'Tenet Improvements',
    'current_base_pay_manager_currency': 'Base Salary',
    'bonus_target_manager_currency': 'Bonus Target',
    'supervisory_organization': 'Team',
    'current_job_profile': 'Job Profile',
    'grade': 'Grade',
    'management_level': 'Management Level',
}

TALENT_FIELD_DISPLAY_NAMES = {
    'talent_perf_what': 'Performance: What',
    'talent_perf_how': 'Performance: How',
    'talent_growth_agility': 'Growth Agility',
    'talent_change_agility': 'Change Agility',
    'talent_movement_readiness': 'Movement Readiness',
    'talent_proposed_actions': 'Proposed Actions',
    'talent_mentor': 'Mentor',
    'talent_mentees': 'Mentees',
    'talent_tenets_strengths': 'Tenet Strengths',
    'talent_tenets_improvements': 'Tenet Improvements',
    'management_level': 'Management Level',
    'supervisory_organization': 'Team',
    'current_job_profile': 'Job Profile',
}


@import_bp.route('/import')
def import_page():
    """Import data page."""
    # Get filter info so the filter panel can be populated (for pre-navigation filtering)
    filter_params = get_filter_params()
    all_employees = get_all_employees()
    _, filter_info = apply_employee_filters(all_employees, filter_params)

    return render_template('import.html', demo_mode=demo_mode.DEMO_MODE, filter_info=filter_info)


@import_bp.route('/api/import/analyze', methods=['POST'])
def analyze_import():
    """
    Analyze an uploaded XLSX file and return metadata.

    Returns counts of employees, whether bonus column exists,
    and checks if the period already exists (for historical imports).
    """
    if demo_mode.DEMO_MODE:
        return jsonify({'success': False, 'error': 'Imports are disabled in demo mode'}), 403

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

    # Unique, unpredictable name avoids collisions between concurrent uploads
    # and symlink/TOCTOU races from a guessable path.
    fd, temp_path = tempfile.mkstemp(dir=temp_dir, prefix='import_analyze_', suffix='.xlsx')
    os.close(fd)  # only the path is needed; file.save reopens it
    try:
        file.save(temp_path)

        # Analyze the file
        analysis = analyze_xlsx(temp_path)

        if not analysis['success']:
            return jsonify({'success': False, 'error': analysis.get('error', 'Analysis failed')}), 400

        result = {
            'success': True,
            'employee_count': analysis['employee_count'],
            'spreadsheet_type': analysis.get('spreadsheet_type', 'bonus'),
            'has_bonus_column': analysis['has_bonus_column'],
            'notes_count': analysis['notes_count'],
            'allocation_count': analysis.get('allocation_count', 0),
            'employees_with_allocations': analysis.get('employees_with_allocations', []),
            'metadata': analysis.get('metadata', {}),
            'import_detection': analysis.get('import_detection', {}),
            'period_exists': False,
            'existing_count': 0,
            'period_id': None
        }

        # For historical imports, check if period exists
        if import_type == 'historical' and period_id:
            db = models.get_db()
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


@import_bp.route('/api/import/current', methods=['POST'])
def import_current():
    """
    Import XLSX as current period data.

    Updates the Employee table with fresh Workday data.
    Preserves existing ratings and justifications unless clear_existing is set.
    """
    if demo_mode.DEMO_MODE:
        return jsonify({'success': False, 'error': 'Imports are disabled in demo mode'}), 403

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    clear_existing = request.form.get('clear_existing', '').lower() == 'true'

    # Save to temp file
    temp_dir = os.path.expanduser('~/tmp')
    os.makedirs(temp_dir, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(dir=temp_dir, prefix='import_current_', suffix='.xlsx')
    os.close(fd)  # only the path is needed; file.save reopens it
    try:
        file.save(temp_path)

        # Analyze the file to get metadata and spreadsheet type
        analysis = analyze_xlsx(temp_path)
        if not analysis.get('success'):
            return jsonify({'success': False, 'error': analysis.get('error', 'Analysis failed')}), 400

        spreadsheet_type = analysis.get('spreadsheet_type', 'bonus')
        workday_pool = None
        manager_currency = None
        if analysis.get('metadata'):
            workday_pool = analysis['metadata'].get('total_pool')

        # Parse the file using appropriate parser based on type
        parsed_metadata = {}  # Initialize for talent files (which don't return metadata)
        if spreadsheet_type == 'talent':
            from xlsx_utils import parse_talent_xlsx_employees
            success, employees, error = parse_talent_xlsx_employees(temp_path)
        else:
            success, employees, error, parsed_metadata = parse_xlsx_employees(temp_path)
            # Use calculated total_pool from parsing if not in analysis metadata
            if not workday_pool and parsed_metadata.get('total_pool'):
                workday_pool = parsed_metadata['total_pool']

        if not success:
            return jsonify({'success': False, 'error': error}), 400

        # Validate Overall Performance derivation for talent imports
        derivation_mismatches = []
        if spreadsheet_type == 'talent':
            from models import derive_overall_performance, derive_future_talent
            for emp_data in employees:
                imported_what = emp_data.get('talent_perf_what')
                imported_how = emp_data.get('talent_perf_how')
                imported_overall = emp_data.get('talent_overall_perf')

                # Only validate if all three fields are present
                if imported_what and imported_how and imported_overall:
                    derived_overall = derive_overall_performance(imported_what, imported_how)
                    if derived_overall and derived_overall != imported_overall:
                        derivation_mismatches.append({
                            'associate': emp_data.get('associate'),
                            'associate_id': emp_data.get('associate_id'),
                            'what': imported_what,
                            'how': imported_how,
                            'imported': imported_overall,
                            'expected': derived_overall
                        })

        db = models.get_db()
        try:
            # Clear existing employees if requested
            cleared = 0
            if clear_existing:
                cleared = db.query(Employee).count()
                db.query(Employee).delete()

            # Store Workday pool and manager currency in BonusSettings
            if workday_pool is not None or manager_currency is not None:
                settings = db.query(BonusSettings).first()
                if not settings:
                    settings = BonusSettings()
                    db.add(settings)
                if workday_pool is not None:
                    settings.workday_pool = workday_pool
                # Track pool source for verification warning
                pool_source = parsed_metadata.get('pool_source', 'calculated_sum')
                settings.pool_source = pool_source
                # Auto-verify if pool came from Workday metadata; require verification if calculated
                settings.pool_verified = (pool_source == 'workday_metadata')
                if manager_currency is not None:
                    settings.manager_currency = manager_currency
                settings.last_updated = datetime.now()

            imported = 0
            tenet_warnings = []  # Collect unrecognized tenet names for warnings

            # For bonus imports, clear cycle membership so only employees
            # in this spreadsheet will appear on /rate
            if spreadsheet_type == 'bonus':
                db.query(Employee).update({Employee.in_current_bonus_cycle: False})

            # Track changes for import change log
            import_changes = {
                'new': [],       # {associate_id, associate, org, job_profile}
                'updated': [],   # {associate_id, associate, changes: [{field, old, new}]}
                'preserved': []  # {associate_id, associate, conflicts: [{field, local, workday}]}
            }

            def format_change_value(value, field_name):
                """Format a value for display in change log."""
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

            for emp_data in employees:
                associate_id = emp_data['associate_id']

                # Check if employee exists
                existing = db.query(Employee).filter(Employee.associate_id == associate_id).first()

                if existing:
                    employee = existing
                    # Track changes for this existing employee (updated count computed at end)
                    emp_updates = []
                    emp_preserved = []
                    # Track if Workday-sourced fields changed (for accurate update count)
                    workday_fields_changed = (
                        employee.associate != emp_data['associate'] or
                        employee.supervisory_organization != emp_data['supervisory_organization'] or
                        employee.current_job_profile != emp_data['current_job_profile']
                    )
                else:
                    employee = Employee(associate_id=associate_id)
                    imported += 1
                    workday_fields_changed = False  # Not applicable for new employees
                    # Track new employee
                    import_changes['new'].append({
                        'associate_id': associate_id,
                        'associate': emp_data['associate'],
                        'org': emp_data.get('supervisory_organization', ''),
                        'job_profile': emp_data.get('current_job_profile', '')
                    })

                # Update common fields
                employee.associate = emp_data['associate']
                employee.supervisory_organization = emp_data['supervisory_organization']
                employee.current_job_profile = emp_data['current_job_profile']

                if spreadsheet_type == 'talent':
                    # Update Workday-sourced fields (always overwrite from Workday)
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

                    # Manager-input fields: ONLY set for new employees (per Spec §5.3)
                    # These are preserved on re-import to prevent data loss
                    if not existing:
                        # Set _original fields from Workday data for modification tracking
                        # These reflect what Workday has, so we can detect local changes
                        # NOTE: For existing employees, _original fields are set individually
                        # AFTER comparison in the else branch below. Setting them here would
                        # break text_unmodified() checks (current vs new instead of current vs old).
                        employee.talent_perf_what_original = emp_data.get('talent_perf_what')
                        employee.talent_perf_how_original = emp_data.get('talent_perf_how')
                        employee.talent_growth_agility_original = emp_data.get('talent_growth_agility')
                        employee.talent_change_agility_original = emp_data.get('talent_change_agility')
                        employee.talent_movement_readiness_original = emp_data.get('talent_movement_readiness')
                        employee.talent_proposed_actions_original = emp_data.get('talent_proposed_actions')

                        # Performance Assessment (manager-entered)
                        employee.talent_perf_what = emp_data.get('talent_perf_what')
                        employee.talent_perf_how = emp_data.get('talent_perf_how')
                        # Use file value if present, otherwise derive from What + How
                        employee.talent_overall_perf = (
                            emp_data.get('talent_overall_perf')
                            or derive_overall_performance(employee.talent_perf_what, employee.talent_perf_how)
                        )

                        # Future Talent (manager-entered)
                        employee.talent_growth_agility = emp_data.get('talent_growth_agility')
                        employee.talent_change_agility = emp_data.get('talent_change_agility')
                        # Use file value if present, otherwise derive from agility fields
                        employee.talent_identified_future = (
                            emp_data.get('talent_identified_future')
                            if emp_data.get('talent_identified_future') is not None
                            else derive_future_talent(employee.talent_growth_agility, employee.talent_change_agility)
                        )

                        # Movement & Career (manager-entered)
                        employee.talent_movement_readiness = emp_data.get('talent_movement_readiness')

                        # Parse tenets and mentor/mentees from Proposed Actions if present
                        # Format: [Strengths: Tenet1; Tenet2] [Improvements: Tenet3] [Mentor: Name] [Mentees: A; B]
                        raw_proposed_actions = emp_data.get('talent_proposed_actions') or ''
                        tenets_config, _ = db_helpers.load_tenets_config()

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

                        # Promotion (manager-entered) - handle [MODIFIED] marker for our exports
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
                    else:
                        # EXISTING employee in talent import: update fields based on local modification status
                        # - If unmodified locally (current == _original): update from Workday
                        # - If modified locally (current != _original): preserve local, update _original to show conflict

                        # Helper to check if text field is unmodified (handles None vs empty string)
                        def text_unmodified(current, original):
                            return (current or '') == (original or '')

                        # Helper to check if JSON string field is unmodified
                        def json_string_unmodified(current, original):
                            try:
                                curr_parsed = json.loads(current) if current else []
                                orig_parsed = json.loads(original) if original else []
                                return sorted(curr_parsed) == sorted(orig_parsed)
                            except (json.JSONDecodeError, TypeError):
                                # If not valid JSON, fall back to string comparison
                                return (current or '') == (original or '')

                        # Helper to compare mentor/mentee fields (normalizes placeholders like "None", "TBD" to empty)
                        def mentor_fields_equal(val1, val2):
                            norm1, _ = normalize_mentor_field(val1)
                            norm2, _ = normalize_mentor_field(val2)
                            return norm1 == norm2

                        # Performance What
                        new_perf_what = emp_data.get('talent_perf_what')
                        old_perf_what = employee.talent_perf_what
                        if text_unmodified(employee.talent_perf_what, employee.talent_perf_what_original):
                            employee.talent_perf_what = new_perf_what
                            if (old_perf_what or '') != (new_perf_what or ''):
                                emp_updates.append({'field': 'talent_perf_what', 'old': format_change_value(old_perf_what, 'talent_perf_what'), 'new': format_change_value(new_perf_what, 'talent_perf_what')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.talent_perf_what or '') != (new_perf_what or ''):
                                emp_preserved.append({'field': 'talent_perf_what', 'local': format_change_value(employee.talent_perf_what, 'talent_perf_what'), 'workday': format_change_value(new_perf_what, 'talent_perf_what')})
                        employee.talent_perf_what_original = new_perf_what

                        # Performance How
                        new_perf_how = emp_data.get('talent_perf_how')
                        old_perf_how = employee.talent_perf_how
                        if text_unmodified(employee.talent_perf_how, employee.talent_perf_how_original):
                            employee.talent_perf_how = new_perf_how
                            if (old_perf_how or '') != (new_perf_how or ''):
                                emp_updates.append({'field': 'talent_perf_how', 'old': format_change_value(old_perf_how, 'talent_perf_how'), 'new': format_change_value(new_perf_how, 'talent_perf_how')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.talent_perf_how or '') != (new_perf_how or ''):
                                emp_preserved.append({'field': 'talent_perf_how', 'local': format_change_value(employee.talent_perf_how, 'talent_perf_how'), 'workday': format_change_value(new_perf_how, 'talent_perf_how')})
                        employee.talent_perf_how_original = new_perf_how

                        # Growth Agility
                        new_growth = emp_data.get('talent_growth_agility')
                        old_growth = employee.talent_growth_agility
                        if text_unmodified(employee.talent_growth_agility, employee.talent_growth_agility_original):
                            employee.talent_growth_agility = new_growth
                            if (old_growth or '') != (new_growth or ''):
                                emp_updates.append({'field': 'talent_growth_agility', 'old': format_change_value(old_growth, 'talent_growth_agility'), 'new': format_change_value(new_growth, 'talent_growth_agility')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.talent_growth_agility or '') != (new_growth or ''):
                                emp_preserved.append({'field': 'talent_growth_agility', 'local': format_change_value(employee.talent_growth_agility, 'talent_growth_agility'), 'workday': format_change_value(new_growth, 'talent_growth_agility')})
                        employee.talent_growth_agility_original = new_growth

                        # Change Agility
                        new_change = emp_data.get('talent_change_agility')
                        old_change = employee.talent_change_agility
                        if text_unmodified(employee.talent_change_agility, employee.talent_change_agility_original):
                            employee.talent_change_agility = new_change
                            if (old_change or '') != (new_change or ''):
                                emp_updates.append({'field': 'talent_change_agility', 'old': format_change_value(old_change, 'talent_change_agility'), 'new': format_change_value(new_change, 'talent_change_agility')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.talent_change_agility or '') != (new_change or ''):
                                emp_preserved.append({'field': 'talent_change_agility', 'local': format_change_value(employee.talent_change_agility, 'talent_change_agility'), 'workday': format_change_value(new_change, 'talent_change_agility')})
                        employee.talent_change_agility_original = new_change

                        # Movement Readiness (uses normalize function)
                        new_movement = normalize_movement_readiness(emp_data.get('talent_movement_readiness'))
                        old_movement = employee.talent_movement_readiness
                        if text_unmodified(employee.talent_movement_readiness, employee.talent_movement_readiness_original):
                            employee.talent_movement_readiness = new_movement
                            if (old_movement or '') != (new_movement or ''):
                                emp_updates.append({'field': 'talent_movement_readiness', 'old': format_change_value(old_movement, 'talent_movement_readiness'), 'new': format_change_value(new_movement, 'talent_movement_readiness')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.talent_movement_readiness or '') != (new_movement or ''):
                                emp_preserved.append({'field': 'talent_movement_readiness', 'local': format_change_value(employee.talent_movement_readiness, 'talent_movement_readiness'), 'workday': format_change_value(new_movement, 'talent_movement_readiness')})
                        employee.talent_movement_readiness_original = new_movement

                        # Tool additions fields - parse from Workday's proposed_actions
                        raw_proposed_actions = emp_data.get('talent_proposed_actions') or ''
                        tenets_config, _ = db_helpers.load_tenets_config()
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
                        old_actions = employee.talent_proposed_actions
                        if text_unmodified(employee.talent_proposed_actions, employee.talent_proposed_actions_original):
                            employee.talent_proposed_actions = new_actions
                            if (old_actions or '') != (new_actions or ''):
                                emp_updates.append({'field': 'talent_proposed_actions', 'old': format_change_value(old_actions, 'talent_proposed_actions'), 'new': format_change_value(new_actions, 'talent_proposed_actions')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.talent_proposed_actions or '') != (new_actions or ''):
                                emp_preserved.append({'field': 'talent_proposed_actions', 'local': format_change_value(employee.talent_proposed_actions, 'talent_proposed_actions'), 'workday': format_change_value(new_actions, 'talent_proposed_actions')})
                        employee.talent_proposed_actions_original = new_actions

                        # Talent Tenets Strengths (JSON string)
                        old_strengths = employee.talent_tenets_strengths
                        if json_string_unmodified(employee.talent_tenets_strengths, employee.talent_tenets_strengths_original):
                            employee.talent_tenets_strengths = new_strengths
                            if (old_strengths or '') != (new_strengths or ''):
                                emp_updates.append({'field': 'talent_tenets_strengths', 'old': format_change_value(old_strengths, 'talent_tenets_strengths'), 'new': format_change_value(new_strengths, 'talent_tenets_strengths')})
                        else:
                            # Only show conflict if local differs from workday
                            if not json_string_unmodified(employee.talent_tenets_strengths, new_strengths):
                                emp_preserved.append({'field': 'talent_tenets_strengths', 'local': format_change_value(employee.talent_tenets_strengths, 'talent_tenets_strengths'), 'workday': format_change_value(new_strengths, 'talent_tenets_strengths')})
                        employee.talent_tenets_strengths_original = new_strengths

                        # Talent Tenets Improvements (JSON string)
                        old_improvements = employee.talent_tenets_improvements
                        if json_string_unmodified(employee.talent_tenets_improvements, employee.talent_tenets_improvements_original):
                            employee.talent_tenets_improvements = new_improvements
                            if (old_improvements or '') != (new_improvements or ''):
                                emp_updates.append({'field': 'talent_tenets_improvements', 'old': format_change_value(old_improvements, 'talent_tenets_improvements'), 'new': format_change_value(new_improvements, 'talent_tenets_improvements')})
                        else:
                            # Only show conflict if local differs from workday
                            if not json_string_unmodified(employee.talent_tenets_improvements, new_improvements):
                                emp_preserved.append({'field': 'talent_tenets_improvements', 'local': format_change_value(employee.talent_tenets_improvements, 'talent_tenets_improvements'), 'workday': format_change_value(new_improvements, 'talent_tenets_improvements')})
                        employee.talent_tenets_improvements_original = new_improvements

                        # Talent Mentor (use mentor_fields_equal to handle placeholders like "None", "TBD")
                        old_mentor_t = employee.talent_mentor
                        if text_unmodified(employee.talent_mentor, employee.talent_mentor_original):
                            employee.talent_mentor = new_mentor
                            if not mentor_fields_equal(old_mentor_t, new_mentor):
                                emp_updates.append({'field': 'talent_mentor', 'old': format_change_value(old_mentor_t, 'talent_mentor'), 'new': format_change_value(new_mentor, 'talent_mentor')})
                        else:
                            # Only show conflict if local differs from workday (considering placeholders)
                            if not mentor_fields_equal(employee.talent_mentor, new_mentor):
                                emp_preserved.append({'field': 'talent_mentor', 'local': format_change_value(employee.talent_mentor, 'talent_mentor'), 'workday': format_change_value(new_mentor, 'talent_mentor')})
                        employee.talent_mentor_original = new_mentor

                        # Talent Mentees (use mentor_fields_equal to handle placeholders like "None", "TBD")
                        old_mentees_t = employee.talent_mentees
                        if text_unmodified(employee.talent_mentees, employee.talent_mentees_original):
                            employee.talent_mentees = new_mentees
                            if not mentor_fields_equal(old_mentees_t, new_mentees):
                                emp_updates.append({'field': 'talent_mentees', 'old': format_change_value(old_mentees_t, 'talent_mentees'), 'new': format_change_value(new_mentees, 'talent_mentees')})
                        else:
                            # Only show conflict if local differs from workday (considering placeholders)
                            if not mentor_fields_equal(employee.talent_mentees, new_mentees):
                                emp_preserved.append({'field': 'talent_mentees', 'local': format_change_value(employee.talent_mentees, 'talent_mentees'), 'workday': format_change_value(new_mentees, 'talent_mentees')})
                        employee.talent_mentees_original = new_mentees

                        # Derive computed fields from updated What/How and agility values
                        employee.talent_overall_perf = derive_overall_performance(
                            employee.talent_perf_what, employee.talent_perf_how
                        )
                        employee.talent_identified_future = derive_future_talent(
                            employee.talent_growth_agility, employee.talent_change_agility
                        )

                        # Aggregate per-employee changes for existing talent employees
                        if emp_updates or workday_fields_changed:
                            import_changes['updated'].append({
                                'associate_id': associate_id,
                                'associate': emp_data['associate'],
                                'changes': emp_updates
                            })
                        if emp_preserved:
                            import_changes['preserved'].append({
                                'associate_id': associate_id,
                                'associate': emp_data['associate'],
                                'conflicts': emp_preserved
                            })
                elif spreadsheet_type != 'talent':
                    # Update bonus-specific fields
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
                    # New fields from 2025 Workday format
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

                if spreadsheet_type == 'bonus':
                    employee.in_current_bonus_cycle = True

                # Parse Notes field for bonus imports (both new and existing employees)
                # This sets _original fields for modification tracking
                if spreadsheet_type != 'talent':
                    notes_data = parse_notes_field(emp_data.get('notes', ''))
                    tenets_config, _ = db_helpers.load_tenets_config()

                    # Convert tenet names to JSON IDs for storage (needed for both new and existing)
                    imported_strengths = convert_tenet_names_to_ids(
                        notes_data.get('tenets_strengths'), tenets_config
                    )
                    imported_improvements = convert_tenet_names_to_ids(
                        notes_data.get('tenets_improvements'), tenets_config
                    )

                    # Track per-employee changes for change log
                    emp_updates = []    # Fields updated from Workday
                    emp_preserved = []  # Fields preserved locally (conflicts)

                    # For existing employees: update fields based on local modification status
                    # - If unmodified locally (current == _original): update from Workday
                    # - If modified locally (current != _original): preserve local, update _original to show conflict
                    if existing:
                        new_rating = notes_data.get('performance_rating')
                        old_rating = employee.performance_rating_percent
                        # Performance rating: unmodified means current == original
                        if employee.performance_rating_percent == employee.performance_rating_percent_original:
                            # Unmodified locally - update from Workday
                            if new_rating is not None:
                                employee.performance_rating_percent = new_rating
                            if old_rating != new_rating:
                                emp_updates.append({'field': 'performance_rating_percent', 'old': format_change_value(old_rating, 'performance_rating_percent'), 'new': format_change_value(new_rating, 'performance_rating_percent')})
                            employee.performance_rating_percent_original = new_rating
                        else:
                            # Modified locally - only show conflict if local differs from workday
                            if employee.performance_rating_percent != new_rating:
                                emp_preserved.append({'field': 'performance_rating_percent', 'local': format_change_value(employee.performance_rating_percent, 'performance_rating_percent'), 'workday': format_change_value(new_rating, 'performance_rating_percent')})
                            employee.performance_rating_percent_original = new_rating

                        # Helper to check if text field is unmodified (handles None vs empty string)
                        def text_unmodified(current, original):
                            return (current or '') == (original or '')

                        # Helper to compare mentor/mentee fields (normalizes placeholders like "None", "TBD" to empty)
                        def mentor_fields_equal(val1, val2):
                            norm1, _ = normalize_mentor_field(val1)
                            norm2, _ = normalize_mentor_field(val2)
                            return norm1 == norm2

                        # Justification
                        new_justification = notes_data.get('justification') or ''
                        old_justification = employee.justification
                        if text_unmodified(employee.justification, employee.justification_original):
                            employee.justification = new_justification
                            employee.justification_original = new_justification
                            if (old_justification or '') != (new_justification or ''):
                                emp_updates.append({'field': 'justification', 'old': format_change_value(old_justification, 'justification'), 'new': format_change_value(new_justification, 'justification')})
                        else:
                            # Only show conflict if local differs from workday
                            if (employee.justification or '') != (new_justification or ''):
                                emp_preserved.append({'field': 'justification', 'local': format_change_value(employee.justification, 'justification'), 'workday': format_change_value(new_justification, 'justification')})
                            employee.justification_original = new_justification

                        # Mentor (use mentor_fields_equal to handle placeholders like "None", "TBD")
                        new_mentor = notes_data.get('mentors') or ''
                        old_mentor_b = employee.mentor
                        if text_unmodified(employee.mentor, employee.mentor_original):
                            employee.mentor = new_mentor
                            employee.mentor_original = new_mentor
                            if not mentor_fields_equal(old_mentor_b, new_mentor):
                                emp_updates.append({'field': 'mentor', 'old': format_change_value(old_mentor_b, 'mentor'), 'new': format_change_value(new_mentor, 'mentor')})
                        else:
                            # Only show conflict if local differs from workday (considering placeholders)
                            if not mentor_fields_equal(employee.mentor, new_mentor):
                                emp_preserved.append({'field': 'mentor', 'local': format_change_value(employee.mentor, 'mentor'), 'workday': format_change_value(new_mentor, 'mentor')})
                            employee.mentor_original = new_mentor

                        # Mentees (use mentor_fields_equal to handle placeholders like "None", "TBD")
                        new_mentees = notes_data.get('mentees') or ''
                        old_mentees_b = employee.mentees
                        if text_unmodified(employee.mentees, employee.mentees_original):
                            employee.mentees = new_mentees
                            employee.mentees_original = new_mentees
                            if not mentor_fields_equal(old_mentees_b, new_mentees):
                                emp_updates.append({'field': 'mentees', 'old': format_change_value(old_mentees_b, 'mentees'), 'new': format_change_value(new_mentees, 'mentees')})
                        else:
                            # Only show conflict if local differs from workday (considering placeholders)
                            if not mentor_fields_equal(employee.mentees, new_mentees):
                                emp_preserved.append({'field': 'mentees', 'local': format_change_value(employee.mentees, 'mentees'), 'workday': format_change_value(new_mentees, 'mentees')})
                            employee.mentees_original = new_mentees

                        # Tenets (JSON arrays) - compare as JSON strings for equality
                        def tenets_unmodified(current, original):
                            curr_str = json.dumps(current, sort_keys=True) if current else '[]'
                            orig_str = json.dumps(original, sort_keys=True) if original else '[]'
                            return curr_str == orig_str

                        old_strengths_b = employee.tenets_strengths
                        if tenets_unmodified(employee.tenets_strengths, employee.tenets_strengths_original):
                            employee.tenets_strengths = imported_strengths
                            employee.tenets_strengths_original = imported_strengths
                            if not tenets_unmodified(old_strengths_b, imported_strengths):
                                emp_updates.append({'field': 'tenets_strengths', 'old': format_change_value(json.dumps(old_strengths_b) if old_strengths_b else None, 'tenets_strengths'), 'new': format_change_value(json.dumps(imported_strengths) if imported_strengths else None, 'tenets_strengths')})
                        else:
                            # Only show conflict if local differs from workday
                            if not tenets_unmodified(employee.tenets_strengths, imported_strengths):
                                emp_preserved.append({'field': 'tenets_strengths', 'local': format_change_value(json.dumps(employee.tenets_strengths) if employee.tenets_strengths else None, 'tenets_strengths'), 'workday': format_change_value(json.dumps(imported_strengths) if imported_strengths else None, 'tenets_strengths')})
                            employee.tenets_strengths_original = imported_strengths

                        old_improvements_b = employee.tenets_improvements
                        if tenets_unmodified(employee.tenets_improvements, employee.tenets_improvements_original):
                            employee.tenets_improvements = imported_improvements
                            employee.tenets_improvements_original = imported_improvements
                            if not tenets_unmodified(old_improvements_b, imported_improvements):
                                emp_updates.append({'field': 'tenets_improvements', 'old': format_change_value(json.dumps(old_improvements_b) if old_improvements_b else None, 'tenets_improvements'), 'new': format_change_value(json.dumps(imported_improvements) if imported_improvements else None, 'tenets_improvements')})
                        else:
                            # Only show conflict if local differs from workday
                            if not tenets_unmodified(employee.tenets_improvements, imported_improvements):
                                emp_preserved.append({'field': 'tenets_improvements', 'local': format_change_value(json.dumps(employee.tenets_improvements) if employee.tenets_improvements else None, 'tenets_improvements'), 'workday': format_change_value(json.dumps(imported_improvements) if imported_improvements else None, 'tenets_improvements')})
                            employee.tenets_improvements_original = imported_improvements

                        # Bonus override (special case) - only update if currently not set locally
                        # This preserves local changes but imports if we don't have a local value
                        new_override = notes_data.get('bonus_override_percent')
                        new_notes = notes_data.get('special_case_notes')
                        if employee.bonus_override_percent is None and new_override is not None:
                            employee.bonus_override_percent = new_override
                        if employee.special_case_notes is None and new_notes:
                            employee.special_case_notes = new_notes
                        employee.bonus_override_percent_original = new_override

                        # Aggregate per-employee changes for existing employees
                        # Count as updated if any field actually changed (manager-input OR Workday-sourced)
                        if emp_updates or workday_fields_changed:
                            import_changes['updated'].append({
                                'associate_id': associate_id,
                                'associate': emp_data['associate'],
                                'changes': emp_updates  # Only detailed changes for manager-input fields
                            })
                        if emp_preserved:
                            import_changes['preserved'].append({
                                'associate_id': associate_id,
                                'associate': emp_data['associate'],
                                'conflicts': emp_preserved
                            })

                    # Initialize manager input fields for new employees only
                    if not existing:
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
                        employee.bonus_override_percent_original = notes_data.get('bonus_override_percent')
                        employee.special_case_notes = notes_data.get('special_case_notes')
                        employee.last_updated = None
                        db.add(employee)
                elif not existing:
                    # Talent import for new employee
                    employee.last_updated = None
                    db.add(employee)

            db.commit()

            result = {
                'success': True,
                'imported': imported,
                'updated': len(import_changes['updated'])  # Only count records with actual changes
            }
            if clear_existing:
                result['cleared'] = cleared
            if derivation_mismatches:
                result['derivation_mismatches'] = derivation_mismatches
                result['derivation_mismatch_count'] = len(derivation_mismatches)
            # Include pool verification info for post-import modal (bonus imports only)
            pool_source = parsed_metadata.get('pool_source', 'calculated_sum')
            if spreadsheet_type != 'talent' and pool_source == 'calculated_sum' and workday_pool:
                result['pool_verification'] = {
                    'amount': workday_pool,
                    'source': pool_source,
                    'needs_verification': True,
                    'currency': manager_currency or 'USD'
                }

            # Add change log with field display names
            if import_changes['new'] or import_changes['updated'] or import_changes['preserved']:
                display_names = TALENT_FIELD_DISPLAY_NAMES if spreadsheet_type == 'talent' else BONUS_FIELD_DISPLAY_NAMES
                for item in import_changes['updated']:
                    for change in item['changes']:
                        change['field_display'] = display_names.get(change['field'], change['field'])
                for item in import_changes['preserved']:
                    for conflict in item['conflicts']:
                        conflict['field_display'] = display_names.get(conflict['field'], conflict['field'])
                result['changes'] = import_changes

            return jsonify(result)

        except Exception as e:
            db.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
        finally:
            db.close()

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@import_bp.route('/api/import/historical', methods=['POST'])
def import_historical():
    """
    Import XLSX as a historical period snapshot.

    Creates Period and RatingSnapshot records.
    Parses Notes field for rating data.
    """
    if demo_mode.DEMO_MODE:
        return jsonify({'success': False, 'error': 'Imports are disabled in demo mode'}), 403

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

    fd, temp_path = tempfile.mkstemp(dir=temp_dir, prefix='import_historical_', suffix='.xlsx')
    os.close(fd)  # only the path is needed; file.save reopens it
    try:
        file.save(temp_path)

        # Parse the file
        success, employees, error, parsed_metadata = parse_xlsx_employees(temp_path)
        if not success:
            return jsonify({'success': False, 'error': error}), 400

        db = models.get_db()
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

                # Prepare new field values
                new_values = {
                    'performance_rating': notes_data.get('performance_rating'),
                    'bonus_allocation': bonus_allocation,
                    'justification': notes_data.get('justification'),
                    'tenets_strengths': notes_data.get('tenets_strengths'),
                    'tenets_improvements': notes_data.get('tenets_improvements'),
                    'mentors': notes_data.get('mentors'),
                    'mentees': notes_data.get('mentees'),
                    'snapshot_name': emp_data['associate'],
                    'snapshot_org': emp_data['supervisory_organization'],
                    'snapshot_job_profile': emp_data['current_job_profile'],
                    'snapshot_bonus_target_manager_currency': emp_data.get('bonus_target_manager_currency') or emp_data.get('bonus_target_local_currency'),
                }

                # Check if snapshot exists
                existing = db.query(RatingSnapshot).filter(
                    RatingSnapshot.period_id == period_id,
                    RatingSnapshot.associate_id == associate_id
                ).first()

                if existing:
                    snapshot = existing
                    # Check if any field actually changed
                    has_changes = any(
                        getattr(snapshot, field) != value
                        for field, value in new_values.items()
                    )
                    if has_changes:
                        updated += 1
                else:
                    snapshot = RatingSnapshot(
                        period_id=period_id,
                        associate_id=associate_id
                    )
                    imported += 1

                # Update snapshot fields
                for field, value in new_values.items():
                    setattr(snapshot, field, value)

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

