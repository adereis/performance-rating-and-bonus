#!/usr/bin/env python3
"""
Convert bonus-from-wd.xlsx to SQLite database.
This script reads the HR export and imports all data into the database.
"""
import openpyxl
import csv
import os
from models import Employee, init_db, get_db

def convert_xlsx_to_db(xlsx_file='bonus-from-wd.xlsx'):
    """Convert XLSX file directly to database."""

    if not os.path.exists(xlsx_file):
        print(f"Error: {xlsx_file} not found")
        return False

    # Initialize database
    init_db()

    # Load the workbook
    wb = openpyxl.load_workbook(xlsx_file)
    sheet = wb.active

    # Read all rows
    rows = list(sheet.iter_rows(values_only=True))

    if len(rows) < 2:
        print("Error: Not enough data in Excel file")
        return False

    # Row 1 (index 1) contains the actual headers
    headers = rows[1]

    print("Importing from Workday export:")
    print(f"Total columns: {len([h for h in headers if h])}")
    print(f"Total rows: {len(rows)}")

    db = get_db()

    try:
        imported = 0
        updated = 0

        # Column indices (based on Workday export structure)
        COL_ASSOCIATE = 0
        COL_SUPERVISORY_ORG = 1
        COL_JOB_PROFILE = 2
        COL_PHOTO = 3
        COL_ERRORS = 4
        COL_ASSOCIATE_ID = 5
        COL_BASE_PAY = 6
        COL_BASE_PAY_USD = 7
        COL_CURRENCY = 8
        COL_GRADE = 9
        COL_ANNUAL_BONUS_TARGET = 10
        COL_LAST_BONUS_ALLOC = 11
        COL_BONUS_TARGET_LOCAL = 12
        COL_BONUS_TARGET_USD = 13
        COL_PROPOSED_BONUS = 14
        COL_PROPOSED_BONUS_USD = 15
        COL_PROPOSED_PCT = 16
        COL_NOTES = 17
        COL_ZERO_BONUS = 18
        COL_PERFORMANCE_RATING = 19  # Optional - only in sample data

        # Process data rows (start from row 2, which is index 2)
        for i, row in enumerate(rows[2:], start=2):
            if not row or not row[COL_ASSOCIATE]:  # Skip empty rows
                continue

            associate_id = str(row[COL_ASSOCIATE_ID]) if row[COL_ASSOCIATE_ID] else f"TEMP_{i}"
            associate_name = str(row[COL_ASSOCIATE]).strip()

            # Check if employee exists
            existing = db.query(Employee).filter(Employee.associate_id == associate_id).first()

            if existing:
                employee = existing
                updated += 1
            else:
                employee = Employee(associate_id=associate_id)
                imported += 1

            # Helper to parse floats
            def parse_float(val):
                try:
                    return float(val) if val else None
                except (ValueError, TypeError):
                    return None

            # Map Workday columns to model
            employee.associate = associate_name
            employee.supervisory_organization = str(row[COL_SUPERVISORY_ORG]) if row[COL_SUPERVISORY_ORG] else ''
            employee.current_job_profile = str(row[COL_JOB_PROFILE]) if row[COL_JOB_PROFILE] else ''
            employee.photo = str(row[COL_PHOTO]) if row[COL_PHOTO] else ''
            employee.errors = str(row[COL_ERRORS]) if row[COL_ERRORS] else ''
            employee.current_base_pay_all_countries = parse_float(row[COL_BASE_PAY])
            employee.current_base_pay_all_countries_usd = parse_float(row[COL_BASE_PAY_USD])
            employee.currency = str(row[COL_CURRENCY]) if row[COL_CURRENCY] else ''
            employee.grade = str(row[COL_GRADE]) if row[COL_GRADE] else ''
            employee.annual_bonus_target_percent = parse_float(row[COL_ANNUAL_BONUS_TARGET])
            employee.last_bonus_allocation_percent = parse_float(row[COL_LAST_BONUS_ALLOC])
            employee.bonus_target_local_currency = parse_float(row[COL_BONUS_TARGET_LOCAL])
            employee.bonus_target_local_currency_usd = parse_float(row[COL_BONUS_TARGET_USD])
            employee.proposed_bonus_amount = parse_float(row[COL_PROPOSED_BONUS])
            employee.proposed_bonus_amount_usd = parse_float(row[COL_PROPOSED_BONUS_USD])
            employee.proposed_percent_of_target_bonus = parse_float(row[COL_PROPOSED_PCT])
            employee.notes = str(row[COL_NOTES]) if row[COL_NOTES] else ''
            employee.zero_bonus_allocated = str(row[COL_ZERO_BONUS]) if row[COL_ZERO_BONUS] else ''

            # Initialize manager input fields as empty if new
            if not existing:
                # Check if this is sample data with performance ratings included
                if len(row) > COL_PERFORMANCE_RATING and row[COL_PERFORMANCE_RATING]:
                    employee.performance_rating_percent = parse_float(row[COL_PERFORMANCE_RATING])
                else:
                    employee.performance_rating_percent = None

                employee.justification = ''
                employee.mentor = ''
                employee.mentees = ''
                employee.ai_activities = ''
                employee.last_updated = None

                db.add(employee)

        db.commit()

        print(f"\n✓ Successfully imported {imported} new employees")
        print(f"✓ Updated {updated} existing employees")
        print(f"✓ Total employees in database: {db.query(Employee).count()}")

        return True

    except Exception as e:
        db.rollback()
        print(f"\n✗ Error importing data: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == '__main__':
    import sys

    # Allow specifying a different file via command line
    xlsx_file = sys.argv[1] if len(sys.argv) > 1 else 'bonus-from-wd.xlsx'

    print(f"Converting {xlsx_file} to database...")
    convert_xlsx_to_db(xlsx_file)
