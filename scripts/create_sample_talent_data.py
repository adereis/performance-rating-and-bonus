#!/usr/bin/env python3
"""
Create sample talent calibration data for the Performance Rating System.
Generates fictitious Workday talent export XLSX files.

Usage:
    python3 create_sample_talent_data.py              # Creates small team (12 employees)
    python3 create_sample_talent_data.py --large      # Creates large org (55 employees)

Output:
    sample-data-talent-small.xlsx
    sample-data-talent-large.xlsx

Distribution guidelines (from Spec §11.3):
    Performance What/How Matrix:
        Surpasses/Surpasses: 10%, Surpasses/Meets: 15%, Surpasses/MeetsSome: 2%
        Meets/Surpasses: 15%, Meets/Meets: 40%, Meets/MeetsSome: 10%, Meets/DoesNotMeet: 2%
        MeetsSome/Surpasses: 2%, MeetsSome/Meets: 3%, MeetsSome/MeetsSome: 1%
    Movement Readiness: Continue 75%, Promotion 20%, Lateral 5%
    Future Talent: Yes 15-20%, No 80-85%
"""
import openpyxl
from openpyxl import Workbook
import random
import sys
import os
import argparse
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import derive_overall_performance, derive_future_talent as _derive_future_talent


def derive_future_talent(growth: str, change: str) -> str:
    """Wrapper returning 'Yes'/'No' string for XLSX output."""
    return 'Yes' if _derive_future_talent(growth, change) else 'No'


# Enum values from Spec §3 (must match Workday export format exactly)
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

# Spec §3.3 - Agility options (no "Not Yet" in spec)
AGILITY_OPTIONS = [
    'Always/Most of the Time',
    'Sometimes'
]

# Spec §3.4 - Movement Readiness options
MOVEMENT_READINESS_OPTIONS = [
    'Continue growing in current role',
    'Ready Now to be promoted in current role',
    'Ready for lateral move'
]


def create_talent_headers(sheet):
    """Add Workday talent export headers."""
    # Row 1-5: Report metadata (skip rows, mimicking Workday format)
    for _ in range(5):
        sheet.append([])

    # Row 6: Headers (matching Workday talent calibration export)
    headers = [
        'Associate ID',
        'Worker',
        'Supervisory Organization',
        'Job Profile',
        'Management Level',
        'Job Category',
        'Hire Date',
        'Length of Service - Worker',
        'Time in Job Profile',
        'Region - Location Based',
        'Country',
        'Performance: What',
        'Performance: How',
        'Overall Performance Rating',
        'Last Talent Assessment Cycle: Overall Performance Rating',
        'Future Talent: Growth Agility',
        'Future Talent: Change Agility',
        'Identified as Future Talent?',
        'Last Talent Assessment Cycle: Identified as Future Talent?',
        'Movement Readiness',
        'Last Talent Assessment Cycle: Movement Readiness',
        'Proposed Talent Actions',
        'Promotions: Proposed Job Profile & Code',
        'Promotions: Business Need',
        'Promotions: Expanded Role Scope',
        'Promotions: Associate Readiness',
        'Calibration Status'
    ]

    sheet.append(headers)


def generate_perf_what_how():
    """
    Generate Performance What/How based on distribution from Spec §11.3.
    Returns (what, how) tuple.
    """
    # Distribution matrix (What, How, probability)
    distribution = [
        ('Surpasses Expectations', 'Surpasses Expectations', 0.10),
        ('Surpasses Expectations', 'Meets Expectations', 0.15),
        ('Surpasses Expectations', 'Meets Some Expectations', 0.02),
        ('Meets Expectations', 'Surpasses Expectations', 0.15),
        ('Meets Expectations', 'Meets Expectations', 0.40),
        ('Meets Expectations', 'Meets Some Expectations', 0.10),
        ('Meets Expectations', 'Does Not Meet Expectations', 0.02),
        ('Meets Some Expectations', 'Surpasses Expectations', 0.02),
        ('Meets Some Expectations', 'Meets Expectations', 0.03),
        ('Meets Some Expectations', 'Meets Some Expectations', 0.01),
    ]

    r = random.random()
    cumulative = 0
    for what, how, prob in distribution:
        cumulative += prob
        if r < cumulative:
            return what, how

    # Fallback (should rarely happen due to rounding)
    return 'Meets Expectations', 'Meets Expectations'


def generate_movement_readiness():
    """Generate movement readiness based on Spec §11.3 distribution."""
    r = random.random()
    if r < 0.75:
        return 'Continue growing in current role'
    elif r < 0.95:
        return 'Ready Now to be promoted in current role'
    else:
        return 'Ready for lateral move'


def generate_agility():
    """
    Generate growth/change agility ratings.

    Target ~40% 'Always/Most of the Time' per field to achieve
    ~16% Future Talent (both fields must be 'Always' per Spec §4.2).
    """
    r = random.random()
    if r < 0.40:
        return 'Always/Most of the Time'
    else:
        return 'Sometimes'


def generate_hire_date():
    """Generate a random hire date 1-10 years ago."""
    days_ago = random.randint(365, 365 * 10)
    hire_date = datetime.now() - timedelta(days=days_ago)
    return hire_date.strftime('%Y-%m-%d')


def generate_length_of_service(hire_date_str):
    """Generate length of service string based on hire date."""
    hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d')
    today = datetime.now()
    delta = today - hire_date
    years = delta.days // 365
    months = (delta.days % 365) // 30
    if years > 0:
        return f"{years} year{'s' if years > 1 else ''}, {months} month{'s' if months != 1 else ''}"
    else:
        return f"{months} month{'s' if months != 1 else ''}"


def generate_time_in_job():
    """Generate time in job profile string."""
    years = random.randint(0, 5)
    months = random.randint(0, 11)
    if years > 0:
        return f"{years} year{'s' if years > 1 else ''}, {months} month{'s' if months != 1 else ''}"
    else:
        return f"{months} month{'s' if months != 1 else ''}"


def get_small_team_talent_data():
    """
    Small team: 12 employees matching create_sample_data.py small team.
    Returns talent calibration data for each employee.
    """
    manager = "Supervisory Organization (Della Gate)"

    employees = [
        ('Paige Duty', 'Staff SRE', 'IC4', 'Manager'),
        ('Lee Latency', 'Senior Software Developer', 'IC3', 'Senior Individual Contributor'),
        ('Mona Torr', 'Senior SRE', 'IC3', 'Senior Individual Contributor'),
        ('Robin Rollback', 'Software Developer', 'IC2', 'Individual Contributor'),
        ('Kenny Canary', 'Software Developer', 'IC2', 'Individual Contributor'),
        ('Tracey Loggins', 'Senior SRE', 'IC3', 'Senior Individual Contributor'),
        ('Sue Q. Ell', 'Senior Software Developer', 'IC3', 'Senior Individual Contributor'),
        ('Jason Blob', 'Software Developer', 'IC2', 'Individual Contributor'),
        ('Al Ert', 'Staff SRE', 'IC4', 'Manager'),
        ('Addie Min', 'Senior Software Developer', 'IC3', 'Senior Individual Contributor'),
        ('Tim Out', 'Software Developer', 'IC2', 'Individual Contributor'),
        ('Barbie Que', 'Senior SRE', 'IC3', 'Senior Individual Contributor'),
    ]

    result = []
    for i, (name, job, grade, mgmt_level) in enumerate(employees):
        perf_what, perf_how = generate_perf_what_how()
        growth = generate_agility()
        change = generate_agility()
        movement = generate_movement_readiness()
        hire_date = generate_hire_date()

        result.append({
            'associate_id': f'EMP{1000 + i}',
            'associate': name,
            'supervisory_organization': manager,
            'job_profile': job,
            'management_level': mgmt_level,
            'job_category': 'Engineering',
            'hire_date': hire_date,
            'length_of_service': generate_length_of_service(hire_date),
            'time_in_job_profile': generate_time_in_job(),
            'region': 'Americas',
            'country': 'United States',
            'perf_what': perf_what,
            'perf_how': perf_how,
            'growth_agility': growth,
            'change_agility': change,
            'movement_readiness': movement,
        })

    return result


def get_large_org_talent_data():
    """
    Large org: 55 employees across 5 managers, matching create_sample_data.py large org.
    Uses the same pun names, IDs, and structure for consistency.

    ID scheme (must match create_sample_data.py exactly):
    - Managers: MGR100-MGR104 (report to Director)
    - ICs: EMP1000-EMP1049 (report to their manager)
    """
    # Director org (managers report here)
    director_org = 'Supervisory Organization (Director)'

    # Manager names and their orgs matching create_sample_data.py
    managers = [
        ('Della Gate', 'Supervisory Organization (Della Gate)'),
        ('Rhoda Map', 'Supervisory Organization (Rhoda Map)'),
        ('Kay P. Eye', 'Supervisory Organization (Kay P. Eye)'),
        ('Agie Enda', 'Supervisory Organization (Agie Enda)'),
        ('Mai Stone', 'Supervisory Organization (Mai Stone)'),
    ]

    # Tech-themed employee names (matching create_sample_data.py exactly)
    names = [
        'Paige Duty', 'Lee Latency', 'Mona Torr', 'Robin Rollback',
        'Kenny Canary', 'Tracey Loggins', 'Sue Q. Ell', 'Jason Blob',
        'Al Ert', 'Addie Min', 'Tim Out', 'Barbie Que',
        'Terry Byte', 'Nole Pointer', 'Marge Conflict', 'Bridget Branch',
        'Cody Ryder', 'Cy Ferr', 'Phil Wall', 'Lana Wan',
        'Artie Ficial', 'Ruth Cause', 'Matt Rick', 'Cassie Cache',
        'Sue Do', 'Pat Ch', 'Devin Null', 'Justin Time',
        "Annie O'Maly", 'Sam Box', 'Val Idation', 'Bill Ding',
        'Ty Po', 'Mike Roservices', 'Lou Pe', 'Connie Tainer',
        'Noah Node', 'Sara Ver', 'Exa M. Elle', 'Dee Ploi',
        "Ray D. O'Button", 'Cam Elcase', 'Hashim Map', 'Ben Chmark',
        'Grace Full', 'Shel Script', 'Sal T. Hash', 'Reba Boot',
        'Stan Dup', 'Kay Eight'
    ]

    # Job profiles for each manager's team (matching create_sample_data.py structure)
    team_jobs = {
        'Della Gate': [
            ('Principal Software Developer', 'IC5', 'Senior Individual Contributor'),
            ('Staff Software Developer', 'IC4', 'Senior Individual Contributor'),
            ('Staff Software Developer', 'IC4', 'Senior Individual Contributor'),
            ('Senior Software Developer', 'IC3', 'Senior Individual Contributor'),
            ('Senior Software Developer', 'IC3', 'Senior Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
            ('Senior Software Developer', 'IC3', 'Senior Individual Contributor'),
        ],
        'Rhoda Map': [
            ('Staff Software Developer', 'IC4', 'Senior Individual Contributor'),
            ('Staff Software Developer', 'IC4', 'Senior Individual Contributor'),
            ('Senior Software Developer', 'IC3', 'Senior Individual Contributor'),
            ('Senior Software Developer', 'IC3', 'Senior Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
            ('Senior Software Developer', 'IC3', 'Senior Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
        ],
        'Kay P. Eye': [
            ('Principal Software Developer', 'IC5', 'Senior Individual Contributor'),
            ('Staff Software Developer', 'IC4', 'Senior Individual Contributor'),
            ('Staff Software Developer', 'IC4', 'Senior Individual Contributor'),
            ('Senior Software Developer', 'IC3', 'Senior Individual Contributor'),
            ('Senior Software Developer', 'IC3', 'Senior Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
            ('Senior Software Developer', 'IC3', 'Senior Individual Contributor'),
            ('Software Developer', 'IC2', 'Individual Contributor'),
        ],
        'Agie Enda': [
            ('Senior SRE', 'IC3', 'Senior Individual Contributor'),
            ('SRE', 'IC2', 'Individual Contributor'),
            ('Staff SRE', 'IC4', 'Senior Individual Contributor'),
            ('Staff SRE', 'IC4', 'Senior Individual Contributor'),
            ('Senior SRE', 'IC3', 'Senior Individual Contributor'),
            ('Senior SRE', 'IC3', 'Senior Individual Contributor'),
            ('SRE', 'IC2', 'Individual Contributor'),
            ('SRE', 'IC2', 'Individual Contributor'),
            ('Senior SRE', 'IC3', 'Senior Individual Contributor'),
            ('SRE', 'IC2', 'Individual Contributor'),
        ],
        'Mai Stone': [
            ('Staff SRE', 'IC4', 'Senior Individual Contributor'),
            ('Staff SRE', 'IC4', 'Senior Individual Contributor'),
            ('Senior SRE', 'IC3', 'Senior Individual Contributor'),
            ('Senior SRE', 'IC3', 'Senior Individual Contributor'),
            ('Senior SRE', 'IC3', 'Senior Individual Contributor'),
            ('SRE', 'IC2', 'Individual Contributor'),
            ('SRE', 'IC2', 'Individual Contributor'),
            ('SRE', 'IC2', 'Individual Contributor'),
            ('SRE', 'IC2', 'Individual Contributor'),
            ('SRE', 'IC2', 'Individual Contributor'),
        ],
    }

    # Region/country mapping (Agie Enda's first two are UK-based per create_sample_data.py)
    region_countries = {
        'Americas': ['United States', 'Canada'],
        'EMEA': ['United Kingdom', 'Germany'],
        'APAC': ['Australia', 'Japan']
    }

    result = []

    # First, add the 5 managers (MGR100-MGR104) reporting to Director
    # This matches create_sample_data.py structure exactly
    for mgr_idx, (manager_name, org) in enumerate(managers):
        perf_what, perf_how = generate_perf_what_how()
        growth = generate_agility()
        change = generate_agility()
        movement = generate_movement_readiness()
        hire_date = generate_hire_date()

        result.append({
            'associate_id': f'MGR{100 + mgr_idx}',
            'associate': manager_name,
            'supervisory_organization': director_org,  # Managers report to Director
            'job_profile': 'Engineering Manager',
            'management_level': 'Manager',
            'job_category': 'Engineering',
            'hire_date': hire_date,
            'length_of_service': generate_length_of_service(hire_date),
            'time_in_job_profile': generate_time_in_job(),
            'region': 'Americas',
            'country': 'United States',
            'perf_what': perf_what,
            'perf_how': perf_how,
            'growth_agility': growth,
            'change_agility': change,
            'movement_readiness': movement,
        })

    # Then add all 50 ICs (EMP1000-EMP1049) reporting to their managers
    # Iterate through managers' teams in same order as create_sample_data.py
    name_idx = 0
    emp_id = 1000

    for manager_name, org in managers:
        for job, grade, mgmt_level in team_jobs[manager_name]:
            name = names[name_idx]

            perf_what, perf_how = generate_perf_what_how()
            growth = generate_agility()
            change = generate_agility()
            movement = generate_movement_readiness()
            hire_date = generate_hire_date()

            # Agie Enda's first two employees (indices 30-31) are UK-based
            # per create_sample_data.py
            if manager_name == 'Agie Enda' and name_idx < 32 and name_idx >= 30:
                region = 'EMEA'
                country = 'United Kingdom'
            else:
                region = random.choice(['Americas', 'EMEA', 'APAC'])
                country = random.choice(region_countries[region])

            result.append({
                'associate_id': f'EMP{emp_id}',
                'associate': name,
                'supervisory_organization': org,  # ICs report to their manager's org
                'job_profile': job,
                'management_level': mgmt_level,
                'job_category': 'Engineering',
                'hire_date': hire_date,
                'length_of_service': generate_length_of_service(hire_date),
                'time_in_job_profile': generate_time_in_job(),
                'region': region,
                'country': country,
                'perf_what': perf_what,
                'perf_how': perf_how,
                'growth_agility': growth,
                'change_agility': change,
                'movement_readiness': movement,
            })

            name_idx += 1
            emp_id += 1

    return result


def write_talent_xlsx(employees, filename):
    """Write talent calibration data to XLSX file."""
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Talent Calibration"

    create_talent_headers(sheet)

    for emp in employees:
        overall_perf = derive_overall_performance(emp['perf_what'], emp['perf_how'])
        future_talent = derive_future_talent(emp['growth_agility'], emp['change_agility'])

        # Generate some random "last cycle" data (previous year)
        last_perf_what, last_perf_how = generate_perf_what_how()
        last_overall = derive_overall_performance(last_perf_what, last_perf_how)
        last_future_talent = derive_future_talent(generate_agility(), generate_agility())
        last_movement = generate_movement_readiness()

        row = [
            emp['associate_id'],
            emp['associate'],
            emp['supervisory_organization'],
            emp['job_profile'],
            emp['management_level'],
            emp['job_category'],
            emp['hire_date'],
            emp['length_of_service'],
            emp['time_in_job_profile'],
            emp['region'],
            emp['country'],
            emp['perf_what'],
            emp['perf_how'],
            overall_perf,
            last_overall,  # Last cycle overall
            emp['growth_agility'],
            emp['change_agility'],
            future_talent,
            last_future_talent,  # Last cycle future talent
            emp['movement_readiness'],
            last_movement,  # Last cycle movement
            '',  # Proposed Talent Actions (empty for sample)
            '',  # Promo job profile
            '',  # Promo business need
            '',  # Promo role scope
            '',  # Promo readiness
            'In Progress',  # Calibration status
        ]
        sheet.append(row)

    wb.save(filename)
    print(f"Created: {filename} ({len(employees)} employees)")


def main():
    parser = argparse.ArgumentParser(
        description='Create sample talent calibration data for the Performance Rating System.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--large', action='store_true',
                        help='Create large org (55 employees) instead of small team')

    args = parser.parse_args()

    if args.large:
        employees = get_large_org_talent_data()
        filename = 'sample-data-talent-large.xlsx'
    else:
        employees = get_small_team_talent_data()
        filename = 'sample-data-talent-small.xlsx'

    write_talent_xlsx(employees, filename)

    # Print distribution stats
    perf_counts = {}
    movement_counts = {}
    future_talent_count = 0

    for emp in employees:
        overall = derive_overall_performance(emp['perf_what'], emp['perf_how'])
        perf_counts[overall] = perf_counts.get(overall, 0) + 1
        movement_counts[emp['movement_readiness']] = movement_counts.get(emp['movement_readiness'], 0) + 1
        if derive_future_talent(emp['growth_agility'], emp['change_agility']) == 'Yes':
            future_talent_count += 1

    print(f"\nDistribution stats:")
    print(f"  Overall Performance:")
    for perf, count in sorted(perf_counts.items()):
        print(f"    {perf}: {count} ({100*count/len(employees):.1f}%)")
    print(f"  Movement Readiness:")
    for movement, count in sorted(movement_counts.items()):
        print(f"    {movement}: {count} ({100*count/len(employees):.1f}%)")
    print(f"  Future Talent: {future_talent_count} ({100*future_talent_count/len(employees):.1f}%)")


if __name__ == '__main__':
    main()
