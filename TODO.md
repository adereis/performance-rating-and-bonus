# Project TODO List

This file tracks future enhancements and feature requests for the Quarterly Performance Rating System.

---

## Planned Features

_(No planned features at this time)_

---

## Backlog Features

_(Features from original README.md Future Enhancements section)_

### CSV Export Functionality
**Priority:** High
**Status:** Not Started (removed incomplete implementation)
**Description:** Add proper browser-download CSV export for ratings and bonus calculations.

**Previous Issue:**
- Incomplete export feature was removed that saved files to ~/tmp without triggering browser download
- Users had to manually retrieve files from server filesystem

**Proper Implementation:**
- Use Flask's `send_file()` with in-memory CSV generation
- Trigger browser download (no server-side file accumulation)
- Export buttons on:
  - Dashboard: Export all ratings with justifications
  - Bonus Calculation page: Export bonus results with all details
- Include all relevant columns in exports
- Timestamped filenames: `ratings_export_2025-11-24.csv`, `bonus_calculation_2025-11-24.csv`

**Implementation Notes:**
```python
from flask import send_file
from io import StringIO, BytesIO

@app.route('/export/ratings')
def export_ratings():
    # Generate CSV in memory
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=...)
    writer.writeheader()
    writer.writerows(data)

    # Convert to bytes for send_file
    mem = BytesIO()
    mem.write(output.getvalue().encode())
    mem.seek(0)

    return send_file(
        mem,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'ratings_export_{timestamp}.csv'
    )
```

---

### Import Compa-Ratio Data from Workday
**Priority:** Low (Deferred)
**Status:** Not Started - Complex and potentially problematic
**Description:** Add support for importing Compa-Ratio (CR) data from Workday to enable salary equity-based bonus adjustments.

**Why Deferred:**

1. **Export Complexity:**
   - Workday export format for CR data is complex and inconsistent
   - Would require importing from specialized compensation reports
   - Multi-row format per employee (varies by country: 4-10 rows)
   - Need to calculate CR from base pay and range midpoint fields

2. **Per-Country Distortions:**
   - CR values can be distorted in some countries due to outdated salary bands
   - Example: Country with outdated bands shows inflated CRs (employees paid above "midpoint")
   - These inflated CRs are compensation for band staleness, not actual overpayment
   - Using CR as bonus drag in these cases would unfairly penalize employees
   - Would require manual per-country CR adjustment factors to compensate
   - Different countries have different band refresh cycles and market conditions

3. **Business Logic Complexity:**
   - Requires country-specific CR interpretation rules
   - Need to identify which countries have distorted bands
   - Must maintain per-country adjustment factors
   - Adds significant complexity for marginal benefit
   - Risk of unintended consequences in bonus distribution

4. **Current Focus:**
   - Bonus algorithm focuses on performance differentiation
   - Team performance is the primary factor, not salary equity
   - Simpler implementation is more maintainable and transparent

**Potential Future Implementation (if needed):**
- Import CR data from Workday compensation export
- Calculate: `compa_ratio = base_pay_usd / range_midpoint_usd`
- Add `compa_ratio` field to Employee model
- Implement per-country CR adjustment configuration
- Add CR Power parameter to bonus calculation
- Apply CR multiplier: `1 / (CR^cr_power)` with country adjustments
- Create country-specific rules for CR interpretation

**Note:** This feature has been removed from the current implementation due to technical complexity and business logic concerns around per-country distortions. The bonus algorithm now focuses solely on performance-based differentiation, which is simpler, more transparent, and avoids unintended geographic biases.

---

### Save Multiple Parameter Configurations
**Priority:** Low
**Status:** Not Started
**Description:** Allow saving multiple bonus calculation parameter sets (e.g., "Conservative", "Aggressive", "Balanced") for quick switching.

**Implementation Notes:**
- Create `bonus_configs.json` or database table
- Store named configs: `{"name": "Conservative", "upside": 1.1, "downside": 2.0, "cr_power": 0.5}`
- Add dropdown in bonus calculation page to select config
- Include "Save Current" and "Load" buttons

---

### Historical Rating Comparison
**Priority:** Medium
**Status:** Not Started
**Description:** Track ratings across quarters and show trends/changes over time per employee.

**Implementation Notes:**
- Create `ratings_history` table with quarter/year tracking
- Archive ratings at end of each quarter
- Add "History" tab showing rating trends per employee
- Chart.js line graph showing performance over time
- Compare quarter-over-quarter changes

---

### Bulk Edit Capabilities
**Priority:** Low
**Status:** Not Started
**Description:** Allow bulk operations like "set all unrated to 100%" or "copy justifications from last quarter".

**Implementation Notes:**
- Add "Bulk Actions" dropdown in rate.html
- Options: "Set all unrated to 100%", "Clear all ratings", "Apply template justification"
- Confirmation dialog before applying
- Update multiple records via `/api/bulk_rate` endpoint

---

### PDF Export for HR Submission
**Priority:** Medium
**Status:** Not Started
**Description:** Generate professional PDF reports with ratings, justifications, and bonus calculations for HR submission.

**Implementation Notes:**
- Use library like ReportLab or WeasyPrint
- Include company branding, manager signature block
- Sections: Team summary, individual ratings with justifications, bonus calculations
- Generate via `/export_pdf` endpoint
- Timestamped filename

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

### Team Tenets / Leadership Principles Evaluation

**Completed:** 2025-11-26
**Description:** Configuration-driven system for evaluating employees against team-specific tenets.

**Implementation:**
- ✅ Database fields added: `tenets_strengths`, `tenets_improvements` (JSON arrays in Text fields)
- ✅ Configuration file system: `tenets.json` (team-specific, gitignored)
- ✅ Sample configuration: `tenets-sample.json` (committed to repo)
- ✅ UI in `rate.html`: Checkbox-based selection with tooltips for tenet descriptions
- ✅ Client-side validation: Exactly 3 strengths, 3 improvements, no duplicates between lists
- ✅ Server-side validation: Count validation, duplicate detection, JSON validation
- ✅ API endpoint: `/api/tenets` serves configuration dynamically
- ✅ Auto-save: Tenet selections saved with 2-second debounce
- ✅ Analytics: Overall and per-organization tenet analysis on analytics page
- ✅ Workday import preservation: Tenets preserved on re-import (manager-entered data)
- ✅ Sample data generation: `populate_sample_ratings.py` generates random tenet selections
- ✅ Comprehensive test coverage: `tests/test_tenets.py` with 10 test cases

**Technical Details:**
- Stores tenet IDs as JSON arrays: `["customer_obsession", "ownership", "bias_for_action"]`
- Dynamic UI rendering from JSON configuration (no hardcoded tenets)
- Real-time checkbox state management (disables selections after 3 chosen)
- Prevents selecting same tenet in both strengths and improvements
- Analytics shows most common strengths/improvements across team and per organization

---

## Notes

- Prioritize features based on team feedback and usage patterns
- All new features should include comprehensive tests
- Update README.md and AGENTS.md when implementing new features
- Maintain backward compatibility with existing Workday exports
