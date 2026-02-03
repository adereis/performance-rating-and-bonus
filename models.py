"""
SQLAlchemy models for the performance rating system.
"""
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer, Boolean, Text, Index
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()


class Period(Base):
    """
    Represents a rating period (e.g., "2024-H1", "2025-Q1").
    Periods are used to organize historical snapshots.
    """
    __tablename__ = 'periods'

    id = Column(String, primary_key=True)  # e.g., "2024-H1", "2025-Q1"
    name = Column(String, nullable=False)  # e.g., "First Half 2024"
    cycle_type = Column(String)  # "bonus" | "talent"
    archived_at = Column(DateTime)
    notes = Column(Text)  # Manager notes about this period

    def to_dict(self):
        """Convert model to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'cycle_type': self.cycle_type,
            'archived_at': self.archived_at.strftime('%Y-%m-%d %H:%M:%S') if self.archived_at else None,
            'notes': self.notes
        }


class RatingSnapshot(Base):
    """
    Historical snapshot of an employee's rating for a specific period.
    Stores both the performance rating (input) and bonus allocation (output).
    """
    __tablename__ = 'rating_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    period_id = Column(String, nullable=False, index=True)  # FK to periods.id
    associate_id = Column(String, nullable=False, index=True)  # Employee identifier

    # Rating vs Allocation (important distinction!)
    performance_rating = Column(Float)  # Manager's Performance Rating (0-200%), INPUT to algorithm
    bonus_allocation = Column(Float)    # Final result from algorithm, OUTPUT

    # Qualitative data (from Notes field, may be NULL for old imports)
    justification = Column(Text)
    tenets_strengths = Column(String)      # Human-readable names, comma-separated
    tenets_improvements = Column(String)   # Human-readable names, comma-separated
    mentors = Column(String)
    mentees = Column(String)

    # Snapshot of employee context at rating time
    snapshot_name = Column(String)           # Employee name at time of snapshot
    snapshot_org = Column(String)            # Supervisory org at time of snapshot
    snapshot_job_profile = Column(String)    # Job profile at time of snapshot
    snapshot_bonus_target_manager_currency = Column(Float)  # Bonus target at time of snapshot

    # Metadata
    archived_at = Column(DateTime)
    has_full_details = Column(Boolean, default=True)  # FALSE if only bonus allocation available

    # Talent calibration snapshot fields
    snapshot_talent_perf_what = Column(String)
    snapshot_talent_perf_how = Column(String)
    snapshot_talent_overall_perf = Column(String)
    snapshot_talent_growth_agility = Column(String)
    snapshot_talent_change_agility = Column(String)
    snapshot_talent_movement_readiness = Column(String)
    snapshot_talent_proposed_actions = Column(Text)
    snapshot_talent_promo_job_profile = Column(String)
    snapshot_talent_tenets_strengths = Column(String)
    snapshot_talent_tenets_improvements = Column(String)
    snapshot_talent_mentor = Column(String)
    snapshot_talent_mentees = Column(String)

    # Unique constraint: one snapshot per employee per period
    __table_args__ = (
        Index('ix_snapshot_period_employee', 'period_id', 'associate_id', unique=True),
    )

    def to_dict(self):
        """Convert model to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'period_id': self.period_id,
            'associate_id': self.associate_id,
            'performance_rating': self.performance_rating,
            'bonus_allocation': self.bonus_allocation,
            'justification': self.justification,
            'tenets_strengths': self.tenets_strengths,
            'tenets_improvements': self.tenets_improvements,
            'mentors': self.mentors,
            'mentees': self.mentees,
            'snapshot_name': self.snapshot_name,
            'snapshot_org': self.snapshot_org,
            'snapshot_job_profile': self.snapshot_job_profile,
            'snapshot_bonus_target_manager_currency': self.snapshot_bonus_target_manager_currency,
            'archived_at': self.archived_at.strftime('%Y-%m-%d %H:%M:%S') if self.archived_at else None,
            'has_full_details': self.has_full_details,
            # Talent snapshot fields
            'snapshot_talent_perf_what': self.snapshot_talent_perf_what,
            'snapshot_talent_perf_how': self.snapshot_talent_perf_how,
            'snapshot_talent_overall_perf': self.snapshot_talent_overall_perf,
            'snapshot_talent_growth_agility': self.snapshot_talent_growth_agility,
            'snapshot_talent_change_agility': self.snapshot_talent_change_agility,
            'snapshot_talent_movement_readiness': self.snapshot_talent_movement_readiness,
            'snapshot_talent_proposed_actions': self.snapshot_talent_proposed_actions,
            'snapshot_talent_promo_job_profile': self.snapshot_talent_promo_job_profile,
            'snapshot_talent_tenets_strengths': self.snapshot_talent_tenets_strengths,
            'snapshot_talent_tenets_improvements': self.snapshot_talent_tenets_improvements,
            'snapshot_talent_mentor': self.snapshot_talent_mentor,
            'snapshot_talent_mentees': self.snapshot_talent_mentees
        }


class BonusSettings(Base):
    """Global bonus calculation settings."""
    __tablename__ = 'bonus_settings'

    id = Column(Integer, primary_key=True)
    workday_pool = Column(Float)  # Total pool from Workday metadata (source of truth)
    budget_override = Column(Float, default=0.0)  # Manager adjustment to pool
    manager_currency = Column(String)  # Currency code extracted from column headers (e.g., 'USD')
    pool_source = Column(String)  # 'workday_metadata' | 'calculated_sum' - how pool was determined
    pool_verified = Column(Boolean, default=False)  # Has user verified the calculated pool?
    last_updated = Column(DateTime)

    def to_dict(self):
        """Convert model to dictionary for JSON serialization."""
        return {
            'workday_pool': self.workday_pool,
            'budget_override': self.budget_override,
            'manager_currency': self.manager_currency,
            'pool_source': self.pool_source,
            'pool_verified': self.pool_verified,
            'last_updated': self.last_updated.strftime('%Y-%m-%d %H:%M:%S') if self.last_updated else ''
        }


class Employee(Base):
    __tablename__ = 'employees'

    # Primary key
    associate_id = Column(String, primary_key=True)

    # Workday fields
    associate = Column(String, nullable=False, index=True)
    supervisory_organization = Column(String)
    current_job_profile = Column(String)
    photo = Column(String)
    errors = Column(String)
    current_base_pay_all_countries = Column(Float)
    current_base_pay_manager_currency = Column(Float)
    currency = Column(String)
    grade = Column(String, index=True)
    annual_bonus_target_percent = Column(Float)
    last_bonus_allocation_percent = Column(Float)
    bonus_target_local_currency = Column(Float)
    bonus_target_manager_currency = Column(Float)
    proposed_bonus_amount = Column(Float)
    proposed_bonus_amount_manager_currency = Column(Float)
    proposed_percent_of_target_bonus = Column(Float)
    notes = Column(String)
    zero_bonus_allocated = Column(String)

    # Manager input fields (Bonus Cycle)
    performance_rating_percent = Column(Float)  # Performance Rating (0-200%)
    performance_rating_percent_original = Column(Float)  # Original from Workday (for modification detection)
    justification = Column(String)
    justification_original = Column(String)  # Original from Workday (for modification detection)
    mentor = Column(String)
    mentor_original = Column(String)  # Original from Workday (for modification detection)
    mentees = Column(String)
    mentees_original = Column(String)  # Original from Workday (for modification detection)
    tenets_strengths = Column(String)  # JSON array of 3 tenet IDs for strengths
    tenets_strengths_original = Column(String)  # Original from Workday (for modification detection)
    tenets_improvements = Column(String)  # JSON array of 3 tenet IDs for improvements
    tenets_improvements_original = Column(String)  # Original from Workday (for modification detection)
    last_updated = Column(DateTime)

    # ═══════════════════════════════════════════════════════════════
    # EXTENDED IDENTITY (from talent report, nullable)
    # ═══════════════════════════════════════════════════════════════
    management_level = Column(String)        # "IC 1", "IC 2", ..., "Manager", "Director"
    job_category = Column(String)            # From Workday
    hire_date = Column(DateTime)             # Date type
    length_of_service = Column(String)       # "2 years, 3 months"
    time_in_job_profile = Column(String)     # "1 year, 6 months"
    region = Column(String)                  # "Americas", "EMEA", "APAC"
    country = Column(String)                 # "United States", "Australia"

    # Historical performance reference (from bonus import, read-only)
    last_perf_review_name = Column(String)   # e.g., "2025-Q2 Talent Assessment"
    last_perf_review_rating = Column(String) # e.g., "Successful Performer"

    # ═══════════════════════════════════════════════════════════════
    # TALENT: PERFORMANCE ASSESSMENT
    # ═══════════════════════════════════════════════════════════════
    talent_perf_what = Column(String)        # ENUM: Surpasses/Meets/Meets Some Expectations
    talent_perf_what_original = Column(String)  # Original from Workday (for modification detection)
    talent_perf_how = Column(String)         # ENUM: Surpasses/Meets/Meets Some/Does Not Meet
    talent_perf_how_original = Column(String)  # Original from Workday (for modification detection)
    talent_overall_perf = Column(String)     # DERIVED: High Impact/Successful/Evolving/Low
    talent_last_overall_perf = Column(String)  # PRESERVED: from Workday historical

    # ═══════════════════════════════════════════════════════════════
    # TALENT: FUTURE TALENT
    # ═══════════════════════════════════════════════════════════════
    talent_growth_agility = Column(String)   # ENUM: Always/Most of the Time, Sometimes
    talent_growth_agility_original = Column(String)  # Original from Workday (for modification detection)
    talent_change_agility = Column(String)   # ENUM: Always/Most of the Time, Sometimes
    talent_change_agility_original = Column(String)  # Original from Workday (for modification detection)
    talent_identified_future = Column(Boolean)  # DERIVED: True when both agility = Always
    talent_last_identified_future = Column(Boolean)  # PRESERVED

    # ═══════════════════════════════════════════════════════════════
    # TALENT: MOVEMENT & CAREER
    # ═══════════════════════════════════════════════════════════════
    talent_movement_readiness = Column(String)  # ENUM: Continue/Ready Now/Ready Lateral
    talent_movement_readiness_original = Column(String)  # Original from Workday (for modification detection)
    talent_last_movement_readiness = Column(String)  # PRESERVED
    talent_proposed_actions = Column(Text)   # Free-form text
    talent_proposed_actions_original = Column(Text)  # Original from Workday (for modification detection)
    talent_mentor = Column(String)           # Mentor (talent cycle, separate from bonus)
    talent_mentor_original = Column(String)  # Original from Workday (for modification detection)
    talent_mentees = Column(String)          # Mentees (talent cycle, separate from bonus)
    talent_mentees_original = Column(String)  # Original from Workday (for modification detection)

    # ═══════════════════════════════════════════════════════════════
    # TALENT: PROMOTION
    # ═══════════════════════════════════════════════════════════════
    talent_promo_job_profile = Column(String)   # "Senior SRE, 1534"
    talent_promo_job_profile_original = Column(String)  # Original from Workday
    talent_promo_business_need = Column(Text)
    talent_promo_business_need_original = Column(Text)  # Original from Workday
    talent_promo_role_scope = Column(Text)
    talent_promo_role_scope_original = Column(Text)  # Original from Workday
    talent_promo_readiness = Column(Text)
    talent_promo_readiness_original = Column(Text)  # Original from Workday

    # ═══════════════════════════════════════════════════════════════
    # TALENT: TENETS (parallel to bonus tenets)
    # ═══════════════════════════════════════════════════════════════
    talent_tenets_strengths = Column(String)     # JSON array of tenet IDs
    talent_tenets_strengths_original = Column(String)  # Original from Workday (for modification detection)
    talent_tenets_improvements = Column(String)  # JSON array of tenet IDs
    talent_tenets_improvements_original = Column(String)  # Original from Workday (for modification detection)

    # ═══════════════════════════════════════════════════════════════
    # TALENT: METADATA
    # ═══════════════════════════════════════════════════════════════
    talent_calibration_status = Column(String)  # Read-only from Workday
    talent_last_updated = Column(DateTime)

    def to_dict(self):
        """Convert model to dictionary for JSON serialization."""
        return {
            'Associate ID': self.associate_id,
            'Associate': self.associate,
            'Supervisory Organization': self.supervisory_organization,
            'Current Job Profile': self.current_job_profile,
            'Photo': self.photo,
            'Errors': self.errors,
            'Current Base Pay All Countries': self.current_base_pay_all_countries,
            'Current Base Pay Manager Currency': self.current_base_pay_manager_currency,
            'Currency': self.currency,
            'Grade': self.grade,
            'Annual Bonus Target Percent': self.annual_bonus_target_percent,
            'Last Bonus Allocation Percent': self.last_bonus_allocation_percent,
            'Bonus Target - Local Currency': self.bonus_target_local_currency,
            'Bonus Target Manager Currency': self.bonus_target_manager_currency,
            'Proposed Bonus Amount': self.proposed_bonus_amount,
            'Proposed Bonus Amount Manager Currency': self.proposed_bonus_amount_manager_currency,
            'Proposed Percent of Target Bonus': self.proposed_percent_of_target_bonus,
            'Notes': self.notes,
            'Zero Bonus Allocated': self.zero_bonus_allocated,
            'performance_rating_percent': self.performance_rating_percent,
            'performance_rating_percent_original': self.performance_rating_percent_original,
            'justification': self.justification,
            'justification_original': self.justification_original,
            'mentor': self.mentor,
            'mentor_original': self.mentor_original,
            'mentees': self.mentees,
            'mentees_original': self.mentees_original,
            'tenets_strengths': self.tenets_strengths,
            'tenets_strengths_original': self.tenets_strengths_original,
            'tenets_improvements': self.tenets_improvements,
            'tenets_improvements_original': self.tenets_improvements_original,
            'last_updated': self.last_updated.strftime('%Y-%m-%d %H:%M:%S') if self.last_updated else '',
            # Extended identity (from talent report)
            'management_level': self.management_level,
            'job_category': self.job_category,
            'hire_date': self.hire_date.strftime('%Y-%m-%d') if self.hire_date else None,
            'length_of_service': self.length_of_service,
            'time_in_job_profile': self.time_in_job_profile,
            'region': self.region,
            'country': self.country,
            # Historical performance reference (from bonus import)
            'last_perf_review_name': self.last_perf_review_name,
            'last_perf_review_rating': self.last_perf_review_rating,
            # Talent: Performance Assessment
            'talent_perf_what': self.talent_perf_what,
            'talent_perf_what_original': self.talent_perf_what_original,
            'talent_perf_how': self.talent_perf_how,
            'talent_perf_how_original': self.talent_perf_how_original,
            'talent_overall_perf': self.talent_overall_perf,
            'talent_last_overall_perf': self.talent_last_overall_perf,
            # Talent: Future Talent
            'talent_growth_agility': self.talent_growth_agility,
            'talent_growth_agility_original': self.talent_growth_agility_original,
            'talent_change_agility': self.talent_change_agility,
            'talent_change_agility_original': self.talent_change_agility_original,
            'talent_identified_future': self.talent_identified_future,
            'talent_last_identified_future': self.talent_last_identified_future,
            # Talent: Movement & Career
            'talent_movement_readiness': self.talent_movement_readiness,
            'talent_movement_readiness_original': self.talent_movement_readiness_original,
            'talent_last_movement_readiness': self.talent_last_movement_readiness,
            'talent_proposed_actions': self.talent_proposed_actions,
            'talent_proposed_actions_original': self.talent_proposed_actions_original,
            'talent_mentor': self.talent_mentor,
            'talent_mentor_original': self.talent_mentor_original,
            'talent_mentees': self.talent_mentees,
            'talent_mentees_original': self.talent_mentees_original,
            # Talent: Promotion
            'talent_promo_job_profile': self.talent_promo_job_profile,
            'talent_promo_job_profile_original': self.talent_promo_job_profile_original,
            'talent_promo_business_need': self.talent_promo_business_need,
            'talent_promo_business_need_original': self.talent_promo_business_need_original,
            'talent_promo_role_scope': self.talent_promo_role_scope,
            'talent_promo_role_scope_original': self.talent_promo_role_scope_original,
            'talent_promo_readiness': self.talent_promo_readiness,
            'talent_promo_readiness_original': self.talent_promo_readiness_original,
            # Talent: Tenets
            'talent_tenets_strengths': self.talent_tenets_strengths,
            'talent_tenets_strengths_original': self.talent_tenets_strengths_original,
            'talent_tenets_improvements': self.talent_tenets_improvements,
            'talent_tenets_improvements_original': self.talent_tenets_improvements_original,
            # Talent: Metadata
            'talent_calibration_status': self.talent_calibration_status,
            'talent_last_updated': self.talent_last_updated.strftime('%Y-%m-%d %H:%M:%S') if self.talent_last_updated else None
        }


# ═══════════════════════════════════════════════════════════════════════════
# TALENT CALIBRATION DERIVATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════


def derive_overall_performance(what: str | None, how: str | None) -> str | None:
    """
    Derive the overall performance rating from the What and How assessments.

    Uses a tier-based approach matching Workday's logic:
      Tier 4 = Surpasses Expectations
      Tier 3 = Meets Expectations
      Tier 2 = Meets Some Expectations
      Tier 1 = Does Not Meet Expectations

    Decision table (matches Workday behavior):
    | What              | How                   | → Result              |
    |-------------------|-----------------------|-----------------------|
    | Does Not Meet     | Does Not Meet         | Low Performer         |
    | Does Not Meet     | Meets Some            | Low Performer         |
    | Meets Some        | Does Not Meet         | Low Performer         |
    | Does Not Meet     | Meets                 | Evolving Performer    |
    | Does Not Meet     | Surpasses             | Evolving Performer    |
    | Meets             | Does Not Meet         | Evolving Performer    |
    | Surpasses         | Does Not Meet         | Evolving Performer    |
    | Meets Some        | Meets Some            | Evolving Performer    |
    | Meets Some        | Meets                 | Evolving Performer    |
    | Meets             | Meets Some            | Evolving Performer    |
    | Surpasses         | Meets Some            | Successful Performer  |
    | Meets Some        | Surpasses             | Successful Performer  |
    | Meets             | Meets                 | Successful Performer  |
    | Meets             | Surpasses             | Successful Performer  |
    | Surpasses         | Meets                 | Successful Performer  |
    | Surpasses         | Surpasses             | High Impact Performer |
    | (null/empty)      | *                     | None                  |
    | *                 | (null/empty)          | None                  |
    """
    if not what or not how:
        return None

    w, h = what.lower(), how.lower()

    def get_tier(rating: str) -> int:
        """Map rating string to numeric tier (1-4)."""
        if 'surpasses' in rating:
            return 4
        if 'does not meet' in rating:
            return 1
        if 'some' in rating:  # "meets some expectations"
            return 2
        if 'meets' in rating:  # "meets expectations"
            return 3
        return 3  # fallback

    w_tier = get_tier(w)
    h_tier = get_tier(h)
    min_tier = min(w_tier, h_tier)
    max_tier = max(w_tier, h_tier)

    # Low Performer: "Does Not Meet" (tier 1) paired with tier 2 or lower
    if min_tier == 1 and max_tier <= 2:
        return 'Low Performer'

    # High Impact: both are Surpasses (tier 4)
    if min_tier == 4:
        return 'High Impact Performer'

    # Successful: both at least Meets (tier 3), OR Surpasses carries Meets Some
    if min_tier >= 3:
        return 'Successful Performer'
    if max_tier == 4 and min_tier == 2:  # Surpasses + Meets Some
        return 'Successful Performer'

    # Evolving: everything else
    return 'Evolving Performer'


def derive_future_talent(growth: str | None, change: str | None) -> bool:
    """
    Derive whether an employee is identified as Future Talent.

    Rule (from Spec §4.2): Both Growth Agility AND Change Agility must
    contain "Always" (case-insensitive) to be identified as Future Talent.
    """
    if not growth or not change:
        return False
    return 'always' in growth.lower() and 'always' in change.lower()


def get_cross_cycle_alignment(bonus_pct: float | None, talent_overall: str | None) -> str:
    """
    Determine cross-cycle alignment between performance rating and talent calibration.

    Per Spec §7.4, compares the performance rating percentage with
    the talent Overall Performance rating to identify alignment or need for review.

    Alignment ranges:
    - High Impact Performer: 120-200%
    - Successful Performer: 90-119%
    - Evolving Performer: 70-89%
    - Low Performer: 0-69%

    Args:
        bonus_pct: Performance rating percentage from bonus cycle (0-200)
        talent_overall: Overall Performance from talent calibration

    Returns:
        "aligned" - Performance rating falls within expected range for overall performance
        "review" - Ratings don't align, may need review
        "incomplete" - Missing either bonus or talent data
    """
    if bonus_pct is None or talent_overall is None:
        return "incomplete"

    # Expected bonus ranges for each overall performance level
    ranges = {
        "High Impact Performer": (120, 200),
        "Successful Performer": (90, 119),
        "Evolving Performer": (70, 89),
        "Low Performer": (0, 69),
    }

    expected_range = ranges.get(talent_overall)
    if expected_range is None:
        return "incomplete"

    lo, hi = expected_range
    return "aligned" if lo <= bonus_pct <= hi else "review"


# Database setup
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///ratings.db')
DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'

# Standard (non-demo) database engine
_engine = None
_SessionLocal = None


def _get_standard_engine():
    """Get or create the standard (non-demo) database engine."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(DATABASE_URL, echo=False)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def _migrate_usd_columns(engine):
    """
    Migrate old *_usd column names to *_manager_currency.

    This handles databases created before the international manager currency
    support was added. SQLite 3.25.0+ supports ALTER TABLE RENAME COLUMN.
    """
    from sqlalchemy import text, inspect

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


def _migrate_add_new_columns(engine):
    """
    Add new columns that were added in later versions.

    This handles databases created before new columns were added.
    """
    from sqlalchemy import text, inspect

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


class DatabaseSchemaError(Exception):
    """Raised when database schema doesn't match expected model schema."""
    pass


def _migrate_normalize_mentor_placeholders(engine):
    """
    Normalize placeholder values in mentor/mentee fields to empty strings.

    Cleans up entries like 'None', 'TBD', 'N/A', etc. that managers may have
    entered as placeholders. This is a one-time cleanup for existing data.
    """
    from sqlalchemy import text, inspect

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


def _validate_schema(engine):
    """
    Validate that the database schema matches the expected model schema.

    Checks that all columns defined in SQLAlchemy models exist in the actual
    database tables. Raises DatabaseSchemaError with a helpful message if
    there's a mismatch.
    """
    from sqlalchemy import inspect

    inspector = inspect(engine)
    errors = []

    # Models to validate: (model_class, table_name)
    models_to_check = [
        (Employee, 'employees'),
        (BonusSettings, 'bonus_settings'),
        (Period, 'periods'),
        (RatingSnapshot, 'rating_snapshots'),
    ]

    for model_class, table_name in models_to_check:
        # Skip if table doesn't exist yet (will be created by create_all)
        if table_name not in inspector.get_table_names():
            continue

        # Get actual columns in database
        db_columns = {col['name'] for col in inspector.get_columns(table_name)}

        # Get expected columns from model
        model_columns = {col.name for col in model_class.__table__.columns}

        # Find missing columns
        missing = model_columns - db_columns

        if missing:
            errors.append(f"  Table '{table_name}' is missing columns: {', '.join(sorted(missing))}")

    if errors:
        db_path = DATABASE_URL.replace('sqlite:///', '')
        raise DatabaseSchemaError(
            f"\n{'='*60}\n"
            f"DATABASE SCHEMA MISMATCH\n"
            f"{'='*60}\n"
            f"The database schema doesn't match the expected model schema.\n\n"
            f"Issues found:\n" + '\n'.join(errors) + "\n\n"
            f"This usually happens when:\n"
            f"  1. The database was created with an older version of the app\n"
            f"  2. A migration failed or was incomplete\n\n"
            f"To fix this, you can either:\n"
            f"  A. Delete the database and re-import your data:\n"
            f"     rm {db_path}\n\n"
            f"  B. Manually add the missing columns (for advanced users):\n"
            f"     sqlite3 {db_path} \"ALTER TABLE <table> ADD COLUMN <col> <type>;\"\n"
            f"{'='*60}\n"
        )


def init_db():
    """Initialize the database, creating all tables."""
    # Skip production db init during testing - tests use isolated temp databases
    if os.getenv('TESTING') == 'true':
        return

    if DEMO_MODE:
        # In demo mode, databases are created per-session in demo_mode.py
        from demo_mode import _log
        _log("Database initialization deferred to per-session setup")
        return

    engine = _get_standard_engine()

    # Run migrations before creating tables (handles schema changes)
    _migrate_usd_columns(engine)
    _migrate_add_new_columns(engine)

    # Create any new tables/columns
    Base.metadata.create_all(bind=engine)

    # Validate schema matches models (catches issues migration didn't handle)
    _validate_schema(engine)

    # Data migrations (run after schema is validated)
    _migrate_normalize_mentor_placeholders(engine)


def get_db():
    """Get a database session."""
    # Guard against test code accidentally using production database.
    # During tests, conftest.py sets TESTING=true and patches this function.
    # If we reach here with TESTING=true, the patch didn't happen (e.g., python -c).
    if os.getenv('TESTING') == 'true':
        raise RuntimeError(
            "get_db() called during testing without proper fixture setup. "
            "Tests must use the 'db_session' or 'client' fixtures from conftest.py. "
            "If running outside pytest, unset the TESTING environment variable."
        )

    if DEMO_MODE:
        # Import here to avoid circular imports
        from demo_mode import get_demo_db
        return get_demo_db()

    _get_standard_engine()  # Ensure engine exists
    db = _SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise
