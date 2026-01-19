---
description: Review commits against project rules and talent calibration spec
allowed-args: "[commit-range]"
---

Use the commit-reviewer subagent to analyze commits with full project context.

## Commit Range

- No argument: reviews last commit (`HEAD~1..HEAD`)
- `HEAD~3`: reviews last 3 commits
- `origin/main..HEAD`: reviews all unpushed commits
- Any valid git revision range

## Project-Specific Review

This reviewer has full context of:

1. **AGENTS.md** — Critical rules, architecture constraints, domain knowledge
2. **docs/SPEC-talent-calibration.md** — Talent calibration extension specification
3. **README.md** — User-facing expectations

### Privacy & Architecture Checks

- **Privacy violations**: Real data, sensitive logging, database commits
- **Architecture breaks**: Cloud dependencies, stored bonuses, auth additions
- **Preserved field handling**: Manager-entered data that must survive re-imports

### Talent Calibration Spec Compliance

When changes touch talent calibration features, verify against the spec:

- **Derivation logic** (Spec §7.1-7.2): What + How → Overall Performance matrix; both agility ratings "Always" → Future Talent
- **Column mappings** (Spec §5.3): `TALENT_COLUMN_MAP` matches spec exactly
- **Field preservation** (Spec §5.2): Talent manager-inputs preserved on re-import (different rules than bonus cycle)
- **Enum values** (Spec §9): Performance What/How options, Overall ratings, agility options, movement readiness
- **UI structure** (Spec §6): Calibrate page layout, Export page, Dashboard cross-cycle view

### Sample Data & Demo Mode Sync

- **Sample data scripts** (Spec §13): Model changes require updates to:
  - `scripts/create_demo_templates.py` — Pre-built demo databases
  - `scripts/create_sample_data.py` — Bonus XLSX generator
  - `scripts/create_sample_talent_data.py` — Talent XLSX generator (NEW)
  - `scripts/populate_sample_ratings.py` — Rating/talent field populator
- **Demo mode** (Spec §14): Templates need talent fields, new pages need demo warning banners

### Domain Logic

- **ID usage**: Uses `associate_id`, not employee names (names can duplicate)
- **Rating scale**: 0-200% range, 100% = baseline (met expectations)
- **Split curve**: Upside exponent 1.35 (≥100%), downside exponent 1.9 (<100%)
- **Currency/bonus logic**: Normalization guarantees `sum(final_bonuses) == sum(bonus_targets)`

## Standard Review Areas

- Commit hygiene (message quality, atomic commits, git story)
- Security vulnerabilities and risks
- Performance concerns and optimization opportunities
- Documentation completeness (README vs AGENTS.md separation)
- Test coverage gaps (must use conftest.py fixtures)
- Similar code elsewhere needing same changes

If commits are unpushed, recommend specific fixes (amend, split, squash).

Summarize findings grouped by severity (Critical > Warnings > Suggestions).

If there are no significant issues, say so briefly—don't manufacture problems.
