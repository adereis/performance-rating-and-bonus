# Talent Calibration Specification

**Version:** 2.0 (AI-Optimized)
**Status:** Approved for Implementation

---

## 1. Overview

Extend the Performance Rating & Bonus tool to support Talent Calibration cycles alongside Bonus cycles.

### Design Decisions (Resolved)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Employee matching on talent import | Create new records if `associate_id` not found | Supports employees not in bonus cycle |
| Talent analytics | Extend existing `/analytics` page | Single analytics view for both cycles |
| Tenets for talent | Yes, full support (`talent_tenets_strengths/improvements`) | Consistent experience across cycles |
| Period display on dashboard | Show "Current Bonus" and "Current Talent" separately | Clear cycle distinction |
| Historical fields (`talent_last_*`) | Preserve locally across re-imports | Enables year-over-year comparison |
| `Worker` vs `Associate` column | Map both to `associate` field | Single name field |
| Calibrate nav link visibility | Always visible | Show instructional message if no data |
| Management Chain columns (02-07) | Skip | Adds complexity without clear value |
| Calibration Status in UI | Show read-only | Useful context for managers |

---

## 2. Schema Definitions

### 2.1 Employee Model Additions

**File:** `models.py`
**Location:** Add after existing `last_updated` field (around line 85)

```python
# ═══════════════════════════════════════════════════════════════
# EXTENDED IDENTITY (from talent report, nullable)
# ═══════════════════════════════════════════════════════════════
management_level = Column(String)        # "IC 1", "IC 2", ..., "Manager", "Director"
job_category = Column(String)            # From Workday
hire_date = Column(DateTime)             # Date type
length_of_service = Column(String)       # "2 years, 3 months"
time_in_job_profile = Column(String)     # "1 year, 6 months"
region = Column(String)                  # "Americas", "EMEA", "APAC"
country = Column(String)                 # "United States", "Australia"

# ═══════════════════════════════════════════════════════════════
# TALENT: PERFORMANCE ASSESSMENT
# ═══════════════════════════════════════════════════════════════
talent_perf_what = Column(String)        # ENUM: see section 3.1
talent_perf_how = Column(String)         # ENUM: see section 3.2
talent_overall_perf = Column(String)     # DERIVED: see section 4.1
talent_last_overall_perf = Column(String)  # PRESERVED: from Workday historical

# ═══════════════════════════════════════════════════════════════
# TALENT: FUTURE TALENT
# ═══════════════════════════════════════════════════════════════
talent_growth_agility = Column(String)   # ENUM: see section 3.3
talent_change_agility = Column(String)   # ENUM: see section 3.3
talent_identified_future = Column(Boolean)  # DERIVED: see section 4.2
talent_last_identified_future = Column(Boolean)  # PRESERVED

# ═══════════════════════════════════════════════════════════════
# TALENT: MOVEMENT & CAREER
# ═══════════════════════════════════════════════════════════════
talent_movement_readiness = Column(String)  # ENUM: see section 3.4
talent_last_movement_readiness = Column(String)  # PRESERVED
talent_proposed_actions = Column(Text)   # Free-form text

# ═══════════════════════════════════════════════════════════════
# TALENT: PROMOTION
# ═══════════════════════════════════════════════════════════════
talent_promo_job_profile = Column(String)   # "Senior SRE, 1534"
talent_promo_business_need = Column(Text)
talent_promo_role_scope = Column(Text)
talent_promo_readiness = Column(Text)

# ═══════════════════════════════════════════════════════════════
# TALENT: TENETS (parallel to bonus tenets)
# ═══════════════════════════════════════════════════════════════
talent_tenets_strengths = Column(String)     # JSON array of tenet IDs
talent_tenets_improvements = Column(String)  # JSON array of tenet IDs

# ═══════════════════════════════════════════════════════════════
# TALENT: METADATA
# ═══════════════════════════════════════════════════════════════
talent_calibration_status = Column(String)  # Read-only from Workday
talent_last_updated = Column(DateTime)
```

### 2.2 Period Model Addition

**File:** `models.py`
**Location:** Period class

```python
cycle_type = Column(String)  # "bonus" | "talent"
```

### 2.3 RatingSnapshot Model Additions

**File:** `models.py`
**Location:** RatingSnapshot class

```python
snapshot_talent_perf_what = Column(String)
snapshot_talent_perf_how = Column(String)
snapshot_talent_overall_perf = Column(String)
snapshot_talent_growth_agility = Column(String)
snapshot_talent_change_agility = Column(String)
snapshot_talent_movement_readiness = Column(String)
snapshot_talent_proposed_actions = Column(Text)
snapshot_talent_promo_job_profile = Column(String)
snapshot_talent_tenets_strengths = Column(String)
snapshot_talent_tenets_improvements = Column(String)
```

---

## 3. Enum Definitions

### 3.1 Performance: What

| Value | DB String |
|-------|-----------|
| Surpasses | `"Surpasses Expectations"` |
| Meets | `"Meets Expectations"` |
| Meets Some | `"Meets Some Expectations"` |

### 3.2 Performance: How

| Value | DB String |
|-------|-----------|
| Surpasses | `"Surpasses Expectations"` |
| Meets | `"Meets Expectations"` |
| Meets Some | `"Meets Some Expectations"` |
| Does Not Meet | `"Does Not Meet Expectations"` |

### 3.3 Agility (Growth & Change)

| Value | DB String |
|-------|-----------|
| Always | `"Always/Most of the Time"` |
| Sometimes | `"Sometimes"` |

### 3.4 Movement Readiness

| Value | DB String |
|-------|-----------|
| Continue | `"Continue growing in current role"` |
| Ready Promotion | `"Ready Now to be promoted in current role"` |
| Ready Lateral | `"Ready for lateral move"` |

### 3.5 Overall Performance (Derived)

| Value | DB String |
|-------|-----------|
| High Impact | `"High Impact Performer"` |
| Successful | `"Successful Performer"` |
| Evolving | `"Evolving Performer"` |
| Low | `"Low Performer"` |

---

## 4. Derivation Logic

### 4.1 Overall Performance Rating

**Function:** `derive_overall_performance(what: str, how: str) -> str | None`

**Decision Table:**

| What | How | Result |
|------|-----|--------|
| `*` | `Does Not Meet*` | `Low Performer` |
| `*Some*` | `*Some*` | `Low Performer` |
| `Surpasses*` | `Surpasses*` | `High Impact Performer` |
| `Surpasses*` | `Meets Expectations` | `High Impact Performer` |
| `Surpasses*` | `*Some*` | `Successful Performer` |
| `Meets Expectations` | `Surpasses*` | `Successful Performer` |
| `Meets Expectations` | `Meets Expectations` | `Successful Performer` |
| `Meets Expectations` | `*Some*` | `Evolving Performer` |
| `*Some*` | `Meets Expectations` | `Evolving Performer` |
| `*Some*` | `Surpasses*` | `Evolving Performer` |
| (null/empty) | `*` | `None` |
| `*` | (null/empty) | `None` |

**Implementation:**
```python
def derive_overall_performance(what: str | None, how: str | None) -> str | None:
    if not what or not how:
        return None
    w, h = what.lower(), how.lower()
    if 'does not meet' in h:
        return 'Low Performer'
    if 'some' in w and 'some' in h:
        return 'Low Performer'
    if 'surpasses' in w:
        return 'High Impact Performer' if 'surpasses' in h or ('meets' in h and 'some' not in h) else 'Successful Performer'
    if 'meets' in w and 'some' not in w:
        if 'surpasses' in h or ('meets' in h and 'some' not in h):
            return 'Successful Performer'
        return 'Evolving Performer'
    if 'some' in w:
        return 'Evolving Performer'
    return 'Successful Performer'
```

**Test Cases:**
```python
assert derive_overall_performance("Surpasses Expectations", "Surpasses Expectations") == "High Impact Performer"
assert derive_overall_performance("Surpasses Expectations", "Meets Expectations") == "High Impact Performer"
assert derive_overall_performance("Meets Expectations", "Meets Expectations") == "Successful Performer"
assert derive_overall_performance("Meets Expectations", "Meets Some Expectations") == "Evolving Performer"
assert derive_overall_performance("Meets Some Expectations", "Meets Some Expectations") == "Low Performer"
assert derive_overall_performance("Meets Expectations", "Does Not Meet Expectations") == "Low Performer"
assert derive_overall_performance(None, "Meets Expectations") is None
assert derive_overall_performance("", "") is None
```

### 4.2 Future Talent Identification

**Function:** `derive_future_talent(growth: str, change: str) -> bool`

**Rule:** Both agility fields must contain "Always" (case-insensitive).

```python
def derive_future_talent(growth: str | None, change: str | None) -> bool:
    if not growth or not change:
        return False
    return 'always' in growth.lower() and 'always' in change.lower()
```

**Test Cases:**
```python
assert derive_future_talent("Always/Most of the Time", "Always/Most of the Time") == True
assert derive_future_talent("Always/Most of the Time", "Sometimes") == False
assert derive_future_talent("Sometimes", "Always/Most of the Time") == False
assert derive_future_talent("Sometimes", "Sometimes") == False
assert derive_future_talent(None, "Always/Most of the Time") == False
```

---

## 5. Import Logic

### 5.1 Spreadsheet Type Detection

**File:** `xlsx_utils.py`
**Function:** `detect_spreadsheet_type(headers: list[str]) -> str`

```python
TALENT_MARKERS = ['Performance: What', 'Performance: How', 'Future Talent', 'Movement Readiness']
BONUS_MARKERS = ['Bonus Target', 'Annual Bonus Target Percent', 'Current Base Pay', 'Proposed Bonus Amount']

def detect_spreadsheet_type(headers: list[str]) -> str:
    text = ' '.join(str(h) for h in headers if h)
    talent = sum(1 for m in TALENT_MARKERS if m in text)
    bonus = sum(1 for m in BONUS_MARKERS if m in text)
    return 'talent' if talent > bonus else 'bonus'
```

### 5.2 Column Mapping (Talent)

**File:** `xlsx_utils.py`

```python
TALENT_COLUMN_MAP = {
    # Identity (map Worker to associate, same as Associate)
    'Associate ID': 'associate_id',
    'Worker': 'associate',
    'Associate': 'associate',

    # Performance
    'Performance: What': 'talent_perf_what',
    'Performance: How': 'talent_perf_how',
    'Overall Performance Rating': 'talent_overall_perf',
    'Last Talent Assessment Cycle: Overall Performance Rating': 'talent_last_overall_perf',

    # Future Talent
    'Future Talent: Growth Agility': 'talent_growth_agility',
    'Future Talent: Change Agility': 'talent_change_agility',
    'Identified as Future Talent?': 'talent_identified_future',
    'Last Talent Assessment Cycle: Identified as Future Talent?': 'talent_last_identified_future',

    # Movement
    'Movement Readiness': 'talent_movement_readiness',
    'Last Talent Assessment Cycle: Movement Readiness': 'talent_last_movement_readiness',
    'Proposed Talent Actions': 'talent_proposed_actions',

    # Promotion
    'Promotions: Proposed Job Profile & Code': 'talent_promo_job_profile',
    'Promotions: Business Need': 'talent_promo_business_need',
    'Promotions: Expanded Role Scope': 'talent_promo_role_scope',
    'Promotions: Associate Readiness': 'talent_promo_readiness',

    # Context
    'Time in Job Profile': 'time_in_job_profile',
    'Job Profile': 'current_job_profile',
    'Management Level': 'management_level',
    'Job Category': 'job_category',
    'Hire Date': 'hire_date',
    'Length of Service - Worker': 'length_of_service',
    'Region - Location Based': 'region',
    'Country': 'country',

    # Metadata
    'Calibration Status': 'talent_calibration_status',
}
```

### 5.3 Field Preservation Rules

**On Talent Re-import:**

| Category | Behavior |
|----------|----------|
| **OVERWRITE** | Context fields: `hire_date`, `time_in_job_profile`, `length_of_service`, `management_level`, `job_category`, `region`, `country`, `current_job_profile` |
| **OVERWRITE** | Metadata: `talent_calibration_status` |
| **PRESERVE** | Historical: `talent_last_overall_perf`, `talent_last_identified_future`, `talent_last_movement_readiness` |
| **PRESERVE** | Manager inputs: `talent_perf_what`, `talent_perf_how`, `talent_growth_agility`, `talent_change_agility`, `talent_movement_readiness`, `talent_proposed_actions`, all `talent_promo_*`, `talent_tenets_*` |

### 5.4 Employee Matching

**On talent import with `associate_id` not in database:**
1. Create new Employee record
2. Set bonus-related fields to NULL
3. Populate talent fields from import
4. Log: "Created new employee: {associate_id}"

---

## 6. API Endpoints

### 6.1 Save Talent Calibration

**Endpoint:** `POST /api/calibrate`
**File:** `app.py`

**Request:**
```json
{
  "associate_id": "12345",
  "talent_perf_what": "Meets Expectations",
  "talent_perf_how": "Surpasses Expectations",
  "talent_growth_agility": "Always/Most of the Time",
  "talent_change_agility": "Sometimes",
  "talent_movement_readiness": "Continue growing in current role",
  "talent_proposed_actions": "Focus on cross-team collaboration...",
  "talent_tenets_strengths": ["tenet_1", "tenet_3"],
  "talent_tenets_improvements": ["tenet_5"],
  "talent_promo_job_profile": null,
  "talent_promo_business_need": null,
  "talent_promo_role_scope": null,
  "talent_promo_readiness": null
}
```

**Response (success):**
```json
{
  "success": true,
  "data": {
    "talent_overall_perf": "Successful Performer",
    "talent_identified_future": false,
    "talent_last_updated": "2026-01-19T10:30:00Z"
  }
}
```

**Response (error):**
```json
{
  "success": false,
  "error": "Invalid value for talent_perf_what: 'Invalid'. Must be one of: Surpasses Expectations, Meets Expectations, Meets Some Expectations"
}
```

**Validation Rules:**
- `talent_perf_what`: Must match enum 3.1 or be null
- `talent_perf_how`: Must match enum 3.2 or be null
- `talent_growth_agility`: Must match enum 3.3 or be null
- `talent_change_agility`: Must match enum 3.3 or be null
- `talent_movement_readiness`: Must match enum 3.4 or be null
- `talent_tenets_*`: Must be valid tenet IDs from `tenets.json`

### 6.2 Get Calibration Status

**Endpoint:** `GET /api/calibrate/status`

**Response:**
```json
{
  "success": true,
  "data": {
    "total": 25,
    "calibrated": 18,
    "percent": 72
  }
}
```

**Calibrated definition:** Employee has non-null value for `talent_perf_what` OR `talent_perf_how`.

---

## 7. Routes & Pages

### 7.1 New Route: /calibrate

**File:** `app.py`
**Template:** `templates/calibrate.html` (NEW)

**Behavior:**
- Always accessible (nav link always visible)
- If no talent data: Show instructional message with import button
- If has talent data: Show calibration cards for each employee

### 7.2 Navigation Update

**File:** `templates/base.html`
**Location:** Nav bar

Add "Calibrate" link between "Rate Team" and "Bonus Calculation":
```html
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('calibrate') }}">Calibrate</a>
</li>
```

### 7.3 Analytics Extension

**File:** `templates/analytics.html`
**File:** `app.py` (analytics route)

Add talent section with:

| Metric | Suggested Range |
|--------|-----------------|
| High Impact Performer | 5-15% |
| Successful Performer | 55-70% |
| Evolving Performer | 15-25% |
| Low Performer | 2-10% |
| Identified as Future Talent | 10-20% |

Movement Readiness breakdown (no suggested ranges, informational only).

### 7.4 Dashboard Extension

**File:** `templates/index.html`

Add header showing: `Current Bonus: {period} | Current Talent: {period}`

Add cross-cycle alignment table with columns:
- Employee
- Bonus Rating (%)
- Overall Performance
- Alignment status

**Alignment Logic:**
```python
def get_alignment(bonus_pct: float | None, talent_overall: str | None) -> str:
    if bonus_pct is None or talent_overall is None:
        return "incomplete"
    ranges = {
        "High Impact Performer": (120, 200),
        "Successful Performer": (90, 119),
        "Evolving Performer": (70, 89),
        "Low Performer": (0, 69),
    }
    lo, hi = ranges.get(talent_overall, (0, 200))
    return "aligned" if lo <= bonus_pct <= hi else "review"
```

---

## 8. File Changes Summary

| File | Action | Changes |
|------|--------|---------|
| `models.py` | MODIFY | Add ~30 columns to Employee, ~10 to RatingSnapshot, 1 to Period |
| `xlsx_utils.py` | MODIFY | Add `detect_spreadsheet_type()`, `TALENT_COLUMN_MAP`, `parse_talent_xlsx()` |
| `app.py` | MODIFY | Add `/calibrate` route, `POST /api/calibrate`, `GET /api/calibrate/status`, extend analytics |
| `templates/calibrate.html` | CREATE | Talent calibration input UI |
| `templates/base.html` | MODIFY | Add Calibrate nav link |
| `templates/analytics.html` | MODIFY | Add talent distribution section |
| `templates/index.html` | MODIFY | Add period display, cross-cycle alignment table |
| `templates/export.html` | MODIFY | Add talent export mode |
| `AGENTS.md` | MODIFY | Document new fields, patterns, API endpoints |

---

## 9. Migration

### 9.1 New Columns

**File:** `models.py`
**Function:** `_migrate_add_talent_columns(engine)`

```python
TALENT_MIGRATIONS = [
    # Employee table
    ('employees', 'management_level', 'TEXT'),
    ('employees', 'job_category', 'TEXT'),
    ('employees', 'hire_date', 'DATETIME'),
    ('employees', 'length_of_service', 'TEXT'),
    ('employees', 'time_in_job_profile', 'TEXT'),
    ('employees', 'region', 'TEXT'),
    ('employees', 'country', 'TEXT'),
    ('employees', 'talent_perf_what', 'TEXT'),
    ('employees', 'talent_perf_how', 'TEXT'),
    ('employees', 'talent_overall_perf', 'TEXT'),
    ('employees', 'talent_last_overall_perf', 'TEXT'),
    ('employees', 'talent_growth_agility', 'TEXT'),
    ('employees', 'talent_change_agility', 'TEXT'),
    ('employees', 'talent_identified_future', 'BOOLEAN'),
    ('employees', 'talent_last_identified_future', 'BOOLEAN'),
    ('employees', 'talent_movement_readiness', 'TEXT'),
    ('employees', 'talent_last_movement_readiness', 'TEXT'),
    ('employees', 'talent_proposed_actions', 'TEXT'),
    ('employees', 'talent_promo_job_profile', 'TEXT'),
    ('employees', 'talent_promo_business_need', 'TEXT'),
    ('employees', 'talent_promo_role_scope', 'TEXT'),
    ('employees', 'talent_promo_readiness', 'TEXT'),
    ('employees', 'talent_tenets_strengths', 'TEXT'),
    ('employees', 'talent_tenets_improvements', 'TEXT'),
    ('employees', 'talent_calibration_status', 'TEXT'),
    ('employees', 'talent_last_updated', 'DATETIME'),
    # Period table
    ('periods', 'cycle_type', 'TEXT'),
    # RatingSnapshot table
    ('rating_snapshots', 'snapshot_talent_perf_what', 'TEXT'),
    ('rating_snapshots', 'snapshot_talent_perf_how', 'TEXT'),
    ('rating_snapshots', 'snapshot_talent_overall_perf', 'TEXT'),
    ('rating_snapshots', 'snapshot_talent_growth_agility', 'TEXT'),
    ('rating_snapshots', 'snapshot_talent_change_agility', 'TEXT'),
    ('rating_snapshots', 'snapshot_talent_movement_readiness', 'TEXT'),
    ('rating_snapshots', 'snapshot_talent_proposed_actions', 'TEXT'),
    ('rating_snapshots', 'snapshot_talent_promo_job_profile', 'TEXT'),
    ('rating_snapshots', 'snapshot_talent_tenets_strengths', 'TEXT'),
    ('rating_snapshots', 'snapshot_talent_tenets_improvements', 'TEXT'),
]
```

---

## 10. Testing

### 10.1 New Test Files

| File | Coverage |
|------|----------|
| `tests/test_talent_import.py` | Spreadsheet detection, column mapping, parsing |
| `tests/test_talent_api.py` | `/api/calibrate` endpoint, validation |
| `tests/test_derivation.py` | `derive_overall_performance()`, `derive_future_talent()` |
| `tests/test_talent_analytics.py` | Distribution calculations, suggested ranges |

### 10.2 Test Fixtures Needed

**File:** `tests/conftest.py`

```python
@pytest.fixture
def sample_talent_employee():
    return Employee(
        associate_id='T001',
        associate='Test Employee',
        talent_perf_what='Meets Expectations',
        talent_perf_how='Surpasses Expectations',
        talent_growth_agility='Always/Most of the Time',
        talent_change_agility='Sometimes',
        talent_movement_readiness='Continue growing in current role',
    )

@pytest.fixture
def sample_talent_xlsx(tmp_path):
    # Creates sample-data-talent-test.xlsx
    ...
```

---

## 11. Sample Data Scripts

### 11.1 New Script

**File:** `scripts/create_sample_talent_data.py`

Creates: `sample-data-talent-small.xlsx`, `sample-data-talent-large.xlsx`

### 11.2 Script Updates

| Script | Update |
|--------|--------|
| `scripts/populate_sample_ratings.py` | Add `--with-talent` flag, `SMALL_TEAM_TALENT` dict |
| `scripts/create_demo_templates.py` | Include talent fields in template databases |

### 11.3 Distribution Guidelines

**Performance What/How Matrix (target %):**
```
              How →   Surpasses   Meets   MeetsSome   DoesNotMeet
What ↓
Surpasses              10%        15%        2%           0%
Meets                  15%        40%       10%           2%
MeetsSome               2%         3%        1%           0%
```

**Other distributions:**
- Movement Readiness: Continue 75%, Promotion 20%, Lateral 5%
- Future Talent: Yes 15-20%, No 80-85%

---

## 12. Implementation Phases

### Phase 1: Model & Import (Foundation)

**Files:** `models.py`, `xlsx_utils.py`
**Tests:** `test_talent_import.py`, `test_derivation.py`

Tasks:
- [ ] Add columns to Employee model
- [ ] Add columns to RatingSnapshot model
- [ ] Add `cycle_type` to Period model
- [ ] Add migration function
- [ ] Implement `detect_spreadsheet_type()`
- [ ] Implement `TALENT_COLUMN_MAP`
- [ ] Implement `parse_talent_xlsx()`
- [ ] Handle employee creation for unknown `associate_id`
- [ ] Implement `derive_overall_performance()`
- [ ] Implement `derive_future_talent()`
- [ ] Write tests

### Phase 2: Calibrate UI (Manager Input)

**Files:** `app.py`, `templates/calibrate.html`, `templates/base.html`
**Tests:** `test_talent_api.py`

Tasks:
- [ ] Create `/calibrate` route
- [ ] Create `calibrate.html` template
- [ ] Add Calibrate nav link
- [ ] Implement `POST /api/calibrate` with validation
- [ ] Implement `GET /api/calibrate/status`
- [ ] Add 2-second auto-save debounce (match rate.html pattern)
- [ ] Add tenet selection UI
- [ ] Add promotion section (expandable)
- [ ] Show bonus context section
- [ ] Write tests

### Phase 3: Export (Output)

**Files:** `app.py`, `templates/export.html`

Tasks:
- [ ] Detect export mode (bonus vs talent)
- [ ] Add talent fields to export table
- [ ] Per-field copy buttons
- [ ] CSV export with talent fields
- [ ] Excel export with talent fields

### Phase 4: Cross-Cycle Views (Correlation)

**Files:** `app.py`, `templates/index.html`, `templates/analytics.html`
**Tests:** `test_talent_analytics.py`

Tasks:
- [ ] Add period display to dashboard header
- [ ] Add cross-cycle alignment table to dashboard
- [ ] Implement alignment logic
- [ ] Extend analytics with talent distributions
- [ ] Add suggested ranges for talent metrics
- [ ] Add movement readiness breakdown chart
- [ ] Update demo templates with talent data

---

## 13. Workday Report Structure

**Talent Calibration XLSX format:**
- Row 1-5: Report parameters (skip)
- Row 6: Column headers
- Row 7+: Employee data

**Required columns for import:**
- `Associate ID` (primary key)
- `Worker` (name)

**All other columns optional.**

---

## 14. UI Patterns

### Auto-save Pattern

**Match existing rate.html implementation:**
```javascript
// 2-second debounce
let saveTimeout;
function scheduleSave(employeeId) {
    clearTimeout(saveTimeout);
    saveTimeout = setTimeout(() => saveCalibration(employeeId), 2000);
}
```

### Card Layout

Match rate.html card structure:
- Green border when calibrated
- Employee name + context header
- Collapsible sections for Promotion, Bonus Context

### Data Attributes

Use `data-employee-id` for all interactive elements (consistent with existing pattern).

---

*End of Specification*
