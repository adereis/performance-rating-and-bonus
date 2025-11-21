#!/usr/bin/env python3
"""
Create sample demo data for the Quarterly Performance Rating System.
This generates fictitious employee data so managers can try the tool out of the box.
"""
import openpyxl
from openpyxl import Workbook
import random

def create_sample_xlsx():
    """Create sample-data.xlsx with fictitious employee data."""

    wb = Workbook()
    sheet = wb.active

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

    # Fictitious data configuration - tech/engineering themed names
    names = [
        'Paige Duty',
        'Lee Latency',
        'Mona Torr',
        'Robin Rollback',
        'Kenny Canary',
        'Tracey Loggins',
        'Sue Q. Ell',
        'Jason Blob',
        'Al Ert',
        'Addie Min',
        'Tim Out',
        'Barbie Que',
        'Terry Byte',
        'Nole Pointer',
        'Marge Conflict',
        'Bridget Branch',
        'Cody Ryder',
        'Cy Ferr',
        'Phil Wall',
        'Lana Wan',
        'Artie Ficial',
        'Ruth Cause',
        'Matt Rick',
        'Cassie Cache',
        'Sue Do',
        'Pat Ch',
        'Devin Null',
        'Justin Time',
        'Annie O\'Maly',
        'Sam Box',
        'Val Idation',
        'Bill Ding',
        'Ty Po',
        'Mike Roservices',
        'Lou Pe',
        'Connie Tainer',
        'Noah Node',
        'Sara Ver',
        'Exa M. Elle',
        'Dee Ploi',
        'Ray D. O\'Button',
        'Cam Elcase',
        'Hashim Map',
        'Ben Chmark',
        'Grace Full',
        'Shel Script',
        'Sal T. Hash',
        'Reba Boot',
        'Stan Dup',
        'Kay Eight'
    ]

    supervisory_orgs = [
        'Engineering - Platform',
        'Engineering - Platform',
        'Engineering - Platform',
        'Engineering - Platform',
        'Engineering - Platform',
        'Engineering - Frontend',
        'Engineering - Frontend',
        'Engineering - Frontend',
        'Engineering - Backend Services',
        'Engineering - Backend Services',
        'Engineering - Backend Services',
        'Engineering - Backend Services',
        'Engineering - Infrastructure',
        'Engineering - Infrastructure',
        'Engineering - Security',
        'Engineering - Security',
        'Product Management',
        'Product Management',
        'Product Management',
        'Engineering - Data',
        'Engineering - Data',
        'Engineering - Mobile',
        'Engineering - Mobile',
        'Engineering - DevOps',
        'Engineering - DevOps',
        'Engineering - QA',
        'Engineering - QA',
        'Engineering - QA',
        'Product Design',
        'Product Design',
        'Engineering - Platform',
        'Engineering - Frontend',
        'Engineering - Backend Services',
        'Engineering - Infrastructure',
        'Engineering - Security',
        'Product Management',
        'Engineering - Data',
        'Engineering - Mobile',
        'Engineering - DevOps',
        'Engineering - QA',
        'Product Design',
        'Engineering - Platform',
        'Engineering - Frontend',
        'Engineering - Backend Services',
        'Engineering - Infrastructure',
        'Product Management',
        'Engineering - Data',
        'Engineering - Mobile',
        'Engineering - DevOps',
        'Engineering - QA'
    ]

    job_profiles = [
        'Senior Software Engineer',
        'Software Engineer',
        'Staff Engineer',
        'Senior Software Engineer',
        'Principal Engineer',
        'Senior Software Engineer',
        'Software Engineer',
        'Senior Software Engineer',
        'Staff Engineer',
        'Senior Software Engineer',
        'Senior Software Engineer',
        'Software Engineer',
        'Senior Software Engineer',
        'Staff Engineer',
        'Senior Software Engineer',
        'Software Engineer',
        'Senior Product Manager',
        'Product Manager',
        'Senior Product Manager',
        'Senior Data Engineer',
        'Data Engineer',
        'Senior Software Engineer',
        'Software Engineer',
        'Senior DevOps Engineer',
        'DevOps Engineer',
        'Senior QA Engineer',
        'QA Engineer',
        'QA Engineer',
        'Senior Product Designer',
        'Product Designer',
        'Software Engineer',
        'Software Engineer',
        'Senior Software Engineer',
        'Senior Software Engineer',
        'Security Engineer',
        'Product Manager',
        'Data Analyst',
        'Mobile Engineer',
        'DevOps Engineer',
        'QA Engineer',
        'Product Designer',
        'Senior Software Engineer',
        'Senior Software Engineer',
        'Software Engineer',
        'Infrastructure Engineer',
        'Senior Product Manager',
        'Senior Data Engineer',
        'Senior Mobile Engineer',
        'Senior DevOps Engineer',
        'Senior QA Engineer'
    ]

    # Salary ranges by job profile (in USD)
    salary_ranges = {
        'Software Engineer': (90000, 120000),
        'Senior Software Engineer': (130000, 170000),
        'Staff Engineer': (170000, 220000),
        'Principal Engineer': (220000, 280000),
        'Product Manager': (110000, 140000),
        'Senior Product Manager': (150000, 190000),
        'Data Engineer': (95000, 125000),
        'Senior Data Engineer': (135000, 175000),
        'Mobile Engineer': (95000, 125000),
        'Senior Mobile Engineer': (135000, 175000),
        'DevOps Engineer': (100000, 130000),
        'Senior DevOps Engineer': (140000, 180000),
        'QA Engineer': (85000, 110000),
        'Senior QA Engineer': (115000, 145000),
        'Product Designer': (95000, 125000),
        'Senior Product Designer': (130000, 165000),
        'Data Analyst': (80000, 105000),
        'Security Engineer': (120000, 160000),
        'Infrastructure Engineer': (115000, 150000)
    }

    # Bonus target percentages by level
    bonus_targets = {
        'Software Engineer': 10,
        'Senior Software Engineer': 12,
        'Staff Engineer': 15,
        'Principal Engineer': 20,
        'Product Manager': 12,
        'Senior Product Manager': 15,
        'Data Engineer': 10,
        'Senior Data Engineer': 12,
        'Mobile Engineer': 10,
        'Senior Mobile Engineer': 12,
        'DevOps Engineer': 10,
        'Senior DevOps Engineer': 12,
        'QA Engineer': 8,
        'Senior QA Engineer': 10,
        'Product Designer': 10,
        'Senior Product Designer': 12,
        'Data Analyst': 8,
        'Security Engineer': 12,
        'Infrastructure Engineer': 12
    }

    # Currency data for non-US employees (25% of team)
    currencies = ['USD', 'GBP', 'EUR', 'CAD', 'INR']
    exchange_rates = {
        'USD': 1.0,
        'GBP': 0.79,
        'EUR': 0.92,
        'CAD': 1.35,
        'INR': 82.5
    }

    # Generate 50 employees
    for i in range(50):
        associate = names[i]
        supervisory_org = supervisory_orgs[i]
        job_profile = job_profiles[i]
        photo = ''
        errors = ''
        associate_id = f'EMP{1000 + i}'

        # Determine currency (75% USD, rest distributed)
        if i < 38:  # First 38 are US-based
            currency = 'USD'
        else:
            currency = random.choice(['GBP', 'EUR', 'CAD', 'INR'])

        # Generate salary
        salary_range = salary_ranges.get(job_profile, (100000, 150000))
        base_pay_usd = random.randint(salary_range[0], salary_range[1])
        base_pay_usd = round(base_pay_usd / 1000) * 1000  # Round to nearest 1000

        # Convert to local currency if needed
        exchange_rate = exchange_rates[currency]
        base_pay_local = base_pay_usd * exchange_rate

        # Bonus calculations
        bonus_target_pct = bonus_targets.get(job_profile, 10)
        bonus_target_usd = base_pay_usd * (bonus_target_pct / 100)
        bonus_target_local = bonus_target_usd * exchange_rate

        # For non-USD, we have both columns
        if currency == 'USD':
            bonus_target_local_col = bonus_target_usd
            bonus_target_usd_col = None  # USD employees don't have the USD column
            base_pay_local_col = base_pay_usd
            base_pay_usd_col = None
        else:
            bonus_target_local_col = bonus_target_local
            bonus_target_usd_col = bonus_target_usd
            base_pay_local_col = base_pay_local
            base_pay_usd_col = base_pay_usd

        # Grade (internal, not shown to managers but in data)
        grade_map = {
            'Software Engineer': 'IC2',
            'Senior Software Engineer': 'IC3',
            'Staff Engineer': 'IC4',
            'Principal Engineer': 'IC5',
            'Product Manager': 'IC3',
            'Senior Product Manager': 'IC4',
            'Data Engineer': 'IC2',
            'Senior Data Engineer': 'IC3',
            'Mobile Engineer': 'IC2',
            'Senior Mobile Engineer': 'IC3',
            'DevOps Engineer': 'IC2',
            'Senior DevOps Engineer': 'IC3',
            'QA Engineer': 'IC2',
            'Senior QA Engineer': 'IC3',
            'Product Designer': 'IC2',
            'Senior Product Designer': 'IC3',
            'Data Analyst': 'IC2',
            'Security Engineer': 'IC3',
            'Infrastructure Engineer': 'IC3'
        }
        grade = grade_map.get(job_profile, 'IC2')

        # Last bonus allocation (previous quarter - some value around 80-120%)
        last_bonus_pct = random.choice([None, None, None, 85, 90, 95, 100, 105, 110, 115])

        # Empty fields for now
        proposed_bonus = None
        proposed_bonus_usd = None
        proposed_pct = None
        notes = ''
        zero_bonus = ''

        row = [
            associate,
            supervisory_org,
            job_profile,
            photo,
            errors,
            associate_id,
            base_pay_local_col,
            base_pay_usd_col,
            currency,
            grade,
            bonus_target_pct,
            last_bonus_pct,
            bonus_target_local_col,
            bonus_target_usd_col,
            proposed_bonus,
            proposed_bonus_usd,
            proposed_pct,
            notes,
            zero_bonus
        ]

        sheet.append(row)

    # Save the workbook
    wb.save('sample-data.xlsx')
    print(f"✓ Created sample-data.xlsx with 50 fictitious employees")
    print("  - 38 US-based employees (USD)")
    print("  - 12 international employees (GBP, EUR, CAD, INR)")
    print("  - Mix of job levels and departments")
    print("  - Ready to import with: python convert_xlsx.py sample-data.xlsx")


if __name__ == '__main__':
    create_sample_xlsx()
