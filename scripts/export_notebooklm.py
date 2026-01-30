#!/usr/bin/env python3
"""
Generate NotebookLM-compatible markdown files from ratings.db.

Creates individual team files and a summary file for use in NotebookLM,
enabling AI-powered analysis of team performance and development data.

Usage:
    python scripts/export_notebooklm.py [--output-dir ~/tmp/notebooklm-export]

Output:
    - 00-organization-summary.md: Aggregate statistics, org structure, patterns
    - team-{manager-name}.md: Individual team files with member details
    - complete-team-data.md: All-in-one file for single-document use
"""

import argparse
import sqlite3
import json
import os
from collections import defaultdict
from datetime import datetime

# Tenet ID to human-readable name mapping
TENETS = {
    'ownership-1': 'Champion Ownership: Prioritize quality',
    'ownership-2': 'Champion Ownership: Act with urgency',
    'ownership-3': 'Champion Ownership: Own outcomes',
    'trust-1': 'Default to Trust: Act with integrity',
    'trust-2': 'Default to Trust: Trust builds community',
    'trust-3': 'Default to Trust: Clear, honest communication',
    'results-1': 'Drive Impactful Results: Ambitious goals',
    'results-2': 'Drive Impactful Results: Focus on what matters',
    'results-3': 'Drive Impactful Results: Continuous improvement',
    'collaboration-1': 'Open Collaboration: Foster transparency',
    'collaboration-2': 'Open Collaboration: Global perspective',
    'collaboration-3': 'Open Collaboration: Seek diverse perspectives',
    'improvement-1': 'Engineer Sustainability: Future-proof solutions',
    'improvement-2': 'Engineer Sustainability: Balance speed and stability',
    'improvement-3': 'Engineer Sustainability: Reduce complexity',
}


def parse_tenets(tenets_json):
    """Convert JSON array of tenet IDs to human-readable names."""
    if not tenets_json:
        return []
    try:
        ids = json.loads(tenets_json)
        return [TENETS.get(t, t) for t in ids]
    except:
        return []


def format_duration(duration_str):
    """Clean up duration strings like '2 year(s), 3 month(s), 15 day(s)'."""
    if not duration_str:
        return 'Unknown'
    return duration_str.replace('(s)', '').replace(' day', '').strip(', ')


def get_employees(db_path):
    """Fetch all employees from the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM employees ORDER BY supervisory_organization, associate")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_bonus_settings(db_path):
    """Fetch bonus settings."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bonus_settings LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def generate_employee_section(emp):
    """Generate markdown section for a single employee."""
    lines = []
    name = emp['associate']

    lines.append(f"### {name}")
    lines.append("")

    # Basic info
    lines.append(f"- **Role**: {emp['current_job_profile'] or 'Unknown'}")
    lines.append(f"- **Level**: {emp['management_level'] or 'Unknown'}")
    lines.append(f"- **Country**: {emp['country'] or 'Unknown'}")
    lines.append(f"- **Manager**: {emp['supervisory_organization'] or 'Unknown'}")

    # Tenure
    los = format_duration(emp['length_of_service'])
    tij = format_duration(emp['time_in_job_profile'])
    lines.append(f"- **Tenure at Company**: {los}")
    lines.append(f"- **Time in Current Role**: {tij}")
    lines.append("")

    # Talent Calibration
    lines.append("#### Talent Calibration Assessment")
    lines.append("")

    perf_what = emp['talent_perf_what'] or 'Not assessed'
    perf_how = emp['talent_perf_how'] or 'Not assessed'
    overall = emp['talent_overall_perf'] or 'Not assessed'

    lines.append(f"- **Performance (What)**: {perf_what}")
    lines.append(f"- **Performance (How)**: {perf_how}")
    lines.append(f"- **Overall Performance**: {overall}")
    lines.append("")

    # Future Talent / Agility
    growth = emp['talent_growth_agility'] or 'Not assessed'
    change = emp['talent_change_agility'] or 'Not assessed'
    movement = emp['talent_movement_readiness'] or 'Not assessed'

    lines.append(f"- **Growth Agility**: {growth}")
    lines.append(f"- **Change Agility**: {change}")
    lines.append(f"- **Movement Readiness**: {movement}")
    lines.append("")

    # Tenets
    strengths = parse_tenets(emp['talent_tenets_strengths'])
    improvements = parse_tenets(emp['talent_tenets_improvements'])

    if strengths:
        lines.append("#### Strengths (Tenets)")
        for s in strengths:
            lines.append(f"- {s}")
        lines.append("")

    if improvements:
        lines.append("#### Areas for Improvement (Tenets)")
        for i in improvements:
            lines.append(f"- {i}")
        lines.append("")

    # Mentor/Mentee relationships
    mentor = emp['talent_mentor']
    mentees = emp['talent_mentees']

    if mentor or mentees:
        lines.append("#### Mentoring")
        if mentor:
            lines.append(f"- **Mentor**: {mentor}")
        if mentees:
            lines.append(f"- **Mentees**: {mentees}")
        lines.append("")

    # Promotion target
    promo_profile = emp['talent_promo_job_profile']
    promo_readiness = emp['talent_promo_readiness']

    if promo_profile:
        lines.append("#### Promotion Consideration")
        lines.append(f"- **Target Role**: {promo_profile}")
        if promo_readiness:
            lines.append("")
            lines.append("**Readiness Assessment:**")
            lines.append("")
            for para in promo_readiness.strip().split('\n\n'):
                lines.append(para.strip())
                lines.append("")

    # Proposed Actions (the rich qualitative data)
    proposed = emp['talent_proposed_actions']
    if proposed:
        lines.append("#### Development Plan & Manager Notes")
        lines.append("")
        for para in proposed.strip().split('\n'):
            if para.strip():
                lines.append(para)
        lines.append("")

    lines.append("---")
    lines.append("")

    return '\n'.join(lines)


def generate_team_file(manager, employees):
    """Generate a markdown file for a single team."""
    lines = []

    lines.append(f"# Team: {manager}")
    lines.append("")
    lines.append(f"**Team Size**: {len(employees)} members")
    lines.append("")

    # Team composition summary
    countries = defaultdict(int)
    roles = defaultdict(int)
    perf_dist = defaultdict(int)

    for emp in employees:
        countries[emp['country'] or 'Unknown'] += 1
        roles[emp['current_job_profile'] or 'Unknown'] += 1
        perf_dist[emp['talent_overall_perf'] or 'Unknown'] += 1

    lines.append("## Team Overview")
    lines.append("")

    lines.append("### Geographic Distribution")
    for country, count in sorted(countries.items(), key=lambda x: -x[1]):
        lines.append(f"- {country}: {count}")
    lines.append("")

    lines.append("### Role Distribution")
    for role, count in sorted(roles.items(), key=lambda x: -x[1]):
        lines.append(f"- {role}: {count}")
    lines.append("")

    lines.append("### Performance Distribution")
    for perf, count in sorted(perf_dist.items(), key=lambda x: -x[1]):
        lines.append(f"- {perf}: {count}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Team Members")
    lines.append("")

    # Sort by overall performance, then name
    perf_order = {'High Impact Performer': 0, 'Successful Performer': 1, 'Evolving Performer': 2, 'Low Performer': 3}
    sorted_employees = sorted(employees, key=lambda e: (perf_order.get(e['talent_overall_perf'], 4), e['associate']))

    for emp in sorted_employees:
        lines.append(generate_employee_section(emp))

    return '\n'.join(lines)


def generate_summary_file(all_employees, settings):
    """Generate the organization summary file."""
    lines = []

    lines.append("# Organization Performance Summary")
    lines.append("")
    lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"**Total Employees**: {len(all_employees)}")
    lines.append("")

    # Organization structure
    lines.append("## Organization Structure")
    lines.append("")

    managers = defaultdict(list)
    for emp in all_employees:
        managers[emp['supervisory_organization']].append(emp)

    lines.append("| Manager | Team Size | High Impact | Successful | Evolving | Low |")
    lines.append("|---------|-----------|-------------|------------|----------|-----|")

    for mgr, team in sorted(managers.items(), key=lambda x: -len(x[1])):
        hi = sum(1 for e in team if e['talent_overall_perf'] == 'High Impact Performer')
        su = sum(1 for e in team if e['talent_overall_perf'] == 'Successful Performer')
        ev = sum(1 for e in team if e['talent_overall_perf'] == 'Evolving Performer')
        lo = sum(1 for e in team if e['talent_overall_perf'] == 'Low Performer')
        lines.append(f"| {mgr} | {len(team)} | {hi} | {su} | {ev} | {lo} |")

    lines.append("")

    # Overall performance distribution
    lines.append("## Performance Distribution")
    lines.append("")

    perf_counts = defaultdict(int)
    for emp in all_employees:
        perf_counts[emp['talent_overall_perf'] or 'Not Assessed'] += 1

    total = len(all_employees)
    for perf in ['High Impact Performer', 'Successful Performer', 'Evolving Performer', 'Low Performer']:
        count = perf_counts.get(perf, 0)
        pct = (count / total) * 100 if total else 0
        lines.append(f"- **{perf}**: {count} ({pct:.1f}%)")
    lines.append("")

    # What vs How matrix
    lines.append("## Performance Matrix (What × How)")
    lines.append("")
    lines.append("| What \\ How | Surpasses | Meets | Meets Some | Does Not Meet |")
    lines.append("|------------|-----------|-------|------------|---------------|")

    what_how = defaultdict(lambda: defaultdict(int))
    for emp in all_employees:
        w = emp['talent_perf_what'] or 'Unknown'
        h = emp['talent_perf_how'] or 'Unknown'
        what_how[w][h] += 1

    for what in ['Surpasses Expectations', 'Meets Expectations', 'Meets Some Expectations', 'Does Not Meet Expectations']:
        row = [what]
        for how in ['Surpasses Expectations', 'Meets Expectations', 'Meets Some Expectations', 'Does Not Meet Expectations']:
            row.append(str(what_how[what][how]))
        lines.append(f"| {' | '.join(row)} |")
    lines.append("")

    # Geographic distribution
    lines.append("## Geographic Distribution")
    lines.append("")

    countries = defaultdict(int)
    regions = defaultdict(int)
    for emp in all_employees:
        countries[emp['country'] or 'Unknown'] += 1
        regions[emp['region'] or 'Unknown'] += 1

    lines.append("### By Region")
    for region, count in sorted(regions.items(), key=lambda x: -x[1]):
        pct = (count / total) * 100
        lines.append(f"- **{region}**: {count} ({pct:.1f}%)")
    lines.append("")

    lines.append("### By Country")
    for country, count in sorted(countries.items(), key=lambda x: -x[1]):
        lines.append(f"- {country}: {count}")
    lines.append("")

    # Role distribution
    lines.append("## Role Distribution")
    lines.append("")

    roles = defaultdict(int)
    levels = defaultdict(int)
    for emp in all_employees:
        roles[emp['current_job_profile'] or 'Unknown'] += 1
        levels[emp['management_level'] or 'Unknown'] += 1

    lines.append("### By Level")
    for level, count in sorted(levels.items(), key=lambda x: -x[1]):
        lines.append(f"- {level}: {count}")
    lines.append("")

    lines.append("### By Job Profile")
    for role, count in sorted(roles.items(), key=lambda x: -x[1]):
        lines.append(f"- {role}: {count}")
    lines.append("")

    # Movement readiness
    lines.append("## Movement Readiness")
    lines.append("")

    readiness = defaultdict(int)
    for emp in all_employees:
        readiness[emp['talent_movement_readiness'] or 'Not Assessed'] += 1

    for status, count in sorted(readiness.items(), key=lambda x: -x[1]):
        pct = (count / total) * 100
        lines.append(f"- **{status}**: {count} ({pct:.1f}%)")
    lines.append("")

    # Agility assessment
    lines.append("## Future Talent Indicators (Agility)")
    lines.append("")

    growth = defaultdict(int)
    change = defaultdict(int)
    for emp in all_employees:
        growth[emp['talent_growth_agility'] or 'Unknown'] += 1
        change[emp['talent_change_agility'] or 'Unknown'] += 1

    lines.append("### Growth Agility")
    for g, count in sorted(growth.items(), key=lambda x: -x[1]):
        lines.append(f"- {g}: {count}")
    lines.append("")

    lines.append("### Change Agility")
    for c, count in sorted(change.items(), key=lambda x: -x[1]):
        lines.append(f"- {c}: {count}")
    lines.append("")

    # Promotion candidates
    promo_candidates = [e for e in all_employees if e['talent_promo_job_profile']]
    if promo_candidates:
        lines.append("## Promotion Candidates")
        lines.append("")
        lines.append(f"**{len(promo_candidates)}** employees being considered for promotion:")
        lines.append("")
        for emp in promo_candidates:
            lines.append(f"- **{emp['associate']}** ({emp['current_job_profile']}) → {emp['talent_promo_job_profile']}")
        lines.append("")

    # Mentoring network
    lines.append("## Mentoring Network")
    lines.append("")

    mentors = [e for e in all_employees if e['talent_mentor']]
    mentees = [e for e in all_employees if e['talent_mentees']]

    lines.append(f"- **{len(mentors)}** employees have assigned mentors")
    lines.append(f"- **{len(mentees)}** employees are mentoring others")
    lines.append("")

    # Tenet patterns
    lines.append("## Tenet Analysis")
    lines.append("")

    strength_counts = defaultdict(int)
    improvement_counts = defaultdict(int)

    for emp in all_employees:
        for s in parse_tenets(emp['talent_tenets_strengths']):
            strength_counts[s] += 1
        for i in parse_tenets(emp['talent_tenets_improvements']):
            improvement_counts[i] += 1

    if strength_counts:
        lines.append("### Most Common Strengths")
        for tenet, count in sorted(strength_counts.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"- {tenet}: {count}")
        lines.append("")

    if improvement_counts:
        lines.append("### Most Common Areas for Improvement")
        for tenet, count in sorted(improvement_counts.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"- {tenet}: {count}")
        lines.append("")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Export ratings.db to NotebookLM-compatible markdown files')
    parser.add_argument('--db', default='ratings.db', help='Path to ratings.db (default: ratings.db)')
    parser.add_argument('--output-dir', default=os.path.expanduser('~/tmp/notebooklm-export'),
                        help='Output directory (default: ~/tmp/notebooklm-export)')
    args = parser.parse_args()

    db_path = args.db
    output_dir = args.output_dir

    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return 1

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Get data
    employees = get_employees(db_path)
    settings = get_bonus_settings(db_path)

    if not employees:
        print("No employees found in database")
        return 1

    # Group by manager
    by_manager = defaultdict(list)
    for emp in employees:
        by_manager[emp['supervisory_organization']].append(emp)

    # Generate team files
    for manager, team in by_manager.items():
        filename = f"team-{manager.lower().replace(' ', '-')}.md"
        filepath = os.path.join(output_dir, filename)
        content = generate_team_file(manager, team)
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Created: {filepath}")

    # Generate summary file
    summary_path = os.path.join(output_dir, "00-organization-summary.md")
    content = generate_summary_file(employees, settings)
    with open(summary_path, 'w') as f:
        f.write(content)
    print(f"Created: {summary_path}")

    # Generate all-in-one file (for single-document use)
    all_in_one_path = os.path.join(output_dir, "complete-team-data.md")
    with open(all_in_one_path, 'w') as f:
        f.write(content)
        f.write("\n\n---\n\n")
        for manager, team in sorted(by_manager.items()):
            f.write(generate_team_file(manager, team))
            f.write("\n\n---\n\n")
    print(f"Created: {all_in_one_path}")

    print(f"\nDone! {len(by_manager) + 2} files created in {output_dir}")
    return 0


if __name__ == '__main__':
    exit(main())
