#!/usr/bin/env python3
"""
Create sample demo data for the Quarterly Performance Rating System.
This generates fictitious Workday employee data (no ratings/tenets).

Usage:
    python3 create_sample_data.py          # Creates small team (12 employees, 1 manager)
    python3 create_sample_data.py --large  # Creates large org (55 employees: 5 managers + 50 ICs)

Note: This generates ONLY Workday export data (salaries, bonus targets, org structure).
      To add sample ratings/tenets, use populate_sample_ratings.py after import.
"""
import openpyxl
from openpyxl import Workbook
import random
import sys


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
    # Bonus percentages are QUARTERLY (annual target / 4)
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
    # NOTE: Bonus percentages are QUARTERLY (annual / 4): IC2=2.5%, IC3=3%, IC4=3.75%, IC5=5%, M3=4.5%
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
            'bonus_pct': 4.5,  # Quarterly bonus target for M3 managers
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

        # Last bonus allocation (previous quarter)
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


if __name__ == '__main__':
    size = 'large' if '--large' in sys.argv else 'small'
    create_sample_xlsx(size)
