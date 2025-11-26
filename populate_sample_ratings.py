#!/usr/bin/env python3
"""
Populate performance ratings, justifications, and tenets for sample data.

This script adds manager-entered data (ratings, justifications, tenets) to
employees after Workday data has been imported. This separation maintains
the architectural distinction between Workday export data and local ratings.

Usage:
    python3 populate_sample_ratings.py small     # For sample-data-small.xlsx
    python3 populate_sample_ratings.py large     # For sample-data-large.xlsx
    python3 populate_sample_ratings.py small --with-tenets  # Include tenets
    python3 populate_sample_ratings.py large --with-tenets  # Include tenets
"""
import sys
import os
import json
import random
from datetime import datetime
from models import Employee, get_db, init_db


# Sample ratings and justifications for small team
SMALL_TEAM_RATINGS = {
    'Paige Duty': (130, 'Exceptional technical leadership and on-call reliability'),
    'Lee Latency': (120, 'Outstanding performance optimization work'),
    'Mona Torr': (110, 'Strong monitoring and observability contributions'),
    'Robin Rollback': (105, 'Reliable deployment management'),
    'Kenny Canary': (100, 'Solid canary testing and deployment work'),
    'Tracey Loggins': (115, 'Excellent logging infrastructure improvements'),
    'Sue Q. Ell': (125, 'Outstanding database optimization and query performance'),
    'Jason Blob': (95, 'Good progress on unstructured data handling'),
    'Al Ert': (135, 'Critical alerting system improvements, exceptional work'),
    'Addie Min': (110, 'Solid access management and security work'),
    'Tim Out': (85, 'Needs improvement in reliability and uptime'),
    'Barbie Que': (110, 'Strong message queue management'),
}

# Sample ratings and justifications for large org
LARGE_ORG_RATINGS = {
    # Della Gate's team
    'Paige Duty': (140, 'Exceptional technical vision and platform architecture'),
    'Lee Latency': (135, 'Outstanding team leadership and delivery'),
    'Mona Torr': (130, 'Outstanding platform reliability improvements'),
    'Robin Rollback': (115, 'Strong API development work'),
    'Kenny Canary': (110, 'Solid infrastructure contributions'),
    'Tracey Loggins': (105, 'Good platform integration work'),
    'Sue Q. Ell': (100, 'Met expectations on service deployment'),
    'Jason Blob': (95, 'Steady progress on platform features'),
    'Al Ert': (90, 'Needs more ownership of features'),
    'Addie Min': (110, 'Solid mentorship and code quality'),

    # Rhoda Map's team
    'Tim Out': (185, 'Exceptional performance - transformational UI architecture work'),
    'Barbie Que': (130, 'Strong team growth and technical direction'),
    'Terry Byte': (120, 'Strong React component library work'),
    'Nole Pointer': (110, 'Solid accessibility improvements'),
    'Marge Conflict': (45, 'Serious performance concerns - requires improvement plan'),
    'Bridget Branch': (100, 'Good responsive design work'),
    'Cody Ryder': (115, 'Excellent state management refactoring'),
    'Cy Ferr': (100, 'Solid component development'),
    'Phil Wall': (65, 'Below expectations - needs significant improvement'),
    'Lana Wan': (85, 'Needs more proactive communication'),

    # Kay P. Eye's team
    'Artie Ficial': (140, 'Exceptional distributed systems architecture'),
    'Ruth Cause': (130, 'Outstanding microservices design'),
    'Matt Rick': (130, 'Excellent cross-team coordination and delivery'),
    'Cassie Cache': (120, 'Strong API design and implementation'),
    'Sue Do': (110, 'Solid service reliability work'),
    'Pat Ch': (105, 'Good backend feature development'),
    'Devin Null': (100, 'Met expectations on service development'),
    'Justin Time': (95, 'Steady progress on REST API work'),
    "Annie O'Maly": (115, 'Strong database optimization'),
    'Sam Box': (90, 'Adequate progress on microservices'),

    # Agie Enda's team
    'Val Idation': (120, 'Outstanding infrastructure automation'),
    'Bill Ding': (105, 'Good deployment pipeline work'),
    'Ty Po': (135, 'Exceptional infrastructure modernization'),
    'Mike Roservices': (130, 'Strong infrastructure team leadership'),
    'Lou Pe': (120, 'Outstanding CI/CD pipeline improvements'),
    'Connie Tainer': (110, 'Strong Kubernetes migration work'),
    'Noah Node': (105, 'Good infrastructure automation'),
    'Sara Ver': (100, 'Solid monitoring setup'),
    'Exa M. Elle': (115, 'Strong cloud cost optimization'),
    'Dee Ploi': (95, 'Good disaster recovery planning'),

    # Mai Stone's team
    "Ray D. O'Button": (135, 'Outstanding SLO/SLI framework design'),
    'Cam Elcase': (130, 'Excellent reliability culture building'),
    'Hashim Map': (125, 'Exceptional on-call process improvements'),
    'Ben Chmark': (120, 'Strong incident response leadership'),
    'Grace Full': (110, 'Solid observability improvements'),
    'Shel Script': (110, 'Strong monitoring and alerting work'),
    'Sal T. Hash': (100, 'Good chaos engineering initiatives'),
    'Reba Boot': (100, 'Solid capacity planning work'),
    'Stan Dup': (95, 'Adequate progress on reliability metrics'),
    'Kay Eight': (90, 'Needs more proactive incident prevention'),
}


def load_tenets():
    """Load tenets configuration from tenets-sample.json."""
    try:
        with open('tenets-sample.json', 'r') as f:
            config = json.load(f)
            return [t['id'] for t in config.get('tenets', []) if t.get('active', True)]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def generate_random_tenets(all_tenets, strength_count=3, improvement_count=3):
    """
    Generate random tenets for an employee.

    Returns:
        tuple: (strengths_list, improvements_list) - Lists of tenet IDs
    """
    if not all_tenets:
        return ([], [])

    # Randomly select strengths (3 unique tenets)
    strengths = random.sample(all_tenets, min(strength_count, len(all_tenets)))

    # Randomly select improvements (3 unique tenets, different from strengths)
    remaining_tenets = [t for t in all_tenets if t not in strengths]
    improvements = random.sample(remaining_tenets, min(improvement_count, len(remaining_tenets)))

    return (strengths, improvements)


def populate_ratings(size='small', include_tenets=False):
    """Populate performance ratings, justifications, and optionally tenets for sample data."""

    # Check if database exists
    if not os.path.exists('ratings.db'):
        print("⚠ Database not found. Please import sample data first:")
        filename = 'sample-data-small.xlsx' if size == 'small' else 'sample-data-large.xlsx'
        print(f"  python3 convert_xlsx.py {filename}")
        return

    # Select appropriate rating dataset
    ratings_data = SMALL_TEAM_RATINGS if size == 'small' else LARGE_ORG_RATINGS
    dataset_name = "small team" if size == 'small' else "large organization"

    # Load tenets if requested
    all_tenets = load_tenets() if include_tenets else None

    db = get_db()
    try:
        updated_count = 0
        tenets_count = 0

        for employee_name, (rating, justification) in ratings_data.items():
            emp = db.query(Employee).filter(Employee.associate == employee_name).first()
            if emp:
                # Populate performance rating and justification
                emp.performance_rating_percent = rating
                emp.justification = justification
                emp.last_updated = datetime.now()
                updated_count += 1

                # Optionally populate tenets
                if include_tenets and all_tenets:
                    strengths, improvements = generate_random_tenets(all_tenets)
                    emp.tenets_strengths = json.dumps(strengths)
                    emp.tenets_improvements = json.dumps(improvements)
                    tenets_count += 1

        db.commit()
        print(f"✓ Populated {updated_count} performance ratings for {dataset_name}")
        print(f"  - Ratings range: {min(r[0] for r in ratings_data.values())}% - {max(r[0] for r in ratings_data.values())}%")
        print(f"  - All employees have ratings and justifications")
        if include_tenets and all_tenets:
            print(f"  - Added random tenets evaluation for {tenets_count} employees ({len(all_tenets)} tenets available)")
        print(f"\n  Ready to view at http://localhost:5000")
        print(f"  Mentor/mentee/AI activity fields left blank for you to fill in")
    except Exception as e:
        db.rollback()
        print(f"✗ Error populating ratings: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == '__main__':
    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python3 populate_sample_ratings.py [small|large] [--with-tenets]")
        print("\nExamples:")
        print("  python3 populate_sample_ratings.py small")
        print("  python3 populate_sample_ratings.py large --with-tenets")
        sys.exit(1)

    size = sys.argv[1]
    if size not in ['small', 'large']:
        print("Error: Size must be 'small' or 'large'")
        sys.exit(1)

    include_tenets = '--with-tenets' in sys.argv
    populate_ratings(size, include_tenets)
