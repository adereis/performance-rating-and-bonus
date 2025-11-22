#!/usr/bin/env python3
"""
Populate performance ratings for sample data.

This script adds realistic performance ratings and justifications to the
sample employee data after it has been imported.

Usage:
    python3 populate_sample_ratings.py small    # For sample-data-small.xlsx
    python3 populate_sample_ratings.py large    # For sample-data-large.xlsx
"""
import sys
import os
from datetime import datetime
from models import Employee, get_db, init_db
import create_sample_data


def populate_ratings(size='small'):
    """Populate performance ratings for sample data."""

    # Check if database exists
    if not os.path.exists('ratings.db'):
        print("⚠ Database not found. Please import sample data first:")
        filename = 'sample-data-small.xlsx' if size == 'small' else 'sample-data-large.xlsx'
        print(f"  python3 convert_xlsx.py {filename}")
        return

    # Get the sample data with ratings
    if size == 'small':
        employees_data = create_sample_data.get_small_team_data()
        dataset_name = "small team"
    else:
        employees_data = create_sample_data.get_large_org_data()
        dataset_name = "large organization"

    db = get_db()
    try:
        updated_count = 0
        for emp_data in employees_data:
            emp = db.query(Employee).filter(Employee.associate == emp_data['associate']).first()
            if emp:
                emp.performance_rating_percent = emp_data['rating']
                emp.justification = emp_data['justification']
                emp.last_updated = datetime.now()
                updated_count += 1

        db.commit()
        print(f"✓ Populated {updated_count} performance ratings for {dataset_name}")
        print(f"  - Ready to view at http://localhost:5000")
        print(f"  - All employees now have ratings and can be used for bonus calculation")
    except Exception as e:
        db.rollback()
        print(f"✗ Error populating ratings: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == '__main__':
    size = 'large' if len(sys.argv) > 1 and sys.argv[1] == 'large' else 'small'
    populate_ratings(size)
