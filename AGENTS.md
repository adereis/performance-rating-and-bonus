# Developer Guide

Instructions for AI agents and human developers working on this codebase.

---

## Quick Reference

| File | Purpose |
|------|---------|
| `app.py` | Flask routes, API endpoints, business logic |
| `models.py` | SQLAlchemy models: Employee, Period, RatingSnapshot, BonusSettings |
| `xlsx_utils.py` | Workday XLSX parsing, column detection, spreadsheet type detection |
| `demo_mode.py` | Session isolation for demo deployment |
| `tests/conftest.py` | Shared pytest fixtures (always use these) |

**Never commit**: `ratings.db`, `real-*.xlsx`, `sample-data-*.xlsx`

---

## Critical Rules

### Privacy (Non-Negotiable)
- ❌ **NEVER** commit `ratings.db`, real Workday exports, or actual employee data
- ❌ **NEVER** log sensitive info (names, salaries, ratings)
- ❌ **NEVER** add telemetry or external API calls
- ✅ Only commit: `sample-data-*.xlsx`, test fixtures, generated data

### Architecture Constraints
- **Local-first**: SQLite only, no cloud dependencies, no authentication
- **Ephemeral bonuses**: Never store calculated bonuses in database
- **Preserve ratings**: Manager-entered fields survive Workday re-imports
- **Fixed pool**: Normalization guarantees `sum(final_bonuses) == sum(bonus_targets)`

### Code Patterns
- **Always use IDs, not names**: `associate_id` is the unique key (names can duplicate)
- **2-second auto-save debounce**: Never break this pattern (rate.html)
- **API responses**: `{"success": bool, "data/error": ...}`
- **Frontend**: Vanilla JS, Chart.js, Bootstrap CSS, `data-employee-id` attributes

---

## Domain Knowledge

### Terminology (Important!)
- **Performance Rating** (UI term): The 0-200% rating entered by managers. Database field: `performance_rating_percent`.
- **Overall Performance** (UI term): The talent calibration result (High Impact / Successful / Evolving / Low Performer). Derived from What + How assessments.
- **Performance Rating System**: The product name (not a rating type).

### Rating Philosophy
- **100% = met expectations** (baseline, not average)
- **90-110%** = solid performer range (most employees)
- **130%+** = exceptional (rare)
- Scale: 0-200% (enforced by validation)

### Bonus Calculation
- **Split curve**: Upside exponent 1.35 (≥100%), downside exponent 1.9 (<100%)
- **Budget override**: Proportional scaling of entire pool (`BonusSettings.budget_override`)
- **Multi-team**: Auto-detected when `len(unique_orgs) > 1`, shows org-level vs team-level

### Currency Handling
- All calculations use **manager's currency** (auto-detected from XLSX headers like "(AUD)")
- **Fallback logic**: `bonus_target_manager_currency OR bonus_target_local_currency`
  - Domestic employees (same currency as manager): converted column is NULL → uses local column
  - International employees: converted column has value → uses it directly
- `CURRENCY_FORMATS` dict in app.py handles symbol/position per currency

### Workday Import

**Spreadsheet Type Detection**: `detect_spreadsheet_type()` in xlsx_utils.py auto-detects bonus vs talent files based on column markers.

**Bonus files** (required columns): `Associate`, `Associate ID`, `Supervisory Organization`, `Current Job Profile`, `Currency`, `Annual Bonus Target Percent`, `Bonus Target - Local Currency`

**Talent files** (markers): `Performance: What`, `Performance: How`, `Future Talent`, `Movement Readiness`

Manager name parsed from: `"Supervisory Organization (Manager Name)"` → extracts "Manager Name"

**Preserved on re-import** (manager-entered):
- Bonus cycle: `performance_rating`, `justification`, `mentors`, `mentees`, `ai_related_activities`, tenets
- Talent cycle: `talent_perf_what`, `talent_perf_how`, `talent_growth_agility`, `talent_change_agility`, `talent_movement_readiness`, `talent_proposed_actions`, `talent_mentor`, `talent_mentees`, `talent_tenets_*`

**Overwritten on re-import** (from Workday): salary, bonus targets, org structure, management_level

### Talent Calibration

**Routes**: `/calibrate` (UI), `/api/calibrate` (POST), `/api/calibrate/status` (GET), `/export/talent` (GET)

**Derivation functions** (in models.py):
- `derive_overall_performance(what, how)` → "High Impact Performer" | "Successful Performer" | "Evolving Performer" | "Low Performer"
- `derive_future_talent(growth, change)` → True if both contain "Always"
- `get_cross_cycle_alignment(bonus_pct, talent_overall)` → "aligned" | "review" | "incomplete"

**Manager detection**: Uses `management_level` field (e.g., "Manager", "Director") in addition to supervisory org lookup. See `has_direct_reports()` in app.py.

**Tenets integration**: Tenets and mentor/mentees embedded in "Proposed Talent Actions" on export using bracket markers (`[Strengths: ...]`, `[Mentor: ...]`, `[Mentees: ...]`), parsed back on import via `parse_proposed_actions_metadata()`.

**Cross-cycle alignment** (Spec §7.4): Dashboard shows alignment between Performance Rating (0-200%) and Overall Performance. Alignment ranges: High Impact = 120-200%, Successful = 90-119%, Evolving = 70-89%, Low = 0-69%.

---

## Development Workflow

**Git**: Commit locally as you work; only push when user explicitly requests.

**Tests**: `python3 -m pytest tests/ -v` — use fixtures from `conftest.py` (never touch production db).

### When Modifying

**New API endpoint**: Add to `app.py`, follow try/except pattern, add test to `test_api.py`

**New database field**: Update `models.py`, handle migration (delete db + re-import for dev), update `convert_xlsx.py` if from Workday

**Bonus algorithm changes**: Update `docs/BONUS_CALCULATION_README.md`, verify pool normalization in tests

---

## Key Gotchas

**Dual field naming**: DB uses `snake_case`, `to_dict()` returns `Title Case` to match Workday columns. Use `'Supervisory Organization'` for dict keys, `supervisory_organization` for ORM.

**Demo mode** (`DEMO_MODE=true`): Session-isolated databases, template dbs generated at Docker build time, no imports allowed.

**Chart.js 4.x segment callbacks**: Use `segCtx.p0DataIndex` (flat), not `segCtx.p0.dataIndex` (undefined).

---

## Don'ts

- ❌ Add cloud dependencies or authentication
- ❌ Store bonus calculations in database
- ❌ Change Workday column names without backward compatibility
- ❌ Remove pool normalization guarantee
- ❌ Change rating scale without updating all validation
- ❌ Make manager-entered fields `nullable=False`
- ❌ Duplicate README content here (README = users, AGENTS = developers)
