#!/usr/bin/env python3
"""
Populate performance ratings, justifications, tenets, and talent data for sample data.

This script adds manager-entered data (ratings, justifications, tenets, talent
calibration) to employees after Workday data has been imported. This separation
maintains the architectural distinction between Workday export data and local ratings.

Usage:
    python3 populate_sample_ratings.py small     # For sample-data-small.xlsx
    python3 populate_sample_ratings.py large     # For sample-data-large.xlsx
    python3 populate_sample_ratings.py small --with-tenets  # Include tenets
    python3 populate_sample_ratings.py large --with-tenets  # Include tenets
    python3 populate_sample_ratings.py small --with-talent  # Include talent calibration
    python3 populate_sample_ratings.py large --with-talent --with-tenets  # All data
"""
import sys
import os
import json
import random
from datetime import datetime

# Add parent directory to path for imports when running as standalone script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Employee, get_db, init_db, derive_overall_performance, derive_future_talent


# ============================================================================
# Talent Calibration Enums (must match Spec §3 exactly)
# ============================================================================

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

AGILITY_OPTIONS = [
    'Always/Most of the Time',
    'Sometimes'
]

MOVEMENT_READINESS_OPTIONS = [
    'Continue growing in current role',
    'Ready Now to be promoted in current role',
    'Ready for lateral move',
    'Ready to be promoted outside of current role',
    'Not well placed'
]


def generate_talent_data(bonus_rating: int) -> dict:
    """
    Generate talent calibration data that's roughly aligned with performance rating.

    Args:
        bonus_rating: The employee's performance rating percent (0-200)

    Returns:
        dict with talent fields
    """
    # Map performance rating to talent calibration distribution
    # Higher performers more likely to have higher talent ratings
    # Movement weights: [Continue, Promotion in role, Lateral, Promotion outside, Not well placed]
    if bonus_rating >= 130:
        # High performers: likely Surpasses
        what_weights = [0.6, 0.35, 0.05]  # Surpasses, Meets, MeetsSome
        how_weights = [0.5, 0.45, 0.05, 0.0]
        agility_weight = 0.6  # 60% chance of "Always"
        movement_weights = [0.45, 0.35, 0.1, 0.1, 0.0]
    elif bonus_rating >= 110:
        # Strong performers: likely Meets with some Surpasses
        what_weights = [0.3, 0.65, 0.05]
        how_weights = [0.25, 0.65, 0.1, 0.0]
        agility_weight = 0.4
        movement_weights = [0.55, 0.25, 0.1, 0.1, 0.0]
    elif bonus_rating >= 90:
        # Solid performers: mostly Meets
        what_weights = [0.1, 0.8, 0.1]
        how_weights = [0.1, 0.75, 0.15, 0.0]
        agility_weight = 0.3
        movement_weights = [0.75, 0.15, 0.05, 0.05, 0.0]
    else:
        # Underperformers: likely Meets Some or lower
        what_weights = [0.0, 0.4, 0.6]
        how_weights = [0.0, 0.3, 0.5, 0.2]
        agility_weight = 0.15
        movement_weights = [0.80, 0.0, 0.05, 0.0, 0.15]

    # Generate What/How
    perf_what = random.choices(PERF_WHAT_OPTIONS, weights=what_weights)[0]
    perf_how = random.choices(PERF_HOW_OPTIONS, weights=how_weights)[0]

    # Generate agility ratings
    growth = 'Always/Most of the Time' if random.random() < agility_weight else 'Sometimes'
    change = 'Always/Most of the Time' if random.random() < agility_weight else 'Sometimes'

    # Generate movement readiness
    movement = random.choices(MOVEMENT_READINESS_OPTIONS, weights=movement_weights)[0]

    # Derive fields
    overall = derive_overall_performance(perf_what, perf_how)
    future_talent = derive_future_talent(growth, change)

    # Generate "last cycle" data (for year-over-year comparison)
    # Slightly different from current to show change
    last_what = random.choice(PERF_WHAT_OPTIONS)
    last_how = random.choice(PERF_HOW_OPTIONS[:3])  # Exclude "Does Not Meet" from history
    last_overall = derive_overall_performance(last_what, last_how)
    last_growth = random.choice(AGILITY_OPTIONS)
    last_change = random.choice(AGILITY_OPTIONS)
    last_future_talent = derive_future_talent(last_growth, last_change)
    last_movement = random.choice(MOVEMENT_READINESS_OPTIONS)

    return {
        'talent_perf_what': perf_what,
        'talent_perf_how': perf_how,
        'talent_overall_perf': overall,
        'talent_growth_agility': growth,
        'talent_change_agility': change,
        'talent_identified_future': future_talent,
        'talent_movement_readiness': movement,
        # Historical data
        'talent_last_overall_perf': last_overall,
        'talent_last_identified_future': last_future_talent,
        'talent_last_movement_readiness': last_movement,
    }


# Sample promotion data for a few high performers
# Includes candidates from both small (12) and large (55) datasets
PROMO_CANDIDATES = {
    # Small team candidates
    'Al Ert': {
        'job_profile': 'Principal SRE, 1847',
        'business_need': 'Team expanding scope to cover global reliability',
        'role_scope': 'Will lead cross-regional SRE initiatives',
        'readiness': 'Demonstrated technical leadership and mentorship',
    },
    'Sue Q. Ell': {
        'job_profile': 'Staff Software Developer, 1623',
        'business_need': 'Need senior DB expertise for new product line',
        'role_scope': 'Expand from query optimization to full data architecture',
        'readiness': 'Strong IC track record, ready for staff scope',
    },
    # Large org candidates (additional high performers)
    'Artie Ficial': {
        'job_profile': 'Principal Software Developer, 2134',
        'business_need': 'Architecture leadership for distributed systems initiative',
        'role_scope': 'Lead cross-team technical strategy and system design',
        'readiness': 'Exceptional technical vision, proven cross-team influence',
    },
    'Ty Po': {
        'job_profile': 'Staff SRE, 1892',
        'business_need': 'Infrastructure modernization requires senior leadership',
        'role_scope': 'Own infrastructure strategy for platform reliability',
        'readiness': 'Outstanding track record, ready for expanded scope',
    },
    "Ray D. O'Button": {
        'job_profile': 'Principal SRE, 1956',
        'business_need': 'SLO/SLI framework expansion across organization',
        'role_scope': 'Define reliability standards and mentor SRE teams',
        'readiness': 'Demonstrated expertise in reliability engineering',
    },
}


# ============================================================================
# Performance Rating Data
# ============================================================================

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
    """Load tenets configuration from samples/tenets-sample.json."""
    try:
        with open('samples/tenets-sample.json', 'r') as f:
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


def populate_ratings(size='small', include_tenets=False, include_talent=False):
    """Populate performance ratings, justifications, and optionally tenets/talent for sample data."""

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
        talent_count = 0
        promo_count = 0

        # Track talent distribution for reporting
        talent_stats = {
            'overall': {},
            'future_talent': 0,
            'movement': {}
        }

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

                # Optionally populate talent calibration data
                if include_talent:
                    talent_data = generate_talent_data(rating)

                    emp.talent_perf_what = talent_data['talent_perf_what']
                    emp.talent_perf_how = talent_data['talent_perf_how']
                    emp.talent_overall_perf = talent_data['talent_overall_perf']
                    emp.talent_growth_agility = talent_data['talent_growth_agility']
                    emp.talent_change_agility = talent_data['talent_change_agility']
                    emp.talent_identified_future = talent_data['talent_identified_future']
                    emp.talent_movement_readiness = talent_data['talent_movement_readiness']

                    # Historical "last cycle" data
                    emp.talent_last_overall_perf = talent_data['talent_last_overall_perf']
                    emp.talent_last_identified_future = talent_data['talent_last_identified_future']
                    emp.talent_last_movement_readiness = talent_data['talent_last_movement_readiness']

                    emp.talent_last_updated = datetime.now()
                    talent_count += 1

                    # Track stats
                    overall = talent_data['talent_overall_perf']
                    talent_stats['overall'][overall] = talent_stats['overall'].get(overall, 0) + 1
                    if talent_data['talent_identified_future']:
                        talent_stats['future_talent'] += 1
                    mvmt = talent_data['talent_movement_readiness']
                    talent_stats['movement'][mvmt] = talent_stats['movement'].get(mvmt, 0) + 1

                    # Add promotion data for specific candidates
                    if employee_name in PROMO_CANDIDATES:
                        promo = PROMO_CANDIDATES[employee_name]
                        emp.talent_promo_job_profile = promo['job_profile']
                        emp.talent_promo_business_need = promo['business_need']
                        emp.talent_promo_role_scope = promo['role_scope']
                        emp.talent_promo_readiness = promo['readiness']
                        # Override movement to "Ready for Promotion"
                        emp.talent_movement_readiness = 'Ready Now to be promoted in current role'
                        promo_count += 1

                    # Optionally add talent tenets (reuse bonus tenets if enabled)
                    if include_tenets and all_tenets:
                        t_strengths, t_improvements = generate_random_tenets(all_tenets, 2, 2)
                        emp.talent_tenets_strengths = json.dumps(t_strengths)
                        emp.talent_tenets_improvements = json.dumps(t_improvements)

        db.commit()
        print(f"✓ Populated {updated_count} performance ratings for {dataset_name}")
        print(f"  - Ratings range: {min(r[0] for r in ratings_data.values())}% - {max(r[0] for r in ratings_data.values())}%")
        print(f"  - All employees have ratings and justifications")

        if include_tenets and all_tenets:
            print(f"  - Added random tenets evaluation for {tenets_count} employees ({len(all_tenets)} tenets available)")

        if include_talent:
            print(f"\n✓ Populated {talent_count} talent calibration records")
            print(f"  Overall Performance Distribution:")
            for perf, count in sorted(talent_stats['overall'].items()):
                pct = 100 * count / talent_count if talent_count else 0
                print(f"    {perf}: {count} ({pct:.0f}%)")
            print(f"  Future Talent: {talent_stats['future_talent']} ({100 * talent_stats['future_talent'] / talent_count:.0f}%)")
            print(f"  Movement Readiness:")
            for mvmt, count in sorted(talent_stats['movement'].items()):
                pct = 100 * count / talent_count if talent_count else 0
                print(f"    {mvmt}: {count} ({pct:.0f}%)")
            if promo_count:
                print(f"  Promotion candidates with full data: {promo_count}")

        print(f"\n  Ready to view at http://localhost:5000")
        print(f"  Mentor/mentee/AI activity fields left blank for you to fill in")

    except Exception as e:
        db.rollback()
        print(f"✗ Error populating ratings: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def main():
    """Main entry point with argument parsing."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Populate performance ratings, justifications, tenets, and talent calibration for sample data.',
        epilog='''
Examples:
  python3 scripts/populate_sample_ratings.py small
  python3 scripts/populate_sample_ratings.py large
  python3 scripts/populate_sample_ratings.py small --with-tenets
  python3 scripts/populate_sample_ratings.py large --with-tenets
  python3 scripts/populate_sample_ratings.py small --with-talent
  python3 scripts/populate_sample_ratings.py large --with-talent --with-tenets

This script adds manager-entered data (ratings, justifications, tenets, talent
calibration) to employees after Workday data has been imported. Run this after
importing sample-data-small.xlsx or sample-data-large.xlsx.

Talent calibration data (--with-talent) includes:
  - Performance What/How ratings (aligned with performance rating)
  - Derived Overall Performance (Spec §4.1)
  - Growth/Change Agility and derived Future Talent (Spec §4.2)
  - Movement Readiness
  - Historical "last cycle" data for year-over-year comparison
  - Promotion data for select high performers
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'size',
        choices=['small', 'large'],
        help='Dataset size: "small" for 12-employee team, "large" for 55-employee org'
    )
    parser.add_argument(
        '--with-tenets',
        action='store_true',
        help='Also populate random tenets evaluation (requires tenets.json or samples/tenets-sample.json)'
    )
    parser.add_argument(
        '--with-talent',
        action='store_true',
        help='Also populate talent calibration data (Performance What/How, agility, movement, etc.)'
    )

    args = parser.parse_args()
    populate_ratings(args.size, args.with_tenets, args.with_talent)


if __name__ == '__main__':
    main()
