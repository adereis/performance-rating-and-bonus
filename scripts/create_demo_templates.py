#!/usr/bin/env python3
"""
Create pre-built demo template databases for the Performance Rating System.

This generates SQLite databases pre-populated with fictitious employee data
and ratings, ready to be copied for new demo sessions.

Usage:
    python3 scripts/create_demo_templates.py

Creates:
    demo-templates/small-team.db  - 12 employees, 1 manager, with ratings
    demo-templates/large-team.db  - 50 employees, 5 managers, with ratings
"""
import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Employee, BonusSettings, Period, RatingSnapshot


def get_small_team_employees():
    """
    Small team: 12 employees under single manager (Della Gate).
    Includes ratings and justifications.
    """
    manager = "Supervisory Organization (Della Gate)"

    # (name, job, salary, grade, bonus_pct, rating, justification)
    employees = [
        ('Paige Duty', 'Staff SRE', 180000, 'IC4', 3.75, 130, 'Exceptional technical leadership and on-call reliability'),
        ('Lee Latency', 'Senior Software Developer', 150000, 'IC3', 3.0, 120, 'Outstanding performance optimization work'),
        ('Mona Torr', 'Senior SRE', 145000, 'IC3', 3.0, 110, 'Strong monitoring and observability contributions'),
        ('Robin Rollback', 'Software Developer', 120000, 'IC2', 2.5, 105, 'Reliable deployment management'),
        ('Kenny Canary', 'Software Developer', 115000, 'IC2', 2.5, 100, 'Solid canary testing and deployment work'),
        ('Tracey Loggins', 'Senior SRE', 155000, 'IC3', 3.0, 115, 'Excellent logging infrastructure improvements'),
        ('Sue Q. Ell', 'Senior Software Developer', 148000, 'IC3', 3.0, 125, 'Outstanding database optimization and query performance'),
        ('Jason Blob', 'Software Developer', 118000, 'IC2', 2.5, 95, 'Good progress on unstructured data handling'),
        ('Al Ert', 'Staff SRE', 175000, 'IC4', 3.75, 135, 'Critical alerting system improvements, exceptional work'),
        ('Addie Min', 'Senior Software Developer', 152000, 'IC3', 3.0, 110, 'Solid access management and security work'),
        ('Tim Out', 'Software Developer', 110000, 'IC2', 2.5, 85, 'Needs improvement in reliability and uptime'),
        ('Barbie Que', 'Senior SRE', 149000, 'IC3', 3.0, 110, 'Strong message queue management'),
    ]

    result = []
    for i, (name, job, salary, grade, bonus_pct, rating, justification) in enumerate(employees):
        bonus_target = salary * (bonus_pct / 100)
        result.append({
            'associate_id': f'EMP{1000 + i}',
            'associate': name,
            'supervisory_organization': manager,
            'current_job_profile': job,
            'currency': 'USD',
            'current_base_pay_all_countries': salary,
            'current_base_pay_all_countries_usd': salary,
            'grade': grade,
            'annual_bonus_target_percent': bonus_pct,
            'bonus_target_local_currency': bonus_target,
            'bonus_target_local_currency_usd': bonus_target,
            'performance_rating_percent': rating,
            'justification': justification,
            'last_updated': datetime.now(),
        })

    return result


def get_large_team_employees():
    """
    Large org: 50 employees across 5 managers.
    Includes ratings and justifications with diverse performance levels.
    """
    teams = {
        'Platform Engineering (Della Gate)': [
            ('Paige Duty', 'Principal Engineer', 220000, 'IC5', 5.0, 140, 'Exceptional technical vision and platform architecture'),
            ('Lee Latency', 'Staff Software Developer', 185000, 'IC4', 3.75, 135, 'Outstanding team leadership and delivery'),
            ('Mona Torr', 'Staff SRE', 180000, 'IC4', 3.75, 130, 'Outstanding platform reliability improvements'),
            ('Robin Rollback', 'Senior Software Developer', 155000, 'IC3', 3.0, 115, 'Strong API development work'),
            ('Kenny Canary', 'Senior Software Developer', 150000, 'IC3', 3.0, 110, 'Solid infrastructure contributions'),
            ('Tracey Loggins', 'Software Developer', 125000, 'IC2', 2.5, 105, 'Good platform integration work'),
            ('Sue Q. Ell', 'Software Developer', 120000, 'IC2', 2.5, 100, 'Met expectations on service deployment'),
            ('Jason Blob', 'Software Developer', 115000, 'IC2', 2.5, 95, 'Steady progress on platform features'),
            ('Al Ert', 'Junior Software Developer', 95000, 'IC1', 2.0, 90, 'Needs more ownership of features'),
            ('Addie Min', 'Senior Software Developer', 160000, 'IC3', 3.0, 110, 'Solid mentorship and code quality'),
        ],
        'Frontend Experience (Rhoda Map)': [
            ('Tim Out', 'Principal Engineer', 225000, 'IC5', 5.0, 185, 'Exceptional performance - transformational UI architecture work'),
            ('Barbie Que', 'Staff Software Developer', 190000, 'IC4', 3.75, 130, 'Strong team growth and technical direction'),
            ('Terry Byte', 'Senior Software Developer', 160000, 'IC3', 3.0, 120, 'Strong React component library work'),
            ('Nole Pointer', 'Senior Software Developer', 155000, 'IC3', 3.0, 110, 'Solid accessibility improvements'),
            ('Marge Conflict', 'Software Developer', 125000, 'IC2', 2.5, 45, 'Serious performance concerns - requires improvement plan'),
            ('Bridget Branch', 'Software Developer', 120000, 'IC2', 2.5, 100, 'Good responsive design work'),
            ('Cody Ryder', 'Senior Software Developer', 158000, 'IC3', 3.0, 115, 'Excellent state management refactoring'),
            ('Cy Ferr', 'Software Developer', 118000, 'IC2', 2.5, 100, 'Solid component development'),
            ('Phil Wall', 'Junior Software Developer', 92000, 'IC1', 2.0, 65, 'Below expectations - needs significant improvement'),
            ('Lana Wan', 'Software Developer', 122000, 'IC2', 2.5, 85, 'Needs more proactive communication'),
        ],
        'Backend Services (Kay P. Eye)': [
            ('Artie Ficial', 'Principal Engineer', 230000, 'IC5', 5.0, 140, 'Exceptional distributed systems architecture'),
            ('Ruth Cause', 'Staff Software Developer', 188000, 'IC4', 3.75, 130, 'Outstanding microservices design'),
            ('Matt Rick', 'Staff Software Developer', 185000, 'IC4', 3.75, 130, 'Excellent cross-team coordination and delivery'),
            ('Cassie Cache', 'Senior Software Developer', 162000, 'IC3', 3.0, 120, 'Strong API design and implementation'),
            ('Sue Do', 'Senior Software Developer', 158000, 'IC3', 3.0, 110, 'Solid service reliability work'),
            ('Pat Ch', 'Software Developer', 128000, 'IC2', 2.5, 105, 'Good backend feature development'),
            ('Devin Null', 'Software Developer', 124000, 'IC2', 2.5, 100, 'Met expectations on service development'),
            ('Justin Time', 'Software Developer', 120000, 'IC2', 2.5, 95, 'Steady progress on REST API work'),
            ("Annie O'Maly", 'Senior Software Developer', 165000, 'IC3', 3.0, 115, 'Strong database optimization'),
            ('Sam Box', 'Junior Software Developer', 98000, 'IC1', 2.0, 90, 'Adequate progress on microservices'),
        ],
        'Infrastructure (Agie Enda)': [
            ('Val Idation', 'Staff SRE', 195000, 'IC4', 3.75, 120, 'Outstanding infrastructure automation'),
            ('Bill Ding', 'Senior SRE', 165000, 'IC3', 3.0, 105, 'Good deployment pipeline work'),
            ('Ty Po', 'Principal Engineer', 235000, 'IC5', 5.0, 135, 'Exceptional infrastructure modernization'),
            ('Mike Roservices', 'Staff SRE', 192000, 'IC4', 3.75, 130, 'Strong infrastructure team leadership'),
            ('Lou Pe', 'Senior SRE', 168000, 'IC3', 3.0, 120, 'Outstanding CI/CD pipeline improvements'),
            ('Connie Tainer', 'Senior SRE', 162000, 'IC3', 3.0, 110, 'Strong Kubernetes migration work'),
            ('Noah Node', 'SRE', 130000, 'IC2', 2.5, 105, 'Good infrastructure automation'),
            ('Sara Ver', 'SRE', 125000, 'IC2', 2.5, 100, 'Solid monitoring setup'),
            ('Exa M. Elle', 'Senior SRE', 170000, 'IC3', 3.0, 115, 'Strong cloud cost optimization'),
            ('Dee Ploi', 'SRE', 128000, 'IC2', 2.5, 95, 'Good disaster recovery planning'),
        ],
        'Site Reliability (Mai Stone)': [
            ("Ray D. O'Button", 'Principal SRE', 228000, 'IC5', 5.0, 135, 'Outstanding SLO/SLI framework design'),
            ('Cam Elcase', 'Staff SRE', 198000, 'IC4', 3.75, 130, 'Excellent reliability culture building'),
            ('Hashim Map', 'Staff SRE', 195000, 'IC4', 3.75, 125, 'Exceptional on-call process improvements'),
            ('Ben Chmark', 'Senior SRE', 172000, 'IC3', 3.0, 120, 'Strong incident response leadership'),
            ('Grace Full', 'Senior SRE', 168000, 'IC3', 3.0, 110, 'Solid observability improvements'),
            ('Shel Script', 'Senior SRE', 165000, 'IC3', 3.0, 110, 'Strong monitoring and alerting work'),
            ('Sal T. Hash', 'SRE', 135000, 'IC2', 2.5, 100, 'Good chaos engineering initiatives'),
            ('Red Undancy', 'SRE', 132000, 'IC2', 2.5, 105, 'Solid failover testing'),
            ('Mo Nitor', 'Senior SRE', 175000, 'IC3', 3.0, 115, 'Strong performance monitoring'),
            ('Polly Morphism', 'SRE', 128000, 'IC2', 2.5, 95, 'Good system flexibility improvements'),
        ],
    }

    result = []
    emp_id = 2000

    for team_name, members in teams.items():
        for (name, job, salary, grade, bonus_pct, rating, justification) in members:
            bonus_target = salary * (bonus_pct / 100)
            result.append({
                'associate_id': f'EMP{emp_id}',
                'associate': name,
                'supervisory_organization': team_name,
                'current_job_profile': job,
                'currency': 'USD',
                'current_base_pay_all_countries': salary,
                'current_base_pay_all_countries_usd': salary,
                'grade': grade,
                'annual_bonus_target_percent': bonus_pct,
                'bonus_target_local_currency': bonus_target,
                'bonus_target_local_currency_usd': bonus_target,
                'performance_rating_percent': rating,
                'justification': justification,
                'last_updated': datetime.now(),
            })
            emp_id += 1

    return result


def get_historical_periods(employees, include_large_history=False):
    """
    Generate historical period data based on current employees.
    Creates 2 periods for small team, 3 for large team.

    Returns list of (period_data, snapshots) tuples.
    """
    from datetime import timedelta
    import random

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

        period1_snapshots.append({
            'period_id': period1['id'],
            'associate_id': emp['associate_id'],
            'performance_rating': historical_rating,
            'bonus_allocation': historical_rating,  # Simplified
            'justification': f"Previous cycle: {emp.get('justification', 'Standard performance')}",
            'snapshot_name': emp['associate'],
            'snapshot_org': emp['supervisory_organization'],
            'snapshot_job_profile': emp['current_job_profile'],
            'snapshot_bonus_target_usd': emp.get('bonus_target_local_currency_usd'),
            'archived_at': period1_date,
            'has_full_details': True,
        })

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

        period2_snapshots.append({
            'period_id': period2['id'],
            'associate_id': emp['associate_id'],
            'performance_rating': historical_rating,
            'bonus_allocation': historical_rating,
            'justification': f"Mid-year: Consistent contributor",
            'snapshot_name': emp['associate'],
            'snapshot_org': emp['supervisory_organization'],
            'snapshot_job_profile': emp['current_job_profile'],
            'snapshot_bonus_target_usd': emp.get('bonus_target_local_currency_usd', 0) * 0.95,  # Slightly lower target
            'archived_at': period2_date,
            'has_full_details': True,
        })

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

                period3_snapshots.append({
                    'period_id': period3['id'],
                    'associate_id': emp['associate_id'],
                    'performance_rating': historical_rating,
                    'bonus_allocation': historical_rating,
                    'justification': None,  # Partial details for older period
                    'snapshot_name': emp['associate'],
                    'snapshot_org': emp['supervisory_organization'],
                    'snapshot_job_profile': emp['current_job_profile'],
                    'snapshot_bonus_target_usd': emp.get('bonus_target_local_currency_usd', 0) * 0.90,
                    'archived_at': period3_date,
                    'has_full_details': False,  # Older period has less detail
                })

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
        settings = BonusSettings(budget_override_usd=0.0, last_updated=datetime.now())
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
    print("Large Team Demo (50 employees, 5 managers, 3 historical periods):")
    large_path = os.path.join(templates_dir, 'large-team.db')
    create_template_database(large_path, get_large_team_employees(), include_large_history=True)

    print()
    print("Done! Template databases created in demo-templates/")
    print()
    print("These databases will be copied for new demo sessions.")


if __name__ == '__main__':
    main()
