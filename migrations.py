"""Database migration functions.

Run automatically by init_db() during application startup. Each
migration is idempotent (safe to run multiple times) and handles
schema changes that SQLAlchemy's create_all() can't manage
(column renames, data migrations).
"""
from sqlalchemy import text, inspect


def migrate_usd_columns(engine):
    """
    Migrate old *_usd column names to *_manager_currency.

    This handles databases created before the international manager currency
    support was added. SQLite 3.25.0+ supports ALTER TABLE RENAME COLUMN.
    """
    inspector = inspect(engine)

    # Define column renames: (table, old_name, new_name)
    renames = [
        ('employees', 'current_base_pay_all_countries_usd', 'current_base_pay_manager_currency'),
        ('employees', 'bonus_target_local_currency_usd', 'bonus_target_manager_currency'),
        ('employees', 'proposed_bonus_amount_usd', 'proposed_bonus_amount_manager_currency'),
        ('bonus_settings', 'budget_override_usd', 'budget_override'),
        ('rating_snapshots', 'snapshot_bonus_target_usd', 'snapshot_bonus_target_manager_currency'),
    ]

    with engine.connect() as conn:
        for table, old_col, new_col in renames:
            # Check if table exists
            if table not in inspector.get_table_names():
                continue

            # Get current columns
            columns = [col['name'] for col in inspector.get_columns(table)]

            # If old column exists and new doesn't, rename it
            if old_col in columns and new_col not in columns:
                print(f"Migrating column {table}.{old_col} → {new_col}")
                conn.execute(text(f'ALTER TABLE {table} RENAME COLUMN {old_col} TO {new_col}'))
                conn.commit()


def migrate_add_new_columns(engine):
    """
    Add new columns that were added in later versions.

    This handles databases created before new columns were added.
    """
    inspector = inspect(engine)

    # Define new columns: (table, column_name, column_type)
    new_columns = [
        ('bonus_settings', 'workday_pool', 'REAL'),
        ('bonus_settings', 'manager_currency', 'TEXT'),
        ('bonus_settings', 'pool_source', 'TEXT'),
        ('bonus_settings', 'pool_verified', 'BOOLEAN'),
        # Period table
        ('periods', 'cycle_type', 'TEXT'),
        # Employee table - Extended identity
        ('employees', 'management_level', 'TEXT'),
        ('employees', 'job_category', 'TEXT'),
        ('employees', 'hire_date', 'DATETIME'),
        ('employees', 'length_of_service', 'TEXT'),
        ('employees', 'time_in_job_profile', 'TEXT'),
        ('employees', 'region', 'TEXT'),
        ('employees', 'country', 'TEXT'),
        # Employee table - Talent: Performance Assessment
        ('employees', 'talent_perf_what', 'TEXT'),
        ('employees', 'talent_perf_how', 'TEXT'),
        ('employees', 'talent_overall_perf', 'TEXT'),
        ('employees', 'talent_last_overall_perf', 'TEXT'),
        # Employee table - Talent: Future Talent
        ('employees', 'talent_growth_agility', 'TEXT'),
        ('employees', 'talent_change_agility', 'TEXT'),
        ('employees', 'talent_identified_future', 'BOOLEAN'),
        ('employees', 'talent_last_identified_future', 'BOOLEAN'),
        # Employee table - Talent: Movement & Career
        ('employees', 'talent_movement_readiness', 'TEXT'),
        ('employees', 'talent_last_movement_readiness', 'TEXT'),
        ('employees', 'talent_proposed_actions', 'TEXT'),
        # Employee table - Talent: Promotion
        ('employees', 'talent_promo_job_profile', 'TEXT'),
        ('employees', 'talent_promo_business_need', 'TEXT'),
        ('employees', 'talent_promo_role_scope', 'TEXT'),
        ('employees', 'talent_promo_readiness', 'TEXT'),
        # Employee table - Talent: Tenets
        ('employees', 'talent_tenets_strengths', 'TEXT'),
        ('employees', 'talent_tenets_improvements', 'TEXT'),
        # Employee table - Talent: Metadata
        ('employees', 'talent_calibration_status', 'TEXT'),
        ('employees', 'talent_last_updated', 'DATETIME'),
        # RatingSnapshot table - Talent snapshot fields
        ('rating_snapshots', 'snapshot_talent_perf_what', 'TEXT'),
        ('rating_snapshots', 'snapshot_talent_perf_how', 'TEXT'),
        ('rating_snapshots', 'snapshot_talent_overall_perf', 'TEXT'),
        ('rating_snapshots', 'snapshot_talent_growth_agility', 'TEXT'),
        ('rating_snapshots', 'snapshot_talent_change_agility', 'TEXT'),
        ('rating_snapshots', 'snapshot_talent_movement_readiness', 'TEXT'),
        ('rating_snapshots', 'snapshot_talent_proposed_actions', 'TEXT'),
        ('rating_snapshots', 'snapshot_talent_promo_job_profile', 'TEXT'),
        ('rating_snapshots', 'snapshot_talent_tenets_strengths', 'TEXT'),
        ('rating_snapshots', 'snapshot_talent_tenets_improvements', 'TEXT'),
        # Talent Mentor/Mentees (separate from bonus cycle)
        ('employees', 'talent_mentor', 'TEXT'),
        ('employees', 'talent_mentees', 'TEXT'),
        ('rating_snapshots', 'snapshot_talent_mentor', 'TEXT'),
        ('rating_snapshots', 'snapshot_talent_mentees', 'TEXT'),
        # Original tracking for Bonus Cycle fields (rating, justification, mentor, mentees, tenets)
        ('employees', 'performance_rating_percent_original', 'REAL'),
        ('employees', 'justification_original', 'TEXT'),
        ('employees', 'mentor_original', 'TEXT'),
        ('employees', 'mentees_original', 'TEXT'),
        ('employees', 'tenets_strengths_original', 'TEXT'),
        ('employees', 'tenets_improvements_original', 'TEXT'),
        # Original tracking for Talent Calibration fields
        ('employees', 'talent_perf_what_original', 'TEXT'),
        ('employees', 'talent_perf_how_original', 'TEXT'),
        ('employees', 'talent_growth_agility_original', 'TEXT'),
        ('employees', 'talent_change_agility_original', 'TEXT'),
        ('employees', 'talent_movement_readiness_original', 'TEXT'),
        ('employees', 'talent_proposed_actions_original', 'TEXT'),
        ('employees', 'talent_promo_job_profile_original', 'TEXT'),
        ('employees', 'talent_promo_business_need_original', 'TEXT'),
        ('employees', 'talent_promo_role_scope_original', 'TEXT'),
        ('employees', 'talent_promo_readiness_original', 'TEXT'),
        # Original tracking for Tool Additions (tenets, mentor, mentees)
        ('employees', 'talent_mentor_original', 'TEXT'),
        ('employees', 'talent_mentees_original', 'TEXT'),
        ('employees', 'talent_tenets_strengths_original', 'TEXT'),
        ('employees', 'talent_tenets_improvements_original', 'TEXT'),
        # Historical performance reference (from bonus import)
        ('employees', 'last_perf_review_name', 'TEXT'),
        ('employees', 'last_perf_review_rating', 'TEXT'),
        # Special case handling (pro-rata leave, etc.)
        ('employees', 'bonus_override_percent', 'REAL'),
        ('employees', 'special_case_notes', 'TEXT'),
    ]

    with engine.connect() as conn:
        for table, col_name, col_type in new_columns:
            # Check if table exists
            if table not in inspector.get_table_names():
                continue

            # Get current columns
            columns = [col['name'] for col in inspector.get_columns(table)]

            # Add column if it doesn't exist
            if col_name not in columns:
                print(f"Adding column {table}.{col_name}")
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type}'))
                conn.commit()


def migrate_normalize_mentor_placeholders(engine):
    """
    Normalize placeholder values in mentor/mentee fields to empty strings.

    Cleans up entries like 'None', 'TBD', 'N/A', etc. that managers may have
    entered as placeholders. This is a one-time cleanup for existing data.
    """
    inspector = inspect(engine)

    # Skip if employees table doesn't exist
    if 'employees' not in inspector.get_table_names():
        return

    # Placeholder values to normalize (lowercase for case-insensitive matching)
    placeholders = (
        'none', 'n/a', 'na', 'tbd', 'tbc', 'tba', '-', '?', 'null', 'nil', 'unknown',
        'not applicable', 'not assigned', 'pending', 'to be determined', 'to be confirmed',
    )

    # Fields to clean
    mentor_fields = ['mentor', 'mentees', 'talent_mentor', 'talent_mentees']

    with engine.connect() as conn:
        # Check which columns exist
        columns = [col['name'] for col in inspector.get_columns('employees')]

        for field in mentor_fields:
            if field not in columns:
                continue

            # Build placeholders for the IN clause
            placeholders_sql = ', '.join(f"'{p}'" for p in placeholders)

            # Update placeholder values to empty string
            sql = f"""
                UPDATE employees
                SET {field} = ''
                WHERE LOWER(TRIM({field})) IN ({placeholders_sql})
            """
            result = conn.execute(text(sql))
            if result.rowcount > 0:
                print(f"Normalized {result.rowcount} placeholder values in {field}")
            conn.commit()
