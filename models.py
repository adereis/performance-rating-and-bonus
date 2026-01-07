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
    archived_at = Column(DateTime)
    notes = Column(Text)  # Manager notes about this period

    def to_dict(self):
        """Convert model to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
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
    performance_rating = Column(Float)  # Manager's assessment (0-200%), INPUT to algorithm
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
            'has_full_details': self.has_full_details
        }


class BonusSettings(Base):
    """Global bonus calculation settings."""
    __tablename__ = 'bonus_settings'

    id = Column(Integer, primary_key=True)
    workday_pool = Column(Float)  # Total pool from Workday metadata (source of truth)
    budget_override = Column(Float, default=0.0)  # Manager adjustment to pool
    last_updated = Column(DateTime)

    def to_dict(self):
        """Convert model to dictionary for JSON serialization."""
        return {
            'workday_pool': self.workday_pool,
            'budget_override': self.budget_override,
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

    # Manager input fields
    performance_rating_percent = Column(Float)
    justification = Column(String)
    mentor = Column(String)
    mentees = Column(String)
    tenets_strengths = Column(String)  # JSON array of 3 tenet IDs for strengths
    tenets_improvements = Column(String)  # JSON array of 3 tenet IDs for improvements
    last_updated = Column(DateTime)

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
            'justification': self.justification,
            'mentor': self.mentor,
            'mentees': self.mentees,
            'tenets_strengths': self.tenets_strengths,
            'tenets_improvements': self.tenets_improvements,
            'last_updated': self.last_updated.strftime('%Y-%m-%d %H:%M:%S') if self.last_updated else ''
        }


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


def get_db():
    """Get a database session."""
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
