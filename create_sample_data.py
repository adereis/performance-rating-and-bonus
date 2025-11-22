#!/usr/bin/env python3
"""
Create sample demo data for the Quarterly Performance Rating System.
This generates fictitious employee data so managers can try the tool out of the box.

Usage:
    python3 create_sample_data.py              # Creates small team (12 employees, 1 manager)
    python3 create_sample_data.py --large      # Creates large org (50 employees, 5 managers)
"""
import openpyxl
from openpyxl import Workbook
import random
import sys


def create_headers(sheet):
    """Add standard Workday export headers."""
    # Row 1: Empty (matches Workday export format)
    sheet.append([])

    # Row 2: Headers (matches Workday export structure)
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
    Includes realistic performance ratings for bonus calculation.
    """
    manager = "Della Gate - Engineering"

    # (name, job, salary, currency, grade, bonus_pct, rating, justification)
    employees = [
        ('Paige Duty', 'Staff SRE', 180000, 'USD', 'IC4', 15, 130, 'Exceptional technical leadership and on-call reliability'),
        ('Lee Latency', 'Senior Software Developer', 150000, 'USD', 'IC3', 12, 120, 'Outstanding performance optimization work'),
        ('Mona Torr', 'Senior SRE', 145000, 'USD', 'IC3', 12, 110, 'Strong monitoring and observability contributions'),
        ('Robin Rollback', 'Software Developer', 120000, 'USD', 'IC2', 10, 105, 'Reliable deployment management'),
        ('Kenny Canary', 'Software Developer', 115000, 'USD', 'IC2', 10, 100, 'Solid canary testing and deployment work'),
        ('Tracey Loggins', 'Senior SRE', 155000, 'USD', 'IC3', 12, 115, 'Excellent logging infrastructure improvements'),
        ('Sue Q. Ell', 'Senior Software Developer', 148000, 'USD', 'IC3', 12, 125, 'Outstanding database optimization and query performance'),
        ('Jason Blob', 'Software Developer', 118000, 'USD', 'IC2', 10, 95, 'Good progress on unstructured data handling'),
        ('Al Ert', 'Staff SRE', 175000, 'USD', 'IC4', 15, 135, 'Critical alerting system improvements, exceptional work'),
        ('Addie Min', 'Senior Software Developer', 152000, 'USD', 'IC3', 12, 108, 'Solid access management and security work'),
        ('Tim Out', 'Software Developer', 110000, 'USD', 'IC2', 10, 85, 'Needs improvement in reliability and uptime'),
        ('Barbie Que', 'Senior SRE', 149000, 'USD', 'IC3', 12, 112, 'Strong message queue management'),
    ]

    result = []
    for i, (name, job, salary, currency, grade, bonus_pct, rating, justification) in enumerate(employees):
        result.append({
            'associate': name,
            'supervisory_organization': manager,
            'job_profile': job,
            'salary': salary,
            'currency': currency,
            'grade': grade,
            'bonus_pct': bonus_pct,
            'rating': rating,
            'justification': justification,
            'associate_id': f'EMP{1000 + i}'
        })

    return result


def get_large_org_data():
    """
    Large org: 50 employees across 5 managers.
    Tests multi-manager/multi-org scenario with international employees.
    """
    # Manager names from Gemini 3
    managers = {
        'Della Gate': 'Engineering - Platform',
        'Rhoda Map': 'Engineering - Frontend',
        'Kay P. Eye': 'Engineering - Backend Services',
        'Agie Enda': 'Engineering - Infrastructure',
        'Mai Stone': 'Engineering - Reliability'
    }

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

    # Job profiles per team with performance ratings
    # Format: (job, salary, grade, bonus_pct, rating, justification) or
    #         (job, salary_usd, grade, bonus_pct, currency, salary_local, rating, justification) for international
    # NOTE: In large org, Engineering Managers are included because a higher-level manager
    #       (e.g., Director) would be rating them along with their teams.
    team_configs = {
        'Engineering - Platform': [
            ('Principal Software Developer', 220000, 'IC5', 20, 140, 'Exceptional technical vision and platform architecture'),
            ('Engineering Manager', 190000, 'M3', 18, 135, 'Outstanding team leadership and delivery'),
            ('Staff Software Developer', 180000, 'IC4', 15, 130, 'Outstanding platform reliability improvements'),
            ('Senior Software Developer', 150000, 'IC3', 12, 115, 'Strong API development work'),
            ('Senior Software Developer', 145000, 'IC3', 12, 110, 'Solid infrastructure contributions'),
            ('Software Developer', 120000, 'IC2', 10, 105, 'Good platform integration work'),
            ('Software Developer', 115000, 'IC2', 10, 100, 'Met expectations on service deployment'),
            ('Software Developer', 118000, 'IC2', 10, 95, 'Steady progress on platform features'),
            ('Software Developer', 112000, 'IC2', 10, 90, 'Needs more ownership of features'),
            ('Senior Software Developer', 152000, 'IC3', 12, 108, 'Solid mentorship and code quality'),
        ],
        'Engineering - Frontend': [
            ('Staff Software Developer', 175000, 'IC4', 15, 125, 'Outstanding UI framework modernization'),
            ('Engineering Manager', 185000, 'M3', 18, 128, 'Strong team growth and technical direction'),
            ('Senior Software Developer', 155000, 'IC3', 12, 118, 'Strong React component library work'),
            ('Senior Software Developer', 149000, 'IC3', 12, 112, 'Solid accessibility improvements'),
            ('Software Developer', 110000, 'IC2', 10, 88, 'Needs improvement in code review participation'),
            ('Software Developer', 125000, 'IC2', 10, 102, 'Good responsive design work'),
            ('Senior Software Developer', 147000, 'IC3', 12, 115, 'Excellent state management refactoring'),
            ('Software Developer', 122000, 'IC2', 10, 98, 'Solid component development'),
            ('Software Developer', 119000, 'IC2', 10, 92, 'Adequate progress on feature development'),
            ('Software Developer', 116000, 'IC2', 10, 85, 'Needs more proactive communication'),
        ],
        'Engineering - Backend Services': [
            ('Principal Software Developer', 215000, 'IC5', 20, 138, 'Exceptional distributed systems architecture'),
            ('Staff Software Developer', 182000, 'IC4', 15, 130, 'Outstanding microservices design'),
            ('Engineering Manager', 188000, 'M3', 18, 132, 'Excellent cross-team coordination and delivery'),
            ('Senior Software Developer', 158000, 'IC3', 12, 120, 'Strong API design and implementation'),
            ('Senior Software Developer', 152000, 'IC3', 12, 112, 'Solid service reliability work'),
            ('Software Developer', 128000, 'IC2', 10, 105, 'Good backend feature development'),
            ('Software Developer', 122000, 'IC2', 10, 100, 'Met expectations on service development'),
            ('Software Developer', 118000, 'IC2', 10, 95, 'Steady progress on REST API work'),
            ('Senior Software Developer', 155000, 'IC3', 12, 115, 'Strong database optimization'),
            ('Software Developer', 125000, 'IC2', 10, 92, 'Adequate progress on microservices'),
        ],
        'Engineering - Infrastructure': [
            ('Senior SRE', 132911, 'IC3', 12, 'GBP', 105000, 120, 'Outstanding infrastructure automation'),
            ('SRE', 98734, 'IC2', 10, 'GBP', 78000, 105, 'Good deployment pipeline work'),
            ('Staff SRE', 185000, 'IC4', 15, 135, 'Exceptional infrastructure modernization'),
            ('Engineering Manager', 192000, 'M3', 18, 130, 'Strong infrastructure team leadership'),
            ('Senior SRE', 155000, 'IC3', 12, 120, 'Outstanding CI/CD pipeline improvements'),
            ('Senior SRE', 152000, 'IC3', 12, 112, 'Strong Kubernetes migration work'),
            ('SRE', 125000, 'IC2', 10, 103, 'Good infrastructure automation'),
            ('SRE', 122000, 'IC2', 10, 98, 'Solid monitoring setup'),
            ('Senior SRE', 148000, 'IC3', 12, 115, 'Strong cloud cost optimization'),
            ('SRE', 130000, 'IC2', 10, 95, 'Good disaster recovery planning'),
        ],
        'Engineering - Reliability': [
            ('Staff SRE', 188000, 'IC4', 15, 133, 'Outstanding SLO/SLI framework design'),
            ('Engineering Manager', 195000, 'M3', 18, 128, 'Excellent reliability culture building'),
            ('Senior SRE', 160000, 'IC3', 12, 125, 'Exceptional on-call process improvements'),
            ('Senior SRE', 156000, 'IC3', 12, 118, 'Strong incident response leadership'),
            ('Senior SRE', 153000, 'IC3', 12, 110, 'Solid observability improvements'),
            ('SRE', 128000, 'IC2', 10, 108, 'Strong monitoring and alerting work'),
            ('SRE', 124000, 'IC2', 10, 102, 'Good chaos engineering initiatives'),
            ('SRE', 120000, 'IC2', 10, 98, 'Solid capacity planning work'),
            ('SRE', 118000, 'IC2', 10, 93, 'Adequate progress on reliability metrics'),
            ('SRE', 115000, 'IC2', 10, 90, 'Needs more proactive incident prevention'),
        ],
    }

    result = []
    name_idx = 0

    for manager_name, teams in managers.items():
        org = teams
        configs = team_configs[org]

        for config in configs:
            if len(config) == 8:  # International employee
                job, salary_usd, grade, bonus_pct, currency, salary_local, rating, justification = config
            else:
                job, salary_usd, grade, bonus_pct, rating, justification = config
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
                'rating': rating,
                'justification': justification,
                'associate_id': f'EMP{1000 + name_idx}'
            })

            name_idx += 1

    return result


def write_employee_data(sheet, employees):
    """Write employee data to worksheet."""
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
            ''   # Zero bonus allocated
        ]

        sheet.append(row)


def create_sample_xlsx(size='small'):
    """
    Create sample-data.xlsx with fictitious employee data.

    Args:
        size: 'small' for 12 employees (1 manager), 'large' for 50 employees (5 managers)
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
        description = "50 employees across 5 managers"

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
    print(f"  - Ready to import with: python3 convert_xlsx.py {filename}")


if __name__ == '__main__':
    size = 'large' if '--large' in sys.argv else 'small'
    create_sample_xlsx(size)
