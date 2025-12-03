# Project TODO List

This file tracks future enhancements and feature requests for the Performance Rating System.

---

## Backlog Features

### Save Multiple Parameter Configurations
**Priority:** Low
**Status:** Not Started
**Description:** Allow saving multiple bonus calculation parameter sets (e.g., "Conservative", "Aggressive", "Balanced") for quick switching.

**Implementation Notes:**
- Create `bonus_configs.json` or database table
- Store named configs: `{"name": "Conservative", "upside": 1.1, "downside": 2.0}`
- Add dropdown in bonus calculation page to select config
- Include "Save Current" and "Load" buttons

---

### Bulk Edit Capabilities
**Priority:** Low
**Status:** Not Started
**Description:** Allow bulk operations like "set all unrated to 100%" or "copy justifications from last period".

**Implementation Notes:**
- Add "Bulk Actions" dropdown in rate.html
- Options: "Set all unrated to 100%", "Clear all ratings", "Apply template justification"
- Confirmation dialog before applying
- Update multiple records via `/api/bulk_rate` endpoint

---

### Read-Only Sharing Mode for Calibration Sessions
**Priority:** Low
**Status:** Not Started
**Description:** Generate read-only view links for calibration sessions with other managers (no database write access).

**Implementation Notes:**
- Add "Generate Share Link" button
- Create unique token/URL: `/calibration/view/<token>`
- Show ratings and analytics, hide edit capabilities
- Optional: password protection
- Token expiration (24-48 hours)

---

### Database Migration System
**Priority:** Low
**Status:** Not Started
**Description:** Implement Alembic or similar for managing database schema changes across versions.

**Implementation Notes:**
- Install Alembic: `pip install alembic`
- Initialize: `alembic init migrations`
- Create migration for current schema as baseline
- Document migration workflow in README
- Update AGENTS.md with migration patterns

---

### API Documentation
**Priority:** Low
**Status:** Not Started
**Description:** Create Swagger/OpenAPI documentation for all API endpoints.

**Implementation Notes:**
- Use Flask-RESTX or flask-swagger-ui
- Document all `/api/*` endpoints
- Include request/response schemas
- Add examples for each endpoint
- Host at `/api/docs`

---

## Completed Features

### Historical Data Preservation
**Completed:** 2025-12-03
**Description:** Preserve rating data across evaluation periods to provide historical context and trend visibility when evaluating team members.

**Implementation:**
- Database: `RatingPeriod` and `EmployeeSnapshot` tables for archival storage
- Archive Period: Dashboard button creates period snapshot, clears current ratings
- Employee History: Modal "History" tab shows all past ratings with expandable details
- Trend Visualization: Chart.js line graph with trend indicator (improving/stable/declining)
- Gap Handling: Dashed lines bridge periods with partial/missing data
- Period Comparison: Analytics page dropdown to compare current vs historical periods
- Historical Import: Import old Workday exports as archived periods (parses Notes field)
- API endpoints: `/api/periods`, `/api/period-comparison/<id>`, `/api/employee/<id>/history`

---

### Export Functionality (CSV and Excel)
**Completed:** 2025-11-28
**Description:** Browser-download export for ratings and bonus calculations in CSV and Excel formats.

**Implementation:**
- `/export` page with data preview and sortable table
- `/export/csv` endpoint for CSV download
- `/export/xlsx` endpoint for Excel download
- Uses Flask's `send_file()` with in-memory generation
- Includes employee name, bonus %, and formatted description
- Copy-to-clipboard for individual descriptions

---

### Multi-Team Bonus Calculation
**Completed:** 2025-11-27
**Description:** Tabbed interface showing organization-level vs team-level bonus calculations for multi-team scenarios.

**Implementation:**
- Auto-detects multi-team scenario by counting unique supervisory organizations
- Tab 1: Overview (organization-level calculation)
- Tab 2: Team Comparison (team-level vs org-level normalization)
- Tab 3: Detailed Breakdown (per-employee side-by-side comparison)
- Shows budget flow between teams (gains/losses from normalization)

---

### Multi-Team Analytics
**Completed:** 2025-11-27
**Description:** Per-team calibration views and cross-team comparison for organizations with multiple teams.

**Implementation:**
- Three tabs: Organization Overview, Per-Team Calibration, Team Comparison Matrix
- Auto-generated insights: rating variance, calibration health, high-variance teams
- Helps identify calibration inconsistencies across teams

---

### Employee Modal Detail View
**Completed:** 2025-11-28
**Description:** Clickable employee names throughout the app that open a modal with full details.

**Implementation:**
- Click any employee name to open modal
- Shows all employee info, rating, justification, tenets
- Inline editing within modal with auto-save
- Unsaved changes warning on close

---

### Employee Filtering for Calibration
**Completed:** 2025-11-28
**Description:** Filter employees on rate page for focused calibration sessions.

**Implementation:**
- Filter by: All, Rated, Unrated, Incomplete Info
- Exclude specific employees from view
- Supports calibration calls focused on subsets of team

---

### Associate ID Refactoring
**Completed:** 2025-11-29
**Description:** System-wide refactor to use Associate ID instead of names for employee identification.

**Implementation:**
- All API endpoints use `associate_id` parameter
- Frontend uses `data-employee-id` attributes
- Handles duplicate names correctly
- Filter system uses `exclude_ids` parameter

---

### Budget Override
**Completed:** 2025-11-26
**Description:** Allow managers to adjust total bonus pool with inline editing.

**Implementation:**
- Inline editable field in summary stats
- Proportional scaling: all bonuses scale by `adjusted_pool / base_pool`
- Persisted in `BonusSettings` table
- Tooltip explains functionality

---

### Team Tenets / Leadership Principles Evaluation
**Completed:** 2025-11-26
**Description:** Configuration-driven system for evaluating employees against team-specific tenets.

**Implementation:**
- Database fields: `tenets_strengths`, `tenets_improvements` (JSON arrays)
- Configuration file: `tenets.json` (team-specific, gitignored)
- UI: Checkbox-based selection with tooltips
- Validation: 3 strengths required, 2-3 improvements allowed
- Analytics: Diverging butterfly chart visualization
- Comprehensive test coverage in `tests/test_tenets.py`

---

## Won't Implement

### Import Compa-Ratio Data from Workday
**Status:** Removed from scope
**Reason:** See AGENTS.md "Domain Knowledge" section for full rationale.

Key issues:
- Workday export format is complex and inconsistent
- Per-country CR distortions due to outdated salary bands
- Would require country-specific adjustment factors
- Adds complexity for marginal benefit
- Bonus algorithm focuses on performance, not salary equity

The feature was prototyped and then removed (commit `a3f545d`) after discovering these issues.

---

## Notes

- Prioritize features based on team feedback and usage patterns
- All new features should include comprehensive tests
- Update README.md and AGENTS.md when implementing new features
- Maintain backward compatibility with existing Workday exports
