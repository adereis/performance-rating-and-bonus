#!/usr/bin/env python3
"""
Regenerate sample XLSX files with the new Workday extended format.

This script updates the sample historical files to use the new format with:
- Row 1: Report title with period
- Row 4: Budget data (pool, currency)
- Row 9: Column headers
- Row 10+: Employee data

Usage:
    python3 scripts/regenerate_sample_xlsx.py
"""
import os
import sys
from datetime import datetime
from openpyxl import Workbook

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_workday_xlsx(employees_data, period_name, total_pool, manager_currency='USD'):
    """
    Create an XLSX file matching the Workday extended export format.

    Args:
        employees_data: List of dicts with employee data
        period_name: Period identifier (e.g., "2024-Q3")
        total_pool: Total bonus pool amount
        manager_currency: Manager's currency code

    Returns:
        Workbook object
    """
    wb = Workbook()
    ws = wb.active

    # Row 1: Report title with period
    ws.append([f'Associate Awards:: Compensation Review: Bonus - {period_name}'])

    # Row 2: Subtitle
    ws.append(['My Current Organizations Budget and Spend'])

    # Row 3: Budget headers
    ws.append(['Name', 'Total Spend Text Value', 'of', 'Total Pool Text Value',
               '% Pool Spent', 'Data Viz Color [Singular]'])

    # Row 4: Budget data
    ws.append(['Bonus', '0.00', 'of', str(total_pool), 0.0, 'style1', manager_currency, 0.0])

    # Rows 5-8: Section headers
    ws.append(['Compensation Planning Header', 'Compensation Planning'])
    ws.append(['Process Preferences'])
    ws.append(['Organization Issues'])
    ws.append(['Associate', '', '', '', '', 'Bonus'])

    # Row 9: Column headers
    headers = [
        'Associate',
        'Supervisory Organization',
        'Current Job Profile',
        'Photo',
        'Errors',
        'Associate ID',
        'Current Base Pay All Countries',
        f'Current Base Pay All Countries ({manager_currency})',
        'Currency',
        'Grade',
        'Annual Bonus Target %',
        'Last Bonus Allocation %',
        'Bonus Target - Local Currency',
        f'Bonus Target - Local Currency ({manager_currency})',
        'Proposed Bonus Amount',
        f'Proposed Bonus Amount ({manager_currency})',
        'Proposed % of Target Bonus',
        'Notes',
        'Zero Bonus Allocated'
    ]
    ws.append(headers)

    # Row 10+: Employee data
    for emp in employees_data:
        row = [
            emp.get('associate', ''),
            emp.get('supervisory_organization', ''),
            emp.get('current_job_profile', ''),
            emp.get('photo', ''),
            emp.get('errors', ''),
            emp.get('associate_id', ''),
            emp.get('current_base_pay_all_countries', ''),
            emp.get('current_base_pay_manager_currency', ''),
            emp.get('currency', manager_currency),
            emp.get('grade', ''),
            emp.get('annual_bonus_target_percent', ''),
            emp.get('last_bonus_allocation_percent', ''),
            emp.get('bonus_target_local_currency', ''),
            emp.get('bonus_target_manager_currency', ''),
            emp.get('proposed_bonus_amount', ''),
            emp.get('proposed_bonus_amount_manager_currency', ''),
            emp.get('proposed_percent_of_target_bonus', ''),
            emp.get('notes', ''),
            emp.get('zero_bonus_allocated', '')
        ]
        ws.append(row)

    return wb


def get_sample_employees():
    """
    Get sample employee data for historical files.
    Uses same data as demo templates for consistency.
    """
    teams = {
        'Platform Engineering (Della Gate)': [
            ('Della Gate', 'Engineering Manager', 210000, 'M2', 6.0, 'MGR100'),
            ('Paige Duty', 'Principal Engineer', 220000, 'IC5', 5.0, 'EMP2001'),
            ('Lee Latency', 'Staff Software Developer', 185000, 'IC4', 3.75, 'EMP2002'),
            ('Mona Torr', 'Staff SRE', 180000, 'IC4', 3.75, 'EMP2003'),
            ('Robin Rollback', 'Senior Software Developer', 155000, 'IC3', 3.0, 'EMP2004'),
            ('Kenny Canary', 'Senior Software Developer', 150000, 'IC3', 3.0, 'EMP2005'),
            ('Tracey Loggins', 'Software Developer', 125000, 'IC2', 2.5, 'EMP2006'),
            ('Sue Q. Ell', 'Software Developer', 120000, 'IC2', 2.5, 'EMP2007'),
            ('Addie Min', 'Senior Software Developer', 160000, 'IC3', 3.0, 'EMP2008'),
            ('Jason Blob', 'Software Developer', 115000, 'IC2', 2.5, 'EMP2009'),
            ('Al Ert', 'Junior Software Developer', 95000, 'IC1', 2.0, 'EMP2010'),
        ],
        'Frontend Experience (Rhoda Map)': [
            ('Rhoda Map', 'Engineering Manager', 205000, 'M2', 6.0, 'MGR101'),
            ('Tim Out', 'Principal Engineer', 225000, 'IC5', 5.0, 'EMP2011'),
            ('Barbie Que', 'Staff Software Developer', 190000, 'IC4', 3.75, 'EMP2012'),
            ('Terry Byte', 'Senior Software Developer', 160000, 'IC3', 3.0, 'EMP2013'),
            ('Cody Ryder', 'Senior Software Developer', 158000, 'IC3', 3.0, 'EMP2014'),
            ('Nole Pointer', 'Senior Software Developer', 155000, 'IC3', 3.0, 'EMP2015'),
            ('Bridget Branch', 'Software Developer', 120000, 'IC2', 2.5, 'EMP2016'),
            ('Cy Ferr', 'Software Developer', 118000, 'IC2', 2.5, 'EMP2017'),
            ('Lana Wan', 'Software Developer', 122000, 'IC2', 2.5, 'EMP2018'),
            ('Phil Wall', 'Junior Software Developer', 92000, 'IC1', 2.0, 'EMP2019'),
            ('Marge Conflict', 'Software Developer', 125000, 'IC2', 2.5, 'EMP2020'),
        ],
        'Backend Services (Kay P. Eye)': [
            ('Kay P. Eye', 'Engineering Manager', 208000, 'M2', 6.0, 'MGR102'),
            ('Artie Ficial', 'Principal Engineer', 230000, 'IC5', 5.0, 'EMP2021'),
            ('Ruth Cause', 'Staff Software Developer', 188000, 'IC4', 3.75, 'EMP2022'),
            ('Matt Rick', 'Staff Software Developer', 185000, 'IC4', 3.75, 'EMP2023'),
            ('Cassie Cache', 'Senior Software Developer', 162000, 'IC3', 3.0, 'EMP2024'),
            ("Annie O'Maly", 'Senior Software Developer', 165000, 'IC3', 3.0, 'EMP2025'),
            ('Sue Do', 'Senior Software Developer', 158000, 'IC3', 3.0, 'EMP2026'),
            ('Pat Ch', 'Software Developer', 128000, 'IC2', 2.5, 'EMP2027'),
            ('Devin Null', 'Software Developer', 124000, 'IC2', 2.5, 'EMP2028'),
            ('Justin Time', 'Software Developer', 120000, 'IC2', 2.5, 'EMP2029'),
            ('Sam Box', 'Junior Software Developer', 98000, 'IC1', 2.0, 'EMP2030'),
        ],
        'Infrastructure (Agie Enda)': [
            ('Agie Enda', 'Engineering Manager', 212000, 'M2', 6.0, 'MGR103'),
            ('Ty Po', 'Principal Engineer', 235000, 'IC5', 5.0, 'EMP2031'),
            ('Mike Roservices', 'Staff SRE', 192000, 'IC4', 3.75, 'EMP2032'),
            ('Val Idation', 'Staff SRE', 195000, 'IC4', 3.75, 'EMP2033'),
            ('Lou Pe', 'Senior SRE', 168000, 'IC3', 3.0, 'EMP2034'),
            ('Connie Tainer', 'Senior SRE', 162000, 'IC3', 3.0, 'EMP2035'),
            ('Exa M. Elle', 'Senior SRE', 170000, 'IC3', 3.0, 'EMP2036'),
            ('Noah Node', 'SRE', 130000, 'IC2', 2.5, 'EMP2037'),
            ('Sara Ver', 'SRE', 125000, 'IC2', 2.5, 'EMP2038'),
            ('Bill Ding', 'Senior SRE', 165000, 'IC3', 3.0, 'EMP2039'),
            ('Dee Ploi', 'SRE', 128000, 'IC2', 2.5, 'EMP2040'),
        ],
        'Site Reliability (Mai Stone)': [
            ('Mai Stone', 'Engineering Manager', 215000, 'M2', 6.0, 'MGR104'),
        ],
    }

    employees = []
    import random
    random.seed(42)  # Reproducible

    for team_name, members in teams.items():
        for (name, job, salary, grade, bonus_pct, emp_id) in members:
            bonus_target = salary * (bonus_pct / 100)
            rating = random.randint(70, 140)

            employees.append({
                'associate_id': emp_id,
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
                'proposed_percent_of_target_bonus': rating,
                'notes': f'Performance Rating: {rating}%\nJustification: Sample historical data',
            })

    return employees


def main():
    print("Regenerating sample XLSX files with new Workday format...")
    print()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    samples_dir = os.path.join(project_dir, 'samples')

    employees = get_sample_employees()
    total_pool = sum(e.get('bonus_target_local_currency', 0) for e in employees)

    periods = [
        ('2023-Q3', 'CY23 Q3'),
        ('2023-Q4', 'CY23 Q4'),
        ('2024-Q1', 'CY24 Q1'),
        ('2024-Q2', 'CY24 Q2'),
        ('2024-Q3', 'CY24 Q3'),
        ('2024-Q4', 'CY24 Q4'),
    ]

    for period_id, period_name in periods:
        filename = f'sample-historical-{period_id}.xlsx'
        filepath = os.path.join(samples_dir, filename)

        wb = create_workday_xlsx(employees, period_name, total_pool)
        wb.save(filepath)
        print(f"  Created {filename}")

    print()
    print(f"Done! Updated {len(periods)} sample files in samples/")


if __name__ == '__main__':
    main()
