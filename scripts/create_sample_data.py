#!/usr/bin/env python3
"""
Create sample demo data for the Performance Rating System.
This generates fictitious Workday employee data (no ratings/tenets).

Usage:
    python3 create_sample_data.py              # Creates small team (12 employees, 1 manager)
    python3 create_sample_data.py --large      # Creates large org (55 employees: 5 managers + 50 ICs)
    python3 create_sample_data.py --historical # Creates 6 quarterly historical spreadsheets

Note: This generates ONLY Workday export data (salaries, bonus targets, org structure).
      To add sample ratings/tenets, use populate_sample_ratings.py after import.
"""
import openpyxl
from openpyxl import Workbook
import random
import sys
import os

# Add parent directory to path for imports when running as standalone script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notes_parser import format_notes_field


def create_headers(sheet):
    """Add standard Workday export headers (exactly as they come from Workday)."""
    # Row 1: Empty (matches Workday export format)
    sheet.append([])

    # Row 2: Headers (matches Workday export structure ONLY - no manager-entered fields)
    headers = [
        'Associate',
        'Supervisory Organization',
        'Current Job Profile',
        'Photo',
        'Errors',
        'Associate ID',
        'Current Base Pay All Countries',
        'Current Base Pay All Countries (USD)',
        'Currency',
        'Grade',
        'Annual Bonus Target Percent',
        'Last Bonus Allocation Percent',
        'Bonus Target - Local Currency',
        'Bonus Target - Local Currency (USD)',
        'Proposed Bonus Amount',
        'Proposed Bonus Amount (USD)',
        'Proposed Percent of Target Bonus',
        'Notes',
        'Zero Bonus Allocated'
    ]

    sheet.append(headers)


def get_small_team_data():
    """
    Small team: 12 employees under single manager (Della Gate).
    Perfect for testing with a manageable dataset.
    Generates Workday data only (no ratings/tenets).
    """
    # Workday format: "Supervisory Organization (Manager Name)"
    manager = "Supervisory Organization (Della Gate)"

    # (name, job, salary, grade, bonus_pct)
    # Bonus percentages are for the rating period (configure as needed for your org)
    employees = [
        ('Paige Duty', 'Staff SRE', 180000, 'IC4', 3.75),
        ('Lee Latency', 'Senior Software Developer', 150000, 'IC3', 3.0),
        ('Mona Torr', 'Senior SRE', 145000, 'IC3', 3.0),
        ('Robin Rollback', 'Software Developer', 120000, 'IC2', 2.5),
        ('Kenny Canary', 'Software Developer', 115000, 'IC2', 2.5),
        ('Tracey Loggins', 'Senior SRE', 155000, 'IC3', 3.0),
        ('Sue Q. Ell', 'Senior Software Developer', 148000, 'IC3', 3.0),
        ('Jason Blob', 'Software Developer', 118000, 'IC2', 2.5),
        ('Al Ert', 'Staff SRE', 175000, 'IC4', 3.75),
        ('Addie Min', 'Senior Software Developer', 152000, 'IC3', 3.0),
        ('Tim Out', 'Software Developer', 110000, 'IC2', 2.5),
        ('Barbie Que', 'Senior SRE', 149000, 'IC3', 3.0),
    ]

    result = []
    for i, (name, job, salary, grade, bonus_pct) in enumerate(employees):
        result.append({
            'associate': name,
            'supervisory_organization': manager,
            'job_profile': job,
            'salary': salary,
            'salary_local': salary,  # USD employees
            'currency': 'USD',
            'grade': grade,
            'bonus_pct': bonus_pct,
            'associate_id': f'EMP{1000 + i}'
        })

    return result


def get_large_org_data():
    """
    Large org: 55 employees across 5 managers (50 ICs + 5 managers).
    Tests multi-manager/multi-org scenario with international employees.
    Matches Workday export format where Supervisory Organization = "Supervisory Organization (Manager Name)"

    The 5 managers (Della Gate, Rhoda Map, Kay P. Eye, Agie Enda, Mai Stone) are included
    in the employee database and report to a VP (not in database).
    """
    # Manager names from Gemini 3
    # Format matches Workday: "Supervisory Organization (Manager Name)"
    managers = {
        'Della Gate': 'Supervisory Organization (Della Gate)',
        'Rhoda Map': 'Supervisory Organization (Rhoda Map)',
        'Kay P. Eye': 'Supervisory Organization (Kay P. Eye)',
        'Agie Enda': 'Supervisory Organization (Agie Enda)',
        'Mai Stone': 'Supervisory Organization (Mai Stone)'
    }

    # Director who manages the managers (not included in employee list - would be rated separately)
    director_org = 'Supervisory Organization (Director)'

    # Tech-themed employee names
    names = [
        'Paige Duty', 'Lee Latency', 'Mona Torr', 'Robin Rollback',
        'Kenny Canary', 'Tracey Loggins', 'Sue Q. Ell', 'Jason Blob',
        'Al Ert', 'Addie Min', 'Tim Out', 'Barbie Que',
        'Terry Byte', 'Nole Pointer', 'Marge Conflict', 'Bridget Branch',
        'Cody Ryder', 'Cy Ferr', 'Phil Wall', 'Lana Wan',
        'Artie Ficial', 'Ruth Cause', 'Matt Rick', 'Cassie Cache',
        'Sue Do', 'Pat Ch', 'Devin Null', 'Justin Time',
        'Annie O\'Maly', 'Sam Box', 'Val Idation', 'Bill Ding',
        'Ty Po', 'Mike Roservices', 'Lou Pe', 'Connie Tainer',
        'Noah Node', 'Sara Ver', 'Exa M. Elle', 'Dee Ploi',
        'Ray D. O\'Button', 'Cam Elcase', 'Hashim Map', 'Ben Chmark',
        'Grace Full', 'Shel Script', 'Sal T. Hash', 'Reba Boot',
        'Stan Dup', 'Kay Eight'
    ]

    # Job profiles per team (Workday data only - no ratings/justifications)
    # Format: (job, salary, grade, bonus_pct) for USD employees
    #         (job, salary_usd, grade, bonus_pct, currency, salary_local) for international
    # NOTE: Bonus percentages are for the rating period: IC2=2.5%, IC3=3%, IC4=3.75%, IC5=5%, M3=4.5%
    team_configs = {
        'Supervisory Organization (Della Gate)': [
            ('Principal Software Developer', 220000, 'IC5', 5),
            ('Staff Software Developer', 180000, 'IC4', 3.75),
            ('Staff Software Developer', 175000, 'IC4', 3.75),
            ('Senior Software Developer', 150000, 'IC3', 3),
            ('Senior Software Developer', 145000, 'IC3', 3),
            ('Software Developer', 120000, 'IC2', 2.5),
            ('Software Developer', 115000, 'IC2', 2.5),
            ('Software Developer', 118000, 'IC2', 2.5),
            ('Software Developer', 112000, 'IC2', 2.5),
            ('Senior Software Developer', 152000, 'IC3', 3),
        ],
        'Supervisory Organization (Rhoda Map)': [
            ('Staff Software Developer', 175000, 'IC4', 3.75),
            ('Staff Software Developer', 172000, 'IC4', 3.75),
            ('Senior Software Developer', 155000, 'IC3', 3),
            ('Senior Software Developer', 149000, 'IC3', 3),
            ('Software Developer', 110000, 'IC2', 2.5),
            ('Software Developer', 125000, 'IC2', 2.5),
            ('Senior Software Developer', 147000, 'IC3', 3),
            ('Software Developer', 122000, 'IC2', 2.5),
            ('Software Developer', 119000, 'IC2', 2.5),
            ('Software Developer', 116000, 'IC2', 2.5),
        ],
        'Supervisory Organization (Kay P. Eye)': [
            ('Principal Software Developer', 215000, 'IC5', 5),
            ('Staff Software Developer', 182000, 'IC4', 3.75),
            ('Staff Software Developer', 178000, 'IC4', 3.75),
            ('Senior Software Developer', 158000, 'IC3', 3),
            ('Senior Software Developer', 152000, 'IC3', 3),
            ('Software Developer', 128000, 'IC2', 2.5),
            ('Software Developer', 122000, 'IC2', 2.5),
            ('Software Developer', 118000, 'IC2', 2.5),
            ('Senior Software Developer', 155000, 'IC3', 3),
            ('Software Developer', 125000, 'IC2', 2.5),
        ],
        'Supervisory Organization (Agie Enda)': [
            ('Senior SRE', 132911, 'IC3', 3, 'GBP', 105000),
            ('SRE', 98734, 'IC2', 2.5, 'GBP', 78000),
            ('Staff SRE', 185000, 'IC4', 3.75),
            ('Staff SRE', 183000, 'IC4', 3.75),
            ('Senior SRE', 155000, 'IC3', 3),
            ('Senior SRE', 152000, 'IC3', 3),
            ('SRE', 125000, 'IC2', 2.5),
            ('SRE', 122000, 'IC2', 2.5),
            ('Senior SRE', 148000, 'IC3', 3),
            ('SRE', 130000, 'IC2', 2.5),
        ],
        'Supervisory Organization (Mai Stone)': [
            ('Staff SRE', 188000, 'IC4', 3.75),
            ('Staff SRE', 186000, 'IC4', 3.75),
            ('Senior SRE', 160000, 'IC3', 3),
            ('Senior SRE', 156000, 'IC3', 3),
            ('Senior SRE', 153000, 'IC3', 3),
            ('SRE', 128000, 'IC2', 2.5),
            ('SRE', 124000, 'IC2', 2.5),
            ('SRE', 120000, 'IC2', 2.5),
            ('SRE', 118000, 'IC2', 2.5),
            ('SRE', 115000, 'IC2', 2.5),
        ],
    }

    result = []
    name_idx = 0

    # First, add the 5 managers themselves as employees reporting to Director
    manager_salaries = [210000, 205000, 215000, 208000, 212000]  # M3 level salaries
    for idx, (manager_name, org) in enumerate(managers.items()):
        result.append({
            'associate': manager_name,
            'supervisory_organization': director_org,
            'job_profile': 'Engineering Manager',
            'salary': manager_salaries[idx],
            'salary_local': manager_salaries[idx],
            'currency': 'USD',
            'grade': 'M3',
            'bonus_pct': 4.5,  # Bonus target for M3 managers
            'associate_id': f'MGR{100 + idx}'
        })

    # Then add all the ICs (individual contributors) reporting to each manager
    for manager_name, org in managers.items():
        configs = team_configs[org]

        for config in configs:
            if len(config) == 6:  # International employee
                job, salary_usd, grade, bonus_pct, currency, salary_local = config
            else:
                job, salary_usd, grade, bonus_pct = config
                currency = 'USD'
                salary_local = salary_usd

            result.append({
                'associate': names[name_idx],
                'supervisory_organization': org,
                'job_profile': job,
                'salary': salary_usd,
                'salary_local': salary_local,
                'currency': currency,
                'grade': grade,
                'bonus_pct': bonus_pct,
                'associate_id': f'EMP{1000 + name_idx}'
            })

            name_idx += 1

    return result


def write_employee_data(sheet, employees):
    """Write employee data to worksheet (Workday data only)."""
    for i, emp in enumerate(employees):
        # Bonus calculations
        if emp['currency'] == 'USD':
            base_pay_local = emp['salary']
            base_pay_usd = None
            bonus_target_local = emp['salary'] * (emp['bonus_pct'] / 100)
            bonus_target_usd = None
        else:
            base_pay_local = emp['salary_local']
            base_pay_usd = emp['salary']
            bonus_target_local = emp['salary_local'] * (emp['bonus_pct'] / 100)
            bonus_target_usd = emp['salary'] * (emp['bonus_pct'] / 100)

        # Last bonus allocation (previous period)
        last_bonus_pct = random.choice([None, None, None, 85, 90, 95, 100, 105, 110, 115])

        row = [
            emp['associate'],
            emp['supervisory_organization'],
            emp['job_profile'],
            '',  # Photo
            '',  # Errors
            emp['associate_id'],
            base_pay_local,
            base_pay_usd,
            emp['currency'],
            emp['grade'],
            emp['bonus_pct'],
            last_bonus_pct,
            bonus_target_local,
            bonus_target_usd,
            None,  # Proposed bonus
            None,  # Proposed bonus USD
            None,  # Proposed percent
            '',  # Notes
            ''  # Zero bonus allocated
        ]

        sheet.append(row)


def create_sample_xlsx(size='small'):
    """
    Create sample-data.xlsx with fictitious Workday employee data (no ratings/tenets).

    Args:
        size: 'small' for 12 employees (1 manager), 'large' for 55 employees (5 managers + 50 ICs)
    """
    wb = Workbook()
    sheet = wb.active

    create_headers(sheet)

    if size == 'small':
        employees = get_small_team_data()
        filename = 'sample-data-small.xlsx'
        description = "12 employees under 1 manager (Della Gate)"
    else:
        employees = get_large_org_data()
        filename = 'sample-data-large.xlsx'
        description = "55 employees (5 managers + 50 ICs)"

    write_employee_data(sheet, employees)

    # Save the workbook
    wb.save(filename)

    print(f"✓ Created {filename}")
    print(f"  - {description}")
    if size == 'large':
        print(f"  - Managers: Della Gate, Rhoda Map, Kay P. Eye, Agie Enda, Mai Stone")
    print(f"  - Total employees: {len(employees)}")
    us_count = sum(1 for e in employees if e['currency'] == 'USD')
    intl_count = len(employees) - us_count
    if intl_count > 0:
        print(f"  - {us_count} US-based (USD), {intl_count} international (GBP)")
    else:
        print(f"  - All US-based (USD)")
    print(f"\nNext steps:")
    print(f"  1. python3 convert_xlsx.py {filename}")
    print(f"  2. python3 populate_sample_ratings.py {size}")
    print(f"  3. python3 app.py")


def get_historical_employee_timelines():
    """
    Define employee timelines for historical data generation.
    Returns dict of associate_id -> timeline info.

    Timeline info includes:
    - joined_quarter: First quarter they appear (None = always there)
    - left_after_quarter: Last quarter they appear (None = still active)
    - promotions: dict of quarter -> (new_job_title, new_grade, new_salary_delta)
    - pre_promotion: (job_title, grade, salary_delta) - state BEFORE first promotion
    - performance_pattern: 'steady', 'improving', 'declining', 'variable'
    """
    return {
        # People who left
        'EMP1005': {  # Robin Rollback - left mid-2024
            'left_after_quarter': '2024-Q1',
            'performance_pattern': 'declining',
        },
        'EMP1015': {  # Bridget Branch - left in 2023
            'left_after_quarter': '2023-Q4',
            'performance_pattern': 'steady',
        },
        'MGR102': {  # Kay P. Eye - manager who left
            'left_after_quarter': '2024-Q2',
            'performance_pattern': 'steady',
        },

        # People who joined recently
        'EMP1048': {  # Stan Dup - joined Q2 2024
            'joined_quarter': '2024-Q2',
            'performance_pattern': 'improving',
        },
        'EMP1049': {  # Kay Eight - joined Q3 2024
            'joined_quarter': '2024-Q3',
            'performance_pattern': 'steady',
        },
        'EMP1042': {  # Cam Elcase - joined Q1 2024
            'joined_quarter': '2024-Q1',
            'performance_pattern': 'variable',
        },

        # People who got promoted (pre_promotion defines their state BEFORE any promotions)
        'EMP1000': {  # Paige Duty - promoted from IC4 to IC5 in Q1 2024
            'pre_promotion': ('Staff Software Developer', 'IC4', -30000),  # Was IC4 before
            'promotions': {
                '2024-Q1': ('Principal Software Developer', 'IC5', 30000),
            },
            'performance_pattern': 'improving',
        },
        'EMP1003': {  # Lee Latency - promoted from IC3 to IC4 in Q3 2024
            'pre_promotion': ('Senior Software Developer', 'IC3', -25000),
            'promotions': {
                '2024-Q3': ('Staff Software Developer', 'IC4', 25000),
            },
            'performance_pattern': 'steady',
        },
        'EMP1020': {  # Artie Ficial - promoted from IC2 to IC3 in Q4 2023
            'pre_promotion': ('Software Developer', 'IC2', -20000),
            'promotions': {
                '2023-Q4': ('Senior Software Developer', 'IC3', 20000),
            },
            'performance_pattern': 'improving',
        },
        'EMP1030': {  # Noah Node - promoted twice! IC2 -> IC3 (Q4 2023) -> IC4 (Q3 2024)
            'pre_promotion': ('SRE', 'IC2', -43000),  # Total salary increase is 18k + 25k = 43k
            'promotions': {
                '2023-Q4': ('Senior SRE', 'IC3', 18000),
                '2024-Q3': ('Staff SRE', 'IC4', 25000),
            },
            'performance_pattern': 'improving',
        },

        # Variable performers (for interesting history)
        'EMP1010': {  # Kenny Canary
            'performance_pattern': 'variable',
        },
        'EMP1025': {  # Sue Do
            'performance_pattern': 'declining',
        },
    }


# Tenet names for historical data (human-readable, not IDs)
HISTORICAL_TENETS = [
    'Delete More Than You Add',
    'Leave the Campfire Cleaner',
    'Tests or It\'s a Hallucination',
    'Comments are Apologies',
    'Ship It to Learn It',
    'YAGNI (You Ain\'t Gonna Need It)',
    'Fail Fast, Fix Faster',
    'Sleep is a Feature',
    'Automate Yourself Out of a Job',
    'Treat Servers Like Cattle, Not Pets',
    'Be a Rubber Duck',
    'Blame the Process, Not the Person',
    'Strong Opinions, Loosely Held',
]

# Sample justifications for different performance levels
JUSTIFICATIONS = {
    'exceptional': [
        "Consistently delivered outstanding results. Led major initiatives and mentored junior team members effectively.",
        "Exceptional technical leadership and cross-team collaboration. Drove significant improvements in system reliability.",
        "Outstanding performance across all dimensions. Key contributor to critical project deliveries.",
    ],
    'exceeds': [
        "Strong performance with notable achievements in code quality and team collaboration.",
        "Exceeded expectations on key deliverables. Good balance of individual contribution and team support.",
        "Solid technical growth and increasing impact on team success.",
    ],
    'meets': [
        "Met all expectations. Reliable contributor with consistent delivery.",
        "Solid performance. Completed assigned work on time with good quality.",
        "Dependable team member who delivers consistently.",
    ],
    'needs_improvement': [
        "Needs improvement in time management and delivery consistency.",
        "Technical skills developing but requires more focus on quality.",
        "Performance below expectations. Clear development plan established.",
    ],
}


def generate_rating_for_pattern(pattern, quarter_index):
    """
    Generate a performance rating based on pattern and quarter index.
    quarter_index: 0 = oldest (2023-Q3), 5 = newest (2024-Q4)
    """
    base_ratings = {
        'steady': [100, 100, 100, 100, 100, 100],
        'improving': [85, 90, 100, 110, 115, 125],
        'declining': [120, 115, 105, 95, 85, 75],
        'variable': [110, 85, 120, 95, 130, 100],
    }
    base = base_ratings.get(pattern, base_ratings['steady'])[quarter_index]
    # Add some randomness
    return max(50, min(185, base + random.randint(-10, 10)))


def generate_justification(rating):
    """Generate appropriate justification based on rating."""
    if rating >= 130:
        return random.choice(JUSTIFICATIONS['exceptional'])
    elif rating >= 110:
        return random.choice(JUSTIFICATIONS['exceeds'])
    elif rating >= 90:
        return random.choice(JUSTIFICATIONS['meets'])
    else:
        return random.choice(JUSTIFICATIONS['needs_improvement'])


def generate_historical_notes(rating, include_full_details=True):
    """
    Generate the Notes field content for historical import.
    Some records have incomplete info (only rating, or nothing at all).
    """
    if not include_full_details:
        # Incomplete record - maybe just rating or nothing
        choice = random.choice(['rating_only', 'partial', 'empty'])
        if choice == 'empty':
            return ''
        elif choice == 'rating_only':
            return f"Performance Rating: {rating}%"
        else:
            # Partial - rating and justification only
            return format_notes_field(
                performance_rating=rating,
                justification=generate_justification(rating),
            )

    # Full details
    strengths = random.sample(HISTORICAL_TENETS, 3)
    improvements = random.sample([t for t in HISTORICAL_TENETS if t not in strengths], random.choice([2, 3]))

    # Random mentor from employee names
    mentors = ['Della Gate', 'Rhoda Map', 'Kay P. Eye', 'Agie Enda', 'Mai Stone',
               'Paige Duty', 'Lee Latency', 'Al Ert', 'Terry Byte']
    mentor = random.choice(mentors) if random.random() > 0.3 else None

    # Random mentees
    mentees_list = ['Tim Out', 'Robin Rollback', 'Kenny Canary', 'Jason Blob',
                   'Ty Po', 'Lou Pe', 'Sam Box', 'Pat Ch']
    mentees = ', '.join(random.sample(mentees_list, random.randint(0, 2))) or None

    return format_notes_field(
        performance_rating=rating,
        justification=generate_justification(rating),
        mentor=mentor,
        mentees=mentees,
        tenets_strengths=', '.join(strengths),
        tenets_improvements=', '.join(improvements),
    )


def quarter_to_index(quarter):
    """Convert quarter string to index (0-5)."""
    quarters = ['2023-Q3', '2023-Q4', '2024-Q1', '2024-Q2', '2024-Q3', '2024-Q4']
    return quarters.index(quarter)


def is_employee_active_in_quarter(emp_id, quarter, timelines):
    """Check if employee was active during a given quarter."""
    q_idx = quarter_to_index(quarter)

    timeline = timelines.get(emp_id, {})

    # Check if joined yet
    joined = timeline.get('joined_quarter')
    if joined and quarter_to_index(joined) > q_idx:
        return False

    # Check if already left
    left = timeline.get('left_after_quarter')
    if left and quarter_to_index(left) < q_idx:
        return False

    return True


def get_employee_job_for_quarter(emp, quarter, timelines):
    """
    Get the job title, grade, and salary for an employee in a specific quarter.
    Accounts for promotions using the pre_promotion field as starting point.

    For employees with promotions:
    - pre_promotion defines their state BEFORE any promotions
    - promotions dict defines when they got promoted

    Example: EMP1000 promoted IC4->IC5 in 2024-Q1
    - 2023-Q3, 2023-Q4: Uses pre_promotion (Staff Software Developer, IC4)
    - 2024-Q1 onwards: Applies promotion (Principal Software Developer, IC5)
    """
    q_idx = quarter_to_index(quarter)
    emp_id = emp['associate_id']

    timeline = timelines.get(emp_id, {})
    promotions = timeline.get('promotions', {})
    pre_promotion = timeline.get('pre_promotion')

    # Start with base values from employee data
    job = emp['job_profile']
    grade = emp['grade']
    salary = emp['salary']
    salary_local = emp.get('salary_local', salary)

    # If employee has promotions, start from pre_promotion state
    if pre_promotion and promotions:
        pre_job, pre_grade, salary_delta = pre_promotion
        job = pre_job
        grade = pre_grade
        # salary_delta is negative (difference from current to pre-promotion)
        salary = emp['salary'] + salary_delta
        salary_local = emp.get('salary_local', emp['salary']) + salary_delta

    # Apply promotions that happened before or during this quarter
    quarters = ['2023-Q3', '2023-Q4', '2024-Q1', '2024-Q2', '2024-Q3', '2024-Q4']
    for promo_q in quarters[:q_idx + 1]:
        if promo_q in promotions:
            new_job, new_grade, promo_salary_delta = promotions[promo_q]
            job = new_job
            grade = new_grade
            salary += promo_salary_delta
            salary_local += promo_salary_delta

    return job, grade, salary, salary_local


def get_bonus_pct_for_grade(grade):
    """Get bonus percentage for a grade."""
    bonus_map = {
        'IC2': 2.5,
        'IC3': 3.0,
        'IC4': 3.75,
        'IC5': 5.0,
        'M3': 4.5,
    }
    return bonus_map.get(grade, 3.0)


def write_historical_employee_data(sheet, employees, quarter, timelines):
    """
    Write employee data for a specific historical quarter.
    Includes Notes field with rating data and Proposed % of Target Bonus.
    """
    q_idx = quarter_to_index(quarter)

    for emp in employees:
        emp_id = emp['associate_id']

        # Skip if employee wasn't active in this quarter
        if not is_employee_active_in_quarter(emp_id, quarter, timelines):
            continue

        # Get job info accounting for promotions
        job, grade, salary, salary_local = get_employee_job_for_quarter(emp, quarter, timelines)
        bonus_pct = get_bonus_pct_for_grade(grade)

        # Determine performance pattern
        timeline = timelines.get(emp_id, {})
        pattern = timeline.get('performance_pattern', 'steady')

        # Generate rating
        rating = generate_rating_for_pattern(pattern, q_idx)

        # Some records have incomplete info (about 15% chance)
        include_full_details = random.random() > 0.15

        # Generate Notes field with rating data
        notes = generate_historical_notes(rating, include_full_details)

        # Calculate bonus allocation (slight variation from rating due to normalization)
        bonus_allocation = rating * random.uniform(0.95, 1.05) if notes else None

        # Last bonus allocation (from previous quarter)
        last_bonus_pct = random.choice([None, None, 85, 90, 95, 100, 105, 110, 115])

        # Build row
        currency = emp.get('currency', 'USD')
        if currency == 'USD':
            base_pay_local = salary
            base_pay_usd = None
            bonus_target_local = salary * (bonus_pct / 100)
            bonus_target_usd = None
        else:
            base_pay_local = salary_local
            base_pay_usd = salary
            bonus_target_local = salary_local * (bonus_pct / 100)
            bonus_target_usd = salary * (bonus_pct / 100)

        row = [
            emp['associate'],
            emp['supervisory_organization'],
            job,  # Use potentially updated job title
            '',  # Photo
            '',  # Errors
            emp_id,
            base_pay_local,
            base_pay_usd,
            currency,
            grade,  # Use potentially updated grade
            bonus_pct,
            last_bonus_pct,
            bonus_target_local,
            bonus_target_usd,
            None,  # Proposed bonus amount
            None,  # Proposed bonus USD
            round(bonus_allocation, 1) if bonus_allocation else None,  # Proposed % of target
            notes,  # Notes with rating data
            ''  # Zero bonus allocated
        ]

        sheet.append(row)


def create_historical_xlsx():
    """
    Create 6 quarterly historical spreadsheets for testing history feature.

    Includes corner cases:
    - Employees who left (appear in earlier quarters, not later)
    - Employees who joined recently (appear in later quarters, not earlier)
    - Promotions (different job titles across quarters)
    - Incomplete information (some Notes fields missing data)
    """
    quarters = ['2023-Q3', '2023-Q4', '2024-Q1', '2024-Q2', '2024-Q3', '2024-Q4']

    # Get base employee data (large org)
    employees = get_large_org_data()

    # Get timelines (who joined, left, got promoted)
    timelines = get_historical_employee_timelines()

    print("Creating historical quarterly data...")
    print("=" * 60)

    for quarter in quarters:
        wb = Workbook()
        sheet = wb.active

        create_headers(sheet)
        write_historical_employee_data(sheet, employees, quarter, timelines)

        filename = f'samples/sample-historical-{quarter}.xlsx'
        wb.save(filename)

        # Count employees in this quarter
        active_count = sum(1 for emp in employees
                         if is_employee_active_in_quarter(emp['associate_id'], quarter, timelines))

        print(f"✓ Created {filename} ({active_count} employees)")

    print("=" * 60)
    print()
    print("Corner cases included:")
    print("  - EMP1005 (Robin Rollback): Left after 2024-Q1")
    print("  - EMP1015 (Bridget Branch): Left after 2023-Q4")
    print("  - MGR102 (Kay P. Eye): Manager who left after 2024-Q2")
    print("  - EMP1048 (Stan Dup): Joined in 2024-Q2")
    print("  - EMP1049 (Kay Eight): Joined in 2024-Q3")
    print("  - EMP1042 (Cam Elcase): Joined in 2024-Q1")
    print("  - EMP1000 (Paige Duty): Promoted IC4→IC5 in 2024-Q1")
    print("  - EMP1003 (Lee Latency): Promoted IC3→IC4 in 2024-Q3")
    print("  - EMP1020 (Artie Ficial): Promoted IC2→IC3 in 2023-Q4")
    print("  - EMP1030 (Noah Node): Promoted IC2→IC3 (2023-Q4) and IC3→IC4 (2024-Q3)")
    print("  - ~15% of records have incomplete Notes data")
    print()
    print("To import historical data:")
    print("  1. Start the app: python3 app.py")
    print("  2. Go to Import page")
    print("  3. For each quarter file, select 'Historical Period' import type")
    print("  4. Enter period ID (e.g., '2023-Q3') and name (e.g., 'Q3 2023')")
    print("  5. Import all 6 files in chronological order")


def main():
    """Main entry point with argument parsing."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Create sample demo data for the Performance Rating System.',
        epilog='''
Examples:
  python3 scripts/create_sample_data.py              # Small team (12 employees)
  python3 scripts/create_sample_data.py --large      # Large org (55 employees)
  python3 scripts/create_sample_data.py --historical # Historical quarterly data

Note: This generates Workday export data (salaries, bonus targets, org structure).
      To add sample ratings/tenets, use populate_sample_ratings.py after import.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--large',
        action='store_true',
        help='Create large organization dataset (55 employees, 5 managers) instead of small team'
    )
    parser.add_argument(
        '--historical',
        action='store_true',
        help='Create 6 quarterly historical spreadsheets (2023-Q3 through 2024-Q4)'
    )

    args = parser.parse_args()

    if args.historical:
        create_historical_xlsx()
    else:
        size = 'large' if args.large else 'small'
        create_sample_xlsx(size)


if __name__ == '__main__':
    main()
