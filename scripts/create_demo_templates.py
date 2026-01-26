#!/usr/bin/env python3
"""
Create pre-built demo template databases for the Performance Rating System.

This generates SQLite databases pre-populated with fictitious employee data,
ratings, and talent calibration data, ready to be copied for new demo sessions.

Usage:
    python3 scripts/create_demo_templates.py

Creates:
    demo-templates/small-team.db  - 12 employees, 1 manager, with ratings + talent
    demo-templates/large-team.db  - 55 employees, 5 managers, with ratings + talent
"""
import sys
import os
import random
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Employee, BonusSettings, Period, RatingSnapshot, derive_overall_performance, derive_future_talent


# ============================================================================
# Talent Calibration Generation (Spec §3, §4.1, §4.2)
# ============================================================================

PERF_WHAT_OPTIONS = [
    'Surpasses Expectations',
    'Meets Expectations',
    'Meets Some Expectations'
]

PERF_HOW_OPTIONS = [
    'Surpasses Expectations',
    'Meets Expectations',
    'Meets Some Expectations',
    'Does Not Meet Expectations'
]

AGILITY_OPTIONS = [
    'Always/Most of the Time',
    'Sometimes'
]

MOVEMENT_READINESS_OPTIONS = [
    'Continue growing in current role',
    'Ready Now to be promoted in current role',
    'Ready for lateral move'
]


def generate_talent_data(bonus_rating: int) -> dict:
    """Generate talent calibration data aligned with performance rating."""
    # Weight distributions based on performance rating (aligned with Spec §7.4)
    if bonus_rating >= 120:
        what_weights = [0.6, 0.35, 0.05]
        how_weights = [0.5, 0.45, 0.05, 0.0]
        agility_weight = 0.6
        movement_weights = [0.5, 0.4, 0.1]
    elif bonus_rating >= 90:
        what_weights = [0.2, 0.70, 0.10]
        how_weights = [0.15, 0.70, 0.15, 0.0]
        agility_weight = 0.35
        movement_weights = [0.70, 0.25, 0.05]
    elif bonus_rating >= 70:
        what_weights = [0.05, 0.50, 0.45]
        how_weights = [0.05, 0.45, 0.50, 0.0]
        agility_weight = 0.20
        movement_weights = [0.85, 0.10, 0.05]
    else:
        what_weights = [0.0, 0.25, 0.75]
        how_weights = [0.0, 0.20, 0.50, 0.30]
        agility_weight = 0.10
        movement_weights = [0.95, 0.03, 0.02]

    perf_what = random.choices(PERF_WHAT_OPTIONS, weights=what_weights)[0]
    perf_how = random.choices(PERF_HOW_OPTIONS, weights=how_weights)[0]
    growth = 'Always/Most of the Time' if random.random() < agility_weight else 'Sometimes'
    change = 'Always/Most of the Time' if random.random() < agility_weight else 'Sometimes'
    movement = random.choices(MOVEMENT_READINESS_OPTIONS, weights=movement_weights)[0]

    overall = derive_overall_performance(perf_what, perf_how)
    future_talent = derive_future_talent(growth, change)

    # Generate historical "last cycle" data
    last_what = random.choice(PERF_WHAT_OPTIONS)
    last_how = random.choice(PERF_HOW_OPTIONS[:3])
    last_overall = derive_overall_performance(last_what, last_how)
    last_growth = random.choice(AGILITY_OPTIONS)
    last_change = random.choice(AGILITY_OPTIONS)
    last_future_talent = derive_future_talent(last_growth, last_change)
    last_movement = random.choice(MOVEMENT_READINESS_OPTIONS)

    return {
        'talent_perf_what': perf_what,
        'talent_perf_how': perf_how,
        'talent_overall_perf': overall,
        'talent_growth_agility': growth,
        'talent_change_agility': change,
        'talent_identified_future': future_talent,
        'talent_movement_readiness': movement,
        'talent_last_overall_perf': last_overall,
        'talent_last_identified_future': last_future_talent,
        'talent_last_movement_readiness': last_movement,
        'talent_last_updated': datetime.now(),
    }


# Promotion candidates with full promo data
PROMO_CANDIDATES = {
    'Al Ert': {
        'talent_promo_job_profile': 'Principal SRE, 1847',
        'talent_promo_business_need': 'Team expanding scope to cover global reliability',
        'talent_promo_role_scope': 'Will lead cross-regional SRE initiatives',
        'talent_promo_readiness': 'Demonstrated technical leadership and mentorship',
    },
    'Sue Q. Ell': {
        'talent_promo_job_profile': 'Staff Software Developer, 1623',
        'talent_promo_business_need': 'Need senior DB expertise for new product line',
        'talent_promo_role_scope': 'Expand from query optimization to full data architecture',
        'talent_promo_readiness': 'Strong IC track record, ready for staff scope',
    },
    'Artie Ficial': {
        'talent_promo_job_profile': 'Principal Software Developer, 2134',
        'talent_promo_business_need': 'Architecture leadership for distributed systems initiative',
        'talent_promo_role_scope': 'Lead cross-team technical strategy and system design',
        'talent_promo_readiness': 'Exceptional technical vision, proven cross-team influence',
    },
    'Ty Po': {
        'talent_promo_job_profile': 'Staff SRE, 1892',
        'talent_promo_business_need': 'Infrastructure modernization requires senior leadership',
        'talent_promo_role_scope': 'Own infrastructure strategy for platform reliability',
        'talent_promo_readiness': 'Outstanding track record, ready for expanded scope',
    },
}


# ============================================================================
# Employee Data Generation
# ============================================================================


def get_small_team_employees():
    """
    Small team: 12 employees under single manager (Della Gate).
    The user IS Della Gate (manager), so she is not included as an employee.
    Includes ratings and justifications.

    Rating distribution designed to show expressive bonus curve:
    - 1 low performer (~60%) - shows steep penalty
    - 2-3 needs improvement (85-90%)
    - 4-5 meeting expectations (95-105%)
    - 2-3 high performers (110-120%)
    - 1-2 exceptional (130-140%) - above linear line
    """
    manager = "Supervisory Organization (Della Gate)"

    # (name, job, salary, grade, bonus_pct, rating, justification)
    employees = [
        # Exceptional performers (above linear line on bonus curve)
        ('Al Ert', 'Staff SRE', 175000, 'IC4', 3.75, 140, 'Exceptional alerting system overhaul, prevented 3 major outages'),
        ('Paige Duty', 'Staff SRE', 180000, 'IC4', 3.75, 130, 'Outstanding technical leadership and on-call reliability'),

        # High performers
        ('Sue Q. Ell', 'Senior Software Developer', 148000, 'IC3', 3.0, 120, 'Excellent database optimization, 40% query improvement'),
        ('Tracey Loggins', 'Senior SRE', 155000, 'IC3', 3.0, 110, 'Strong logging infrastructure improvements'),

        # Meeting expectations (cluster around 100%)
        ('Mona Torr', 'Senior SRE', 145000, 'IC3', 3.0, 105, 'Solid monitoring and observability contributions'),
        ('Robin Rollback', 'Software Developer', 120000, 'IC2', 2.5, 100, 'Reliable deployment management, met all targets'),
        ('Kenny Canary', 'Software Developer', 115000, 'IC2', 2.5, 100, 'Consistent canary testing and deployment work'),
        ('Lee Latency', 'Senior Software Developer', 150000, 'IC3', 3.0, 95, 'Good performance work, some delays on key projects'),
        ('Barbie Que', 'Senior SRE', 149000, 'IC3', 3.0, 95, 'Adequate message queue management'),

        # Needs improvement
        ('Jason Blob', 'Software Developer', 118000, 'IC2', 2.5, 85, 'Needs improvement on code quality and testing'),
        ('Addie Min', 'Senior Software Developer', 152000, 'IC3', 3.0, 85, 'Security work incomplete, missed deadlines'),

        # Low performer (shows steep penalty on curve)
        ('Tim Out', 'Software Developer', 110000, 'IC2', 2.5, 60, 'Significant performance issues, on improvement plan'),
    ]

    result = []
    for i, (name, job, salary, grade, bonus_pct, rating, justification) in enumerate(employees):
        bonus_target = salary * (bonus_pct / 100)

        # Generate talent calibration data aligned with performance rating
        talent_data = generate_talent_data(rating)

        emp_data = {
            'associate_id': f'EMP{1000 + i}',
            'associate': name,
            'supervisory_organization': manager,
            'current_job_profile': job,
            'currency': 'USD',
            'current_base_pay_all_countries': salary,
            'current_base_pay_manager_currency': salary,
            'grade': grade,
            'annual_bonus_target_percent': bonus_pct,
            'bonus_target_local_currency': bonus_target,
            'bonus_target_manager_currency': bonus_target,
            'performance_rating_percent': rating,
            'justification': justification,
            'mentor': '',  # Empty string, not NULL
            'mentees': '',  # Empty string, not NULL
            'last_updated': datetime.now(),
            # Talent calibration fields
            **talent_data,
        }

        # Add promotion data for select candidates
        if name in PROMO_CANDIDATES:
            emp_data.update(PROMO_CANDIDATES[name])
            emp_data['talent_movement_readiness'] = 'Ready Now to be promoted in current role'

        result.append(emp_data)

    return result


def get_large_team_employees():
    """
    Large org: 55 employees across 5 teams (10 ICs + 1 manager per team).
    The user is a director who manages the 5 team managers.
    The 5 managers are included as employees that the director rates.
    Includes ratings and justifications with diverse performance levels.

    Each team has a mix showing the full bonus curve:
    - 1-2 exceptional (130-145%) - above linear line
    - 2 high performers (115-125%)
    - 3-4 meeting expectations (90-110%)
    - 1-2 needs improvement (70-85%)
    - 0-1 low performer (50-65%)
    """
    teams = {
        'Platform Engineering (Della Gate)': [
            # Manager
            ('Della Gate', 'Engineering Manager', 210000, 'M2', 6.0, 110, 'Strong platform team leadership, delivered key infrastructure projects'),
            # Exceptional - above linear bonus line
            ('Paige Duty', 'Principal Engineer', 220000, 'IC5', 5.0, 145, 'Exceptional technical vision, led platform redesign saving $2M/year'),
            ('Lee Latency', 'Staff Software Developer', 185000, 'IC4', 3.75, 130, 'Outstanding team leadership, zero production incidents'),
            # High performers
            ('Mona Torr', 'Staff SRE', 180000, 'IC4', 3.75, 120, 'Strong platform reliability, 99.99% uptime achieved'),
            ('Robin Rollback', 'Senior Software Developer', 155000, 'IC3', 3.0, 115, 'Excellent API development and documentation'),
            # Meeting expectations
            ('Kenny Canary', 'Senior Software Developer', 150000, 'IC3', 3.0, 105, 'Solid infrastructure contributions'),
            ('Tracey Loggins', 'Software Developer', 125000, 'IC2', 2.5, 100, 'Met expectations on platform integration'),
            ('Sue Q. Ell', 'Software Developer', 120000, 'IC2', 2.5, 100, 'Reliable service deployment work'),
            ('Addie Min', 'Senior Software Developer', 160000, 'IC3', 3.0, 95, 'Good mentorship, some project delays'),
            # Needs improvement
            ('Jason Blob', 'Software Developer', 115000, 'IC2', 2.5, 80, 'Code quality needs improvement, missed deadlines'),
            ('Al Ert', 'Junior Software Developer', 95000, 'IC1', 2.0, 70, 'Struggling with ownership, needs more guidance'),
        ],
        'Frontend Experience (Rhoda Map)': [
            # Manager
            ('Rhoda Map', 'Engineering Manager', 205000, 'M2', 6.0, 105, 'Good frontend team leadership, successful design system rollout'),
            # Exceptional - includes one very high performer
            ('Tim Out', 'Principal Engineer', 225000, 'IC5', 5.0, 140, 'Transformational UI architecture, 60% performance improvement'),
            ('Barbie Que', 'Staff Software Developer', 190000, 'IC4', 3.75, 135, 'Outstanding team growth and design system'),
            # High performers
            ('Terry Byte', 'Senior Software Developer', 160000, 'IC3', 3.0, 120, 'Excellent React component library'),
            ('Cody Ryder', 'Senior Software Developer', 158000, 'IC3', 3.0, 115, 'Strong state management refactoring'),
            # Meeting expectations
            ('Nole Pointer', 'Senior Software Developer', 155000, 'IC3', 3.0, 105, 'Solid accessibility improvements'),
            ('Bridget Branch', 'Software Developer', 120000, 'IC2', 2.5, 100, 'Good responsive design work'),
            ('Cy Ferr', 'Software Developer', 118000, 'IC2', 2.5, 95, 'Adequate component development'),
            # Needs improvement
            ('Lana Wan', 'Software Developer', 122000, 'IC2', 2.5, 85, 'Communication issues, missed sprint goals'),
            ('Phil Wall', 'Junior Software Developer', 92000, 'IC1', 2.0, 70, 'Below expectations, struggling with React'),
            # Low performer
            ('Marge Conflict', 'Software Developer', 125000, 'IC2', 2.5, 55, 'Serious performance concerns, on PIP'),
        ],
        'Backend Services (Kay P. Eye)': [
            # Manager
            ('Kay P. Eye', 'Engineering Manager', 208000, 'M2', 6.0, 115, 'Excellent API team leadership, drove cross-team standards'),
            # Exceptional
            ('Artie Ficial', 'Principal Engineer', 230000, 'IC5', 5.0, 140, 'Exceptional distributed systems architecture'),
            ('Ruth Cause', 'Staff Software Developer', 188000, 'IC4', 3.75, 130, 'Outstanding microservices redesign'),
            # High performers
            ('Matt Rick', 'Staff Software Developer', 185000, 'IC4', 3.75, 125, 'Excellent cross-team coordination'),
            ('Cassie Cache', 'Senior Software Developer', 162000, 'IC3', 3.0, 115, 'Strong API design and caching strategy'),
            # Meeting expectations
            ("Annie O'Maly", 'Senior Software Developer', 165000, 'IC3', 3.0, 105, 'Good database optimization work'),
            ('Sue Do', 'Senior Software Developer', 158000, 'IC3', 3.0, 100, 'Met expectations on service reliability'),
            ('Pat Ch', 'Software Developer', 128000, 'IC2', 2.5, 100, 'Solid backend feature development'),
            ('Devin Null', 'Software Developer', 124000, 'IC2', 2.5, 95, 'Steady progress on REST APIs'),
            # Needs improvement
            ('Justin Time', 'Software Developer', 120000, 'IC2', 2.5, 85, 'Frequently late on deliverables'),
            ('Sam Box', 'Junior Software Developer', 98000, 'IC1', 2.0, 75, 'Needs more initiative on tasks'),
        ],
        'Infrastructure (Agie Enda)': [
            # Manager
            ('Agie Enda', 'Engineering Manager', 212000, 'M2', 6.0, 120, 'Outstanding infrastructure team leadership, drove cloud migration'),
            # Exceptional
            ('Ty Po', 'Principal Engineer', 235000, 'IC5', 5.0, 140, 'Exceptional infrastructure modernization'),
            ('Mike Roservices', 'Staff SRE', 192000, 'IC4', 3.75, 130, 'Outstanding container platform work'),
            # High performers
            ('Val Idation', 'Staff SRE', 195000, 'IC4', 3.75, 120, 'Excellent infrastructure automation'),
            ('Lou Pe', 'Senior SRE', 168000, 'IC3', 3.0, 115, 'Strong CI/CD pipeline improvements'),
            # Meeting expectations
            ('Connie Tainer', 'Senior SRE', 162000, 'IC3', 3.0, 105, 'Good Kubernetes migration work'),
            ('Exa M. Elle', 'Senior SRE', 170000, 'IC3', 3.0, 100, 'Met cloud cost optimization targets'),
            ('Noah Node', 'SRE', 130000, 'IC2', 2.5, 100, 'Solid infrastructure automation'),
            ('Sara Ver', 'SRE', 125000, 'IC2', 2.5, 95, 'Adequate monitoring setup'),
            # Needs improvement
            ('Bill Ding', 'Senior SRE', 165000, 'IC3', 3.0, 85, 'Deployment issues, needs more testing'),
            ('Dee Ploi', 'SRE', 128000, 'IC2', 2.5, 65, 'DR planning incomplete, reliability gaps'),
        ],
        'Site Reliability (Mai Stone)': [
            # Manager
            ('Mai Stone', 'Engineering Manager', 215000, 'M2', 6.0, 100, 'Solid SRE team leadership, met reliability targets'),
            # Exceptional
            ("Ray D. O'Button", 'Principal SRE', 228000, 'IC5', 5.0, 135, 'Outstanding SLO/SLI framework design'),
            ('Cam Elcase', 'Staff SRE', 198000, 'IC4', 3.75, 130, 'Excellent reliability culture building'),
            # High performers
            ('Hashim Map', 'Staff SRE', 195000, 'IC4', 3.75, 120, 'Strong on-call process improvements'),
            ('Ben Chmark', 'Senior SRE', 172000, 'IC3', 3.0, 115, 'Good incident response leadership'),
            # Meeting expectations
            ('Grace Full', 'Senior SRE', 168000, 'IC3', 3.0, 105, 'Solid observability improvements'),
            ('Shel Script', 'Senior SRE', 165000, 'IC3', 3.0, 100, 'Met monitoring and alerting goals'),
            ('Mo Nitor', 'Senior SRE', 175000, 'IC3', 3.0, 100, 'Reliable performance monitoring'),
            ('Red Undancy', 'SRE', 132000, 'IC2', 2.5, 95, 'Adequate failover testing'),
            # Needs improvement
            ('Sal T. Hash', 'SRE', 135000, 'IC2', 2.5, 85, 'Chaos engineering incomplete'),
            ('Polly Morphism', 'SRE', 128000, 'IC2', 2.5, 80, 'System flexibility work behind schedule'),
        ],
    }

    result = []
    emp_id = 2000

    for team_name, members in teams.items():
        for (name, job, salary, grade, bonus_pct, rating, justification) in members:
            bonus_target = salary * (bonus_pct / 100)

            # Generate talent calibration data aligned with performance rating
            talent_data = generate_talent_data(rating)

            emp_data = {
                'associate_id': f'EMP{emp_id}',
                'associate': name,
                'supervisory_organization': team_name,
                'current_job_profile': job,
                'currency': 'USD',
                'current_base_pay_all_countries': salary,
                'current_base_pay_manager_currency': salary,
                'grade': grade,
                'annual_bonus_target_percent': bonus_pct,
                'bonus_target_local_currency': bonus_target,
                'bonus_target_manager_currency': bonus_target,
                'performance_rating_percent': rating,
                'justification': justification,
                'mentor': '',  # Empty string, not NULL
                'mentees': '',  # Empty string, not NULL
                'last_updated': datetime.now(),
                # Talent calibration fields
                **talent_data,
            }

            # Add promotion data for select candidates
            if name in PROMO_CANDIDATES:
                emp_data.update(PROMO_CANDIDATES[name])
                emp_data['talent_movement_readiness'] = 'Ready Now to be promoted in current role'

            result.append(emp_data)
            emp_id += 1

    return result


def generate_snapshot_talent_data(emp: dict) -> dict:
    """
    Generate talent snapshot data with variation from current talent data.
    Creates realistic historical talent data for trend analysis.
    """
    # Get current performance rating to generate varied historical talent data
    current_rating = emp.get('performance_rating_percent', 100)
    # Vary historical rating similar to how bonus snapshots vary
    historical_rating = max(50, min(180, current_rating + random.randint(-20, 10)))

    # Generate talent data based on varied historical rating
    # Use same weighted generation as current data but with historical rating
    if historical_rating >= 120:
        what_weights = [0.6, 0.35, 0.05]
        how_weights = [0.5, 0.45, 0.05, 0.0]
        agility_weight = 0.55
        movement_weights = [0.55, 0.35, 0.10]
    elif historical_rating >= 90:
        what_weights = [0.2, 0.70, 0.10]
        how_weights = [0.15, 0.70, 0.15, 0.0]
        agility_weight = 0.30
        movement_weights = [0.75, 0.20, 0.05]
    elif historical_rating >= 70:
        what_weights = [0.05, 0.50, 0.45]
        how_weights = [0.05, 0.45, 0.50, 0.0]
        agility_weight = 0.20
        movement_weights = [0.85, 0.10, 0.05]
    else:
        what_weights = [0.0, 0.25, 0.75]
        how_weights = [0.0, 0.20, 0.50, 0.30]
        agility_weight = 0.10
        movement_weights = [0.95, 0.03, 0.02]

    perf_what = random.choices(PERF_WHAT_OPTIONS, weights=what_weights)[0]
    perf_how = random.choices(PERF_HOW_OPTIONS, weights=how_weights)[0]
    growth = 'Always/Most of the Time' if random.random() < agility_weight else 'Sometimes'
    change = 'Always/Most of the Time' if random.random() < agility_weight else 'Sometimes'
    movement = random.choices(MOVEMENT_READINESS_OPTIONS, weights=movement_weights)[0]
    overall = derive_overall_performance(perf_what, perf_how)

    return {
        'snapshot_talent_perf_what': perf_what,
        'snapshot_talent_perf_how': perf_how,
        'snapshot_talent_overall_perf': overall,
        'snapshot_talent_growth_agility': growth,
        'snapshot_talent_change_agility': change,
        'snapshot_talent_movement_readiness': movement,
        'snapshot_talent_proposed_actions': None,
        'snapshot_talent_promo_job_profile': emp.get('talent_promo_job_profile'),
        'snapshot_talent_tenets_strengths': None,
        'snapshot_talent_tenets_improvements': None,
    }


def get_historical_periods(employees, include_large_history=False):
    """
    Generate historical period data based on current employees.
    Creates 2 periods for small team, 3 for large team.
    Includes talent calibration snapshot data.

    Returns list of (period_data, snapshots) tuples.
    """
    from datetime import timedelta

    periods = []

    # Period 1: Previous half (6 months ago)
    period1_date = datetime.now() - timedelta(days=180)
    period1 = {
        'id': '2024-H2',
        'name': 'Second Half 2024',
        'notes': 'Year-end performance cycle',
        'archived_at': period1_date,
    }

    # Generate snapshots with slightly different ratings (simulating growth)
    period1_snapshots = []
    for emp in employees:
        # Vary historical rating by -15 to +10 from current
        current_rating = emp.get('performance_rating_percent', 100)
        historical_rating = max(50, min(180, current_rating + random.randint(-15, 10)))

        snapshot_data = {
            'period_id': period1['id'],
            'associate_id': emp['associate_id'],
            'performance_rating': historical_rating,
            'bonus_allocation': historical_rating,  # Simplified
            'justification': f"Previous cycle: {emp.get('justification', 'Standard performance')}",
            'snapshot_name': emp['associate'],
            'snapshot_org': emp['supervisory_organization'],
            'snapshot_job_profile': emp['current_job_profile'],
            'snapshot_bonus_target_manager_currency': emp.get('bonus_target_manager_currency'),
            'archived_at': period1_date,
            'has_full_details': True,
            # Talent calibration snapshot data
            **generate_snapshot_talent_data(emp),
        }
        period1_snapshots.append(snapshot_data)

    periods.append((period1, period1_snapshots))

    # Period 2: One year ago
    period2_date = datetime.now() - timedelta(days=365)
    period2 = {
        'id': '2024-H1',
        'name': 'First Half 2024',
        'notes': 'Mid-year review cycle',
        'archived_at': period2_date,
    }

    period2_snapshots = []
    for emp in employees:
        current_rating = emp.get('performance_rating_percent', 100)
        # More variation for older period
        historical_rating = max(50, min(175, current_rating + random.randint(-20, 5)))

        snapshot_data = {
            'period_id': period2['id'],
            'associate_id': emp['associate_id'],
            'performance_rating': historical_rating,
            'bonus_allocation': historical_rating,
            'justification': f"Mid-year: Consistent contributor",
            'snapshot_name': emp['associate'],
            'snapshot_org': emp['supervisory_organization'],
            'snapshot_job_profile': emp['current_job_profile'],
            'snapshot_bonus_target_manager_currency': emp.get('bonus_target_manager_currency', 0) * 0.95,
            'archived_at': period2_date,
            'has_full_details': True,
            # Talent calibration snapshot data
            **generate_snapshot_talent_data(emp),
        }
        period2_snapshots.append(snapshot_data)

    periods.append((period2, period2_snapshots))

    # Period 3: For large team only - 18 months ago
    if include_large_history:
        period3_date = datetime.now() - timedelta(days=545)
        period3 = {
            'id': '2023-H2',
            'name': 'Second Half 2023',
            'notes': 'Annual review - restructuring year',
            'archived_at': period3_date,
        }

        period3_snapshots = []
        # Only include ~80% of employees (some are "new hires")
        for emp in employees:
            if random.random() > 0.2:  # 80% of employees existed
                current_rating = emp.get('performance_rating_percent', 100)
                historical_rating = max(55, min(170, current_rating + random.randint(-25, 0)))

                snapshot_data = {
                    'period_id': period3['id'],
                    'associate_id': emp['associate_id'],
                    'performance_rating': historical_rating,
                    'bonus_allocation': historical_rating,
                    'justification': None,  # Partial details for older period
                    'snapshot_name': emp['associate'],
                    'snapshot_org': emp['supervisory_organization'],
                    'snapshot_job_profile': emp['current_job_profile'],
                    'snapshot_bonus_target_manager_currency': emp.get('bonus_target_manager_currency', 0) * 0.90,
                    'archived_at': period3_date,
                    'has_full_details': False,  # Older period has less detail
                    # Talent calibration snapshot data (older period)
                    **generate_snapshot_talent_data(emp),
                }
                period3_snapshots.append(snapshot_data)

        periods.append((period3, period3_snapshots))

    return periods


def create_template_database(db_path, employees, include_large_history=False):
    """Create a template database with the given employees and historical periods."""
    # Remove existing database if any
    if os.path.exists(db_path):
        os.remove(db_path)

    # Create new database
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Add employees
        for emp_data in employees:
            employee = Employee(**emp_data)
            session.add(employee)

        # Add default bonus settings
        settings = BonusSettings(budget_override=0.0, last_updated=datetime.now())
        session.add(settings)

        # Add historical periods
        historical_periods = get_historical_periods(employees, include_large_history)
        total_snapshots = 0

        for period_data, snapshots in historical_periods:
            period = Period(**period_data)
            session.add(period)

            for snap_data in snapshots:
                snapshot = RatingSnapshot(**snap_data)
                session.add(snapshot)
                total_snapshots += 1

        session.commit()
        print(f"  Created {db_path} with {len(employees)} employees")
        print(f"  Added {len(historical_periods)} historical periods with {total_snapshots} snapshots")

    except Exception as e:
        session.rollback()
        print(f"  Error creating {db_path}: {e}")
        raise
    finally:
        session.close()


def main():
    print("Creating demo template databases...")
    print()

    # Determine paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    templates_dir = os.path.join(project_dir, 'demo-templates')

    # Create templates directory if needed
    os.makedirs(templates_dir, exist_ok=True)

    # Create small team template (2 historical periods)
    print("Small Team Demo (12 employees, 1 manager, 2 historical periods):")
    small_path = os.path.join(templates_dir, 'small-team.db')
    create_template_database(small_path, get_small_team_employees(), include_large_history=False)

    print()

    # Create large team template (3 historical periods)
    print("Large Team Demo (55 employees incl. 5 managers, 3 historical periods):")
    large_path = os.path.join(templates_dir, 'large-team.db')
    create_template_database(large_path, get_large_team_employees(), include_large_history=True)

    print()
    print("Done! Template databases created in demo-templates/")
    print()
    print("These databases will be copied for new demo sessions.")


if __name__ == '__main__':
    main()
