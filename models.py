"""
SQLAlchemy models for the performance rating system.
"""
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()


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
    ai_activities = Column(String)
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
            'ai_activities': self.ai_activities,
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
