# Developer Guide

Instructions for AI agents and human developers working on this codebase.

---

## Quick Reference

| File | Purpose |
|------|---------|
| `app.py` | Application factory (`create_app()`), app-level filters/context processor/request hooks/error handlers, blueprint registration. **No routes live here** — they're in `blueprints/`. |
| `config.py` | `Config` class: env-driven settings; fails fast if `SECRET_KEY` unset when `FLASK_ENV=production` |
| `blueprints/` | Flask blueprints, one per route group: `core` (/, /health, /demo/*), `rate`, `calibrate`, `bonus`, `analytics`, `export`, `import_`, `history`. Thin handlers; logic lives in `services/`. Blueprints never `import app` (would break `python app.py`); they read config via `demo_mode`/`models`/`services`. |
| `models.py` | SQLAlchemy models: Employee, Period, RatingSnapshot, BonusSettings |
| `migrations.py` | Database migrations: column renames, additions, placeholder cleanup |
| `xlsx_utils.py` | Workday XLSX parsing, column detection, spreadsheet type detection |
| `demo_mode.py` | Session isolation for demo deployment |
| `services/employee_utils.py` | Constants, status checks, formatting (pure functions, no Flask/DB) |
| `services/analytics.py` | Analytics sub-computations: ratings, tenets, talent, tenure, inconsistencies |
| `services/export.py` | Export data prep, XLSX helpers, snapshot builders, context markdown |
| `services/bonus.py` | Bonus curve calculation, calibration distribution, mentorship stats |
| `services/import_handler.py` | Import field comparison, update helpers, apply functions |
| `services/db_helpers.py` | Database access, filtering, settings, tenets config |
| `static/css/base.css` | Base stylesheet (extracted from base.html) |
| `static/js/placeholder.js` | Shared placeholder detection (rate + calibrate) |
| `static/js/employee-index.js` | Shared sidebar navigation (rate + calibrate) |
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
- **Employee data entry exists in TWO places** (keep them in sync!):
  1. `templates/rate_card.html` - Detailed employee card in /rate page
  2. `templates/base.html` - Employee detail modal (click any employee name). Contains `renderEmployeeModal()`, `saveEmployeeModal()`, and `autoSaveAndCloseModal()` functions

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
- **Special case overrides**: Set `bonus_override_percent` to bypass curve calculation (e.g., pro-rata leave, retention). This avoids penalizing employees with artificially low performance ratings when their circumstances don't reflect actual performance. Uses Option B pool handling: override bonuses come from the same pool, unused portion redistributed to other employees. Employees with override are excluded from analytics distributions. **Workflow completion**: override employees count as "complete" in the sidebar (green dot with orange ring) regardless of rating/justification/tenets — but those fields remain editable since partial-quarter employees may still receive full evaluations. Export marker: `[Override: 50%, Paternity leave Apr-Sep]` (reason optional)

### Currency Handling
- All calculations use **manager's currency** (auto-detected from XLSX headers like "(AUD)")
- **Fallback logic**: `bonus_target_manager_currency OR bonus_target_local_currency`
  - Domestic employees (same currency as manager): converted column is NULL → uses local column
  - International employees: converted column has value → uses it directly
- `CURRENCY_FORMATS` dict in app.py handles symbol/position per currency

### Workday Import

**Spreadsheet Type Detection**: `detect_spreadsheet_type()` in xlsx_utils.py auto-detects bonus vs talent files based on column markers.

**Format Support** (auto-detected):
- **Legacy format**: Integer percentages (5 = 5%), columns like `Supervisory Organization`, `Current Job Profile`
- **Report format**: Decimal percentages (0.05 = 5%), columns like `Direct Manager`, `Job Title`, `Management Level`

**Proper format indicators**: Row 1 contains "Compensation Review: Bonus - CYxx Qx", decimal values in percentage columns.

**New fields (Report format)**: `management_level`, `country`, `hire_date`, `time_in_job_profile`, `last_perf_review_name`, `last_perf_review_rating`

**Bonus files** (required columns): `Associate`, `Associate ID`, `Supervisory Organization` (or `Direct Manager`), `Current Job Profile` (or `Job Title`), `Currency`, `Annual Bonus Target Percent`, `Bonus Target - Local Currency`

**Talent files** (markers): `Performance: What`, `Performance: How`, `Future Talent`, `Movement Readiness`

Manager name parsed from: `"Supervisory Organization (Manager Name)"` or `"Direct Manager"` column → extracts manager name.

**Preserved on re-import** (manager-entered):
- Bonus cycle: `performance_rating`, `justification`, `mentors`, `mentees`, tenets, `bonus_override_percent`, `special_case_notes`
- Talent cycle: `talent_perf_what`, `talent_perf_how`, `talent_growth_agility`, `talent_change_agility`, `talent_movement_readiness`, `talent_proposed_actions`, `talent_mentor`, `talent_mentees`, `talent_tenets_*`

**Overwritten on re-import** (from Workday): salary, bonus targets, org structure, management_level, country, tenure fields

**Notes Field Format** (canonical bracketed format for Workday round-tripping):
- `[Performance Rating: X%]`
- `[Override: X%, reason]` (special cases like pro-rata leave)
- `[Strengths: ...]` / `[Improvements: ...]`
- `[Mentor: ...]` / `[Mentees: ...]`
- `Justification:` (section header, allows multi-line text)

Parser: `notes_parser.py` — `parse_notes_field()` extracts, `format_notes_field()` serializes. Exports use this format in the Notes column; the separate Description column is human-readable (no brackets).

### Talent Calibration

**Routes**: `/calibrate` (UI), `/api/calibrate` (POST), `/api/calibrate/status` (GET), `/export/talent` (GET)

**Derivation functions** (in models.py):
- `derive_overall_performance(what, how)` → "High Impact Performer" | "Successful Performer" | "Evolving Performer" | "Low Performer"
- `derive_future_talent(growth, change)` → True if both contain "Always"
- `get_cross_cycle_alignment(bonus_pct, talent_overall)` → "aligned" | "review" | "incomplete"

**Manager detection**: Uses `management_level` field (e.g., "Manager", "Director") in addition to supervisory org lookup. See `has_direct_reports()` in app.py.

**Tenets integration**: Tenets and mentor/mentees embedded in "Proposed Talent Actions" on export using bracket markers (`[Strengths: ...]`, `[Mentor: ...]`, `[Mentees: ...]`), parsed back on import via `parse_proposed_actions_metadata()`.

**Cross-cycle alignment** (Spec §7.4): Dashboard shows alignment between Performance Rating (0-200%) and Overall Performance. Alignment ranges: High Impact = 120-200%, Successful = 90-119%, Evolving = 70-89%, Low = 0-69%.

### Tenure Analytics

Built into `/analytics` page. Parses Workday tenure strings (e.g., "2 years, 3 months") via `parse_tenure_to_months()`.

**Metrics**: Length of Service distribution, Time in Job Profile distribution, averages by role.

**Performance quadrants** (based on time in role + performance):
- `promotion_candidate`: High Impact + 2+ years in role → Career Check-in needed
- `rising_star`: High Impact + < 2 years → High Performer
- `solid_contributor`: Successful Performer
- `needs_attention`: Low/Evolving + 6+ months → Attention needed
- `developing`: < 6 months in role → Still Ramping

**Tenure-based inconsistencies** (flagged in calibration review):
- New hire (< 6 months) rated Low/Evolving
- Ready Now but < 2 years in role
- 5+ years in role but "Continue growing"
- High Impact + 3+ years but no movement set

### Prior Cycle Bonus Detection

**Location**: Analytics page, inconsistencies card

Compares calculated bonus allocation against `last_bonus_allocation_percent` from Workday. Flags employees where the delta exceeds ±15 percentage points. Uses `calculate_bonus_for_employees()` with standard curve parameters.

- **`bonus_decrease_from_prior`**: Calculated bonus >15pp lower than prior cycle
- **`bonus_increase_from_prior`**: Calculated bonus >15pp higher than prior cycle
- Special case employees (bonus override) are excluded from comparison

### Expandable Analytics Lists

**Pattern**: Lists with >5 items show first 5, then a clickable "... and X more" toggle.

**CSS classes**: `.expandable-item` (hidden by default), `.expanded` (shown), `.expand-toggle` (clickable link)

**Usage in templates**: Add `class="{% if loop.index > 5 %}expandable-item expandable-{name}{% endif %}"` to `<li>` elements, with a toggle link using `data-target="expandable-{name}"`. JS handler in `analytics.html` toggles the `.expanded` class.

**Applied to**: Tenet mismatch, prior cycle bonus decrease/increase lists.

### Organization Snapshot Export

**Routes**: `/export/snapshot/xlsx`, `/export/snapshot/csv`

**Purpose**: Self-documenting export for AI/analyst consumption (e.g., NotebookLM, Claude).

**XLSX sheets**:
- `_README`: Markdown document with domain knowledge, rating philosophy, algorithms, tenet definitions (single cell, AI-optimized)
- `employees`: Core identity, compensation, manager info
- `bonus_cycle`: Performance ratings, justifications, calculated bonuses
- `talent_cycle`: Calibration data, agility, movement, promotions
- `history`: Historical rating snapshots by period

**CSV ZIP files**: Same structure but `README.md` file instead of `_README` sheet

**Implementation**: `build_context_markdown(tenets_config, demo_mode)` in app.py generates the markdown content. Tenet definitions are grouped by category inline (not a separate sheet).

### Export Sync Detection (Bonus Export Page)

Determines which employees have pending changes for Workday on the `/export` page. **Two-tier architecture**:

**Tier 1 — Tool Additions Modified** (`tool_additions_modified`):
Any of 7 tracked fields differ from their `_original` value imported from Workday:
- `performance_rating_percent` vs `performance_rating_percent_original`
- `justification` vs `justification_original`
- `mentor` vs `mentor_original`
- `mentees` vs `mentees_original`
- `tenets_strengths` vs `tenets_strengths_original`
- `tenets_improvements` vs `tenets_improvements_original`
- `bonus_override_percent` vs `bonus_override_percent_original`

Two comparison functions in `export_page()` (app.py):
- `is_field_modified()`: Conservative — returns False if `_original` is None (used for justification)
- `needs_sync_to_workday()`: Aggressive — returns True if content exists but `_original` is None (used for tool-generated fields like tenets, mentor)

Override uses `is not None` comparison (not `bool()`) because 0.0 is a valid override value.

**Tier 2 — Bonus Allocation Differs** (`bonus_allocation_differs`):
Compares `int(calculated_bonus_percent) != round(proposed_percent_of_target_bonus)`. True when Workday has no value (new sync needed).

**Combined**: `needs_sync = tool_additions_modified OR bonus_allocation_differs`

**Template rendering rules** (critical — do NOT regress):
1. **Tool Additions box**: Render ONLY when `tool_additions_modified` is true. ⚠️ Never gate on `tool_additions_text` (non-empty) — that shows the box for every employee with any content.
2. **Description content** (`.description-content`): Hidden by JS when "Show pending only" is active and `tool_additions_modified` is false (avoids showing unchanged notes for bonus-only diffs).
3. **Bonus ⟳ badge**: Shown next to Bonus % when `bonus_allocation_differs` is true.
4. **Per-field ⟳ badges**: Inside the Tool Additions box, each modified field gets a `field-sync-badge`.

**"Show pending only" + "Hide bonus changes" interaction** (JS in `applyBonusFilters()`):
- When "Hide bonus changes" is checked, `effectiveNeedsSync = toolSyncModified` (ignores bonus diffs for row visibility).
- The status bar count updates dynamically to reflect the effective pending count.
- This means: all three checkboxes checked + fresh import = **empty list** (expected).

**Data attributes on `<tr>` rows** (required for JS filtering):
- `data-needs-sync` — server-computed combined flag
- `data-tool-sync` — tool additions modified
- `data-bonus-differs` — bonus allocation differs

**Regression tests**: `tests/test_export_sync.py` — covers fresh import invariants, per-field modification detection, bonus comparison, template rendering gates, and description content visibility.

---

## Development Workflow

**Git**: Commit locally as you work; only push when user explicitly requests.

**Tests**: `python3 -m pytest tests/ -v` — use fixtures from `conftest.py` (never touch production db).

**Interactive / browser testing**: the pytest suite is blind to rendering, CSS, and
client-side JS (where some of the worst historical bugs lived — the modal data-wipe,
the tenets crash). After UI changes, follow `docs/INTERACTIVE_TESTING.md` to drive the
app through headless Chrome (smoke tour, modal, bonus chart, exclude-managers filter,
demo-mode session isolation). It also documents the environment gotchas (blocked
`sleep`, kill-by-port not `pkill`, Jinja template caching → restart on `.html` edits).

**Blueprint split (done)**: `docs/REFACTOR_APP_SPLIT.md` was the executable plan;
all phases are complete. `app.py` went from a 4,449-line god-module to a ~290-line
application factory; the 32 routes now live in eight `blueprints/` modules and the
heavy logic in `services/`. The endpoint-renaming gotcha is resolved (all endpoints
are now namespaced, e.g. `rate.rate_page`, `core.index`) — keep that in mind when
adding `url_for(...)`/`request.endpoint` references.

### When Modifying

**New API endpoint**: Add it to the relevant `blueprints/<group>.py` (decorate with
that blueprint, e.g. `@rate_bp.route(...)`), follow the try/except pattern, keep logic
in `services/`, and add a test to `test_api.py`. `url_for`/`request.endpoint` use the
namespaced name (`<blueprint>.<func>`).

**New database field**: Update `models.py`, add to `_migrate_add_new_columns()`, update `convert_xlsx.py` if from Workday.

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
