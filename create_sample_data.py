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
        ('Paige Duty', 'Staff Engineer', 180000, 'USD', 'IC4', 15, 130, 'Exceptional technical leadership and on-call reliability'),
        ('Lee Latency', 'Senior Software Engineer', 150000, 'USD', 'IC3', 12, 120, 'Outstanding performance optimization work'),
        ('Mona Torr', 'Senior Software Engineer', 145000, 'USD', 'IC3', 12, 110, 'Strong monitoring and observability contributions'),
        ('Robin Rollback', 'Software Engineer', 120000, 'USD', 'IC2', 10, 105, 'Reliable deployment management'),
        ('Kenny Canary', 'Software Engineer', 115000, 'USD', 'IC2', 10, 100, 'Solid canary testing and deployment work'),
        ('Tracey Loggins', 'Senior Software Engineer', 155000, 'USD', 'IC3', 12, 115, 'Excellent logging infrastructure improvements'),
        ('Sue Q. Ell', 'Senior Software Engineer', 148000, 'USD', 'IC3', 12, 125, 'Outstanding database optimization and query performance'),
        ('Jason Blob', 'Software Engineer', 118000, 'USD', 'IC2', 10, 95, 'Good progress on unstructured data handling'),
        ('Al Ert', 'Staff Engineer', 175000, 'USD', 'IC4', 15, 135, 'Critical alerting system improvements, exceptional work'),
        ('Addie Min', 'Senior Software Engineer', 152000, 'USD', 'IC3', 12, 108, 'Solid access management and security work'),
        ('Tim Out', 'Software Engineer', 110000, 'USD', 'IC2', 10, 85, 'Needs improvement in reliability and uptime'),
        ('Barbie Que', 'Senior Software Engineer', 149000, 'USD', 'IC3', 12, 112, 'Strong message queue management'),
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
        'Kay P. Eye': 'Product Management',
        'Agie Enda': 'Engineering - Data',
        'Mai Stone': 'Engineering - Infrastructure'
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
    team_configs = {
        'Engineering - Platform': [
            ('Principal Engineer', 220000, 'IC5', 20, 140, 'Exceptional technical vision and platform architecture'),
            ('Staff Engineer', 180000, 'IC4', 15, 130, 'Outstanding platform reliability improvements'),
            ('Senior Software Engineer', 150000, 'IC3', 12, 115, 'Strong API development work'),
            ('Senior Software Engineer', 145000, 'IC3', 12, 110, 'Solid infrastructure contributions'),
            ('Software Engineer', 120000, 'IC2', 10, 105, 'Good platform integration work'),
            ('Software Engineer', 115000, 'IC2', 10, 100, 'Met expectations on service deployment'),
            ('Software Engineer', 118000, 'IC2', 10, 95, 'Steady progress on platform features'),
            ('Software Engineer', 112000, 'IC2', 10, 90, 'Needs more ownership of features'),
            ('Senior Software Engineer', 148000, 'IC3', 12, 120, 'Excellent platform tooling improvements'),
            ('Senior Software Engineer', 152000, 'IC3', 12, 108, 'Solid mentorship and code quality'),
        ],
        'Engineering - Frontend': [
            ('Staff Engineer', 175000, 'IC4', 15, 125, 'Outstanding UI framework modernization'),
            ('Senior Software Engineer', 155000, 'IC3', 12, 118, 'Strong React component library work'),
            ('Senior Software Engineer', 149000, 'IC3', 12, 112, 'Solid accessibility improvements'),
            ('Software Engineer', 110000, 'IC2', 10, 88, 'Needs improvement in code review participation'),
            ('Software Engineer', 125000, 'IC2', 10, 102, 'Good responsive design work'),
            ('Senior Software Engineer', 147000, 'IC3', 12, 115, 'Excellent state management refactoring'),
            ('Software Engineer', 122000, 'IC2', 10, 98, 'Solid component development'),
            ('Senior Software Engineer', 151000, 'IC3', 12, 110, 'Strong performance optimization'),
            ('Software Engineer', 119000, 'IC2', 10, 92, 'Adequate progress on feature development'),
            ('Software Engineer', 116000, 'IC2', 10, 85, 'Needs more proactive communication'),
        ],
        'Product Management': [
            ('Senior Product Manager', 165000, 'IC4', 15, 128, 'Exceptional product strategy and roadmap'),
            ('Senior Product Manager', 160000, 'IC4', 15, 122, 'Outstanding stakeholder management'),
            ('Product Manager', 130000, 'IC3', 12, 110, 'Strong feature prioritization'),
            ('Product Manager', 125000, 'IC3', 12, 105, 'Good user research and validation'),
            ('Product Manager', 135000, 'IC3', 12, 115, 'Excellent cross-functional collaboration'),
            ('Product Manager', 128000, 'IC3', 12, 100, 'Met goals on product launches'),
            ('Senior Product Manager', 158000, 'IC4', 15, 118, 'Strong data-driven decision making'),
            ('Product Manager', 132000, 'IC3', 12, 108, 'Solid execution on product initiatives'),
            ('Product Manager', 127000, 'IC3', 12, 95, 'Needs improvement in stakeholder alignment'),
            ('Product Manager', 133000, 'IC3', 12, 112, 'Strong customer empathy and insights'),
        ],
        'Engineering - Data': [
            ('Senior Data Engineer', 132911, 'IC3', 12, 'GBP', 105000, 120, 'Outstanding data pipeline architecture'),
            ('Data Engineer', 98734, 'IC2', 10, 'GBP', 78000, 105, 'Good ETL development work'),
            ('Senior Data Engineer', 145000, 'IC3', 12, 115, 'Strong data warehouse optimization'),
            ('Data Engineer', 115000, 'IC2', 10, 100, 'Solid data quality improvements'),
            ('Senior Data Engineer', 148000, 'IC3', 12, 125, 'Excellent ML pipeline infrastructure'),
            ('Data Engineer', 118000, 'IC2', 10, 98, 'Good progress on data ingestion'),
            ('Senior Data Engineer', 142000, 'IC3', 12, 110, 'Strong analytics platform work'),
            ('Data Engineer', 112000, 'IC2', 10, 92, 'Adequate data modeling work'),
            ('Senior Data Engineer', 150000, 'IC3', 12, 118, 'Excellent data governance initiatives'),
            ('Data Engineer', 120000, 'IC2', 10, 95, 'Steady progress on reporting tools'),
        ],
        'Engineering - Infrastructure': [
            ('Staff Infrastructure Engineer', 185000, 'IC4', 15, 135, 'Exceptional infrastructure modernization'),
            ('Senior DevOps Engineer', 155000, 'IC3', 12, 120, 'Outstanding CI/CD pipeline improvements'),
            ('Senior DevOps Engineer', 152000, 'IC3', 12, 112, 'Strong Kubernetes migration work'),
            ('DevOps Engineer', 125000, 'IC2', 10, 103, 'Good infrastructure automation'),
            ('DevOps Engineer', 122000, 'IC2', 10, 98, 'Solid monitoring setup'),
            ('Senior Security Engineer', 160000, 'IC3', 12, 125, 'Excellent security hardening'),
            ('Security Engineer', 135000, 'IC2', 10, 108, 'Strong vulnerability management'),
            ('Senior DevOps Engineer', 148000, 'IC3', 12, 115, 'Strong cloud cost optimization'),
            ('DevOps Engineer', 128000, 'IC2', 10, 100, 'Met expectations on infrastructure work'),
            ('DevOps Engineer', 130000, 'IC2', 10, 95, 'Good disaster recovery planning'),
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
