"""
SQLAlchemy models for the performance rating system.
"""
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer, Boolean, Text, Index
from sqlalchemy.ext.declarative import declarative_base
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
    snapshot_bonus_target_usd = Column(Float)  # Bonus target at time of snapshot

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
            'snapshot_bonus_target_usd': self.snapshot_bonus_target_usd,
            'archived_at': self.archived_at.strftime('%Y-%m-%d %H:%M:%S') if self.archived_at else None,
            'has_full_details': self.has_full_details
        }


class BonusSettings(Base):
    """Global bonus calculation settings."""
    __tablename__ = 'bonus_settings'

    id = Column(Integer, primary_key=True)
    budget_override_usd = Column(Float, default=0.0)
    last_updated = Column(DateTime)

    def to_dict(self):
        """Convert model to dictionary for JSON serialization."""
        return {
            'budget_override_usd': self.budget_override_usd,
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
    current_base_pay_all_countries_usd = Column(Float)
    currency = Column(String)
    grade = Column(String, index=True)
    annual_bonus_target_percent = Column(Float)
    last_bonus_allocation_percent = Column(Float)
    bonus_target_local_currency = Column(Float)
    bonus_target_local_currency_usd = Column(Float)
    proposed_bonus_amount = Column(Float)
    proposed_bonus_amount_usd = Column(Float)
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
            'Current Base Pay All Countries (USD)': self.current_base_pay_all_countries_usd,
            'Currency': self.currency,
            'Grade': self.grade,
            'Annual Bonus Target Percent': self.annual_bonus_target_percent,
            'Last Bonus Allocation Percent': self.last_bonus_allocation_percent,
            'Bonus Target - Local Currency': self.bonus_target_local_currency,
            'Bonus Target - Local Currency (USD)': self.bonus_target_local_currency_usd,
            'Proposed Bonus Amount': self.proposed_bonus_amount,
            'Proposed Bonus Amount (USD)': self.proposed_bonus_amount_usd,
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
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize the database, creating all tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get a database session."""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise
