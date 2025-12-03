# AI Development Credits & Developer Guide

This project was developed with the assistance of AI coding agents to accelerate development and ensure code quality.

---

## Table of Contents
1. [AI Development History](#ai-development-history)
2. [Coding Standards](#coding-standards)
3. [Architectural Principles](#architectural-principles)
4. [Development Patterns](#development-patterns)
5. [Domain Knowledge](#domain-knowledge)
6. [Development Constraints](#development-constraints)
7. [File Responsibilities](#file-responsibilities)

---

## AI Development History

### Development Approach

The Performance Rating System was built through an iterative collaboration between human direction and AI implementation:

1. **Requirements Definition**: Human-defined business requirements for performance rating and bonus calculation
2. **AI Implementation**: Claude Code (Anthropic) implemented features, wrote tests, and created documentation
3. **Iterative Refinement**: Multiple rounds of feedback and adjustment to match exact requirements
4. **Quality Assurance**: Comprehensive test suite (70 tests) ensuring correctness

### AI Contributions

#### Claude Code (Anthropic)
- **Primary Development Agent**: Implemented core application logic, database models, and web interface
- **Testing**: Created comprehensive test suite with 70 unit tests covering all major functionality
- **Documentation**: Authored README.md, BONUS_CALCULATION_README.md, and inline code documentation
- **Algorithm Implementation**: Implemented bonus calculation algorithm with split curve and normalization
- **UI/UX**: Designed and implemented all HTML templates with responsive CSS
- **Sample Data**: Created sample data generator with realistic fictitious employee data

#### Key Features Developed with AI Assistance
- ✅ Flask web application architecture
- ✅ SQLAlchemy ORM models and database schema
- ✅ Auto-save functionality with debouncing
- ✅ Performance rating validation and API endpoints
- ✅ Analytics dashboard with Chart.js visualizations
- ✅ Distribution calibration calculations and UI
- ✅ Algorithmic bonus calculation with configurable parameters
- ✅ Budget override feature with proportional scaling
- ✅ Multi-currency support (USD, GBP, EUR, CAD, INR)
- ✅ Workday Excel import functionality
- ✅ Sample data generation for demo purposes
- ✅ Team tenets evaluation with inline editing UI
- ✅ Historical data preservation with period archiving
- ✅ Employee rating history with trend visualization
- ✅ Period-over-period comparison in Analytics
- ✅ Period Browser for viewing archived periods

### Human Oversight

All AI-generated code was:
- **Reviewed**: Human verification of correctness and alignment with requirements
- **Tested**: Validated through comprehensive test suite and manual testing
- **Refined**: Iteratively improved based on feedback and edge cases
- **Documented**: Ensured clear documentation for maintainability

### Transparency

This project demonstrates how AI coding assistants can accelerate development while maintaining high code quality standards. The AI handled implementation details, allowing human focus on:
- Business logic and requirements
- User experience decisions
- Architectural choices
- Edge case identification
- Final quality validation

### Reproducibility

To achieve similar results with AI assistance:

1. **Clear Requirements**: Provide detailed specifications for desired functionality
2. **Iterative Feedback**: Review outputs and provide specific feedback for refinement
3. **Test-Driven**: Request comprehensive tests to ensure correctness
4. **Documentation**: Explicitly request user-facing and technical documentation
5. **Sample Data**: Ask for realistic demo data to enable immediate testing

### Development Workflow

**Git Commit Policy**: The AI agent performs git commits locally as work progresses, but only pushes to GitHub when explicitly instructed by the user. This allows for local version control while maintaining user control over what gets published to remote repositories.

**Documentation Maintenance**: Keep TODO.md updated as features are implemented:
- Move completed features from "Planned" or "Backlog" to "Completed" section
- Add completion date and brief implementation summary
- Remove or update features that are no longer relevant
- Add new feature requests to appropriate section as they arise

### Model Information

- **AI Model**: Claude Sonnet 4.5 (claude-sonnet-4-5@20250929)
- **Platform**: Claude Code CLI (Anthropic)
- **Development Period**: November 2025
- **Total Test Coverage**: 139 unit tests
- **Lines of Code**: ~3,000 (application + tests)

---

## Coding Standards

### Python Style
- Follow PEP 8 conventions
- Use type hints where appropriate for function parameters and return values
- Maximum line length: 100 characters
- Use descriptive variable names matching existing patterns:
  - `perf_rating` for performance rating values
  - `bonus_target_usd` for monetary values in USD
  - `justification` for text explanations
  - `assoc_id` for employee/associate identifiers

### Database Patterns
- **All monetary values stored in USD** for calculations (canonical form)
- Display values converted to local currency for UI presentation only
- Use SQLAlchemy ORM patterns established in `models.py`
- **Preserve manager-entered data** on Workday re-imports (ratings, justifications, mentor/mentee fields)
- Workday fields (salary, targets, org structure) are updated on re-import

### Testing Requirements
- Write tests for all new features before or alongside implementation
- Maintain test coverage above 70%
- Follow existing test patterns in `tests/conftest.py` for fixtures
- Use descriptive test names: `test_[feature]_[scenario]_[expected_result]`
  - Example: `test_bonus_calculation_with_split_curve_normalization`
- Each test should be independent and not rely on execution order

### Frontend Patterns
- Vanilla JavaScript (no frameworks) - keep it simple
- 2-second debounce on auto-save operations
- Use fetch API for AJAX calls to backend
- Bootstrap-style CSS classes for consistency
- Chart.js for data visualizations
- **Sortable tables**: Use `.sortable` class on headers with `data-sort` attributes
- **Data attributes**: Store sortable values on table rows as `data-{column}` attributes
- **Employee identification**: Always use `data-employee-id` attribute (never `data-employee-name`)
  - Employee names can be duplicated; `associate_id` is the unique primary key
  - All clickable employee names must have: `<span class="employee-name" data-employee-id="{{ employee['Associate ID'] }}">`
  - All API endpoints use IDs, not names

### Visualization Patterns
- **Chart.js** for standard charts (bar, line, pie)
- **Custom HTML/Canvas**: For specialized visualizations like diverging bar charts
- When creating complex charts (e.g., butterfly/diverging charts):
  - Start with simplest approach first (e.g., tried single Chart.js instance, didn't align)
  - Break down into smaller independent components (individual charts per row)
  - Use CSS Grid for precise alignment
  - Prioritize visual clarity over complex single-chart solutions

---

## Architectural Principles

### Data Flow
- **Workday is source of truth** for employee data (salary, bonus targets, org structure)
- **Manager ratings are local-only** and preserved across Workday updates
- **Bonus calculations are ephemeral** (recalculated on demand, never stored in database)
- **Historical snapshots** preserve rating data across periods (`RatingPeriod` + `EmployeeSnapshot` tables)
- Import flow: Workday XLSX → Import UI → `xlsx_utils.py` → SQLite → Flask API → Web UI
- Archive flow: Dashboard → Archive Period → Snapshots created → Current ratings cleared

### Key Design Decisions

#### Employee Identification by ID (Not Name)
- **Primary key**: `associate_id` is the unique identifier for all employees
- **Why**: Employee names can be duplicated (e.g., two "John Smith"s in different departments)
- **Everywhere IDs are used**:
  - API endpoints: `/api/employee/<associate_id>` (not name)
  - Filter system: `exclude_ids` parameter (not `exclude_names`)
  - Employee modal: Opens by ID, saves by ID
  - Frontend: All clickable names use `data-employee-id` attribute
  - JavaScript: All fetch calls use IDs to identify employees
- **Display**: Names are shown to users, but IDs are used for all data operations
- **Critical**: Never use employee names as identifiers in URLs, API calls, or data attributes

#### Local-First Architecture
- **No cloud dependencies**: SQLite only, no external databases
- **No authentication**: Designed for single-user local execution
- **Privacy-focused**: All sensitive data stays on user's machine
- No telemetry or external API calls

#### Auto-Save Pattern
- 2-second debounce on rating changes (defined in rate.html)
- Prevents excessive API calls during typing
- Visual feedback on save status (saving indicator)
- Preserves user work without explicit "Save" button

#### Fixed Pool Guarantee
- Normalization ensures bonuses sum to exact target pool (USD)
- Sum of all `bonus_target_usd` values = total pool
- After applying performance multipliers, normalize to preserve pool
- Mathematical guarantee: `sum(final_bonuses) == sum(bonus_targets)`

#### Split Curve Algorithm
- Different exponents for above/below 100% performance
- **Upside exponent** (default 1.35): Rewards for ratings ≥ 100%
- **Downside exponent** (default 1.9): Penalties for ratings < 100%
- More aggressive penalties than rewards (intentional asymmetry)

### Don't Break These
- **Never commit** `ratings.db` or real Workday export files (privacy - already in .gitignore)
- **Never change bonus algorithm** without updating BONUS_CALCULATION_README.md
- **Preserve backward compatibility** with existing Workday export format
- **Never store calculated bonuses** in database (keep ephemeral)
- **Never add cloud dependencies** or external API calls
- **Never break the 2-second auto-save debounce** pattern

---

## Development Patterns

### Adding a New API Endpoint

1. Add route to `app.py`
2. Follow existing pattern: try/except with JSON error responses
3. Use appropriate HTTP methods (GET for reads, POST for writes)
4. Return JSON with consistent structure: `{"success": bool, "data": {...}}` or `{"success": false, "error": "message"}`
5. Add corresponding tests to `tests/test_api.py`
6. Update API documentation in code comments

Example pattern:
```python
@app.route('/api/new_endpoint', methods=['POST'])
def new_endpoint():
    try:
        data = request.get_json()
        # Validation
        if not data.get('required_field'):
            return jsonify({"success": False, "error": "Missing required_field"}), 400

        # Business logic
        result = perform_operation(data)

        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
```

### Adding a Database Field

1. Update `Employee` model in `models.py`
2. Handle migration (we don't use Alembic - manual ALTER TABLE or recreate database)
3. Update `convert_xlsx.py` if field comes from Workday export
4. Add tests for new field in `tests/test_models.py`
5. Update UI templates if field is user-facing
6. Update sample data generator (`create_sample_data.py`) if needed

**Migration approach**: This project uses simple SQLite, so:
- For dev: Delete `ratings.db` and re-import
- For production: Write manual ALTER TABLE statement or provide migration script

### Modifying Bonus Algorithm

1. Update calculation in `app.py` bonus_calculation route (around line 200+)
2. Update `BONUS_CALCULATION_README.md` with manager-friendly explanation
3. Add test cases to verify:
   - Pool normalization still guarantees exact sum
   - Edge cases (all 0%, all 100%, all 200%)
   - Multi-currency handling
4. Test with both small and large sample datasets

### Adding a New Template/Page

1. Create HTML template in `templates/` directory
2. Extend `base.html` for consistent layout
3. Add route in `app.py` to render template
4. Add navigation link in `base.html` if needed
5. Test rendering with `tests/test_api.py`

### Inline Editing with Auto-Save Pattern

For editable fields in summary stats or cards:

1. **HTML Structure**:
   ```html
   <input type="number"
          id="field_name"
          value="{{ value }}"
          style="border: none; background: transparent; ..."
          title="Tooltip explaining what this does">
   ```

2. **CSS for Visual Feedback**:
   ```css
   #field_name:hover {
       background: rgba(102, 126, 234, 0.05) !important;
   }
   #field_name:focus {
       background: rgba(102, 126, 234, 0.1) !important;
       border: 1px solid #667eea !important;
   }
   ```

3. **JavaScript Auto-Save**:
   - Debounce: 2 seconds after last keystroke
   - Also save on blur (when clicking away)
   - Show temporary "✓ Saved" indicator
   - Reload page if values affect displayed data

4. **Examples**: Rating percentages on `/rate`, budget override on `/bonus-calculation`

### Working with Historical Data

#### Archiving a Period
1. User clicks "Archive Period" on Dashboard
2. API creates new `RatingPeriod` record with period_id and name
3. For each employee with ratings, creates `EmployeeSnapshot` with:
   - Reference to period and employee
   - Snapshot of current rating data (rating, justification, tenets, mentors)
   - Snapshot of context (job profile, org at time of snapshot)
4. Clears all current ratings from `Employee` table
5. Returns success with count of archived employees

#### Displaying Employee History
1. Click employee name → Modal opens with "History" tab
2. API `/api/employee/<id>/history` returns all snapshots ordered by period
3. Trend chart shows ratings over time with:
   - Solid lines for consecutive periods
   - Dashed lines bridging gaps (partial/missing data)
   - Trend indicator (improving/stable/declining) using linear regression
4. Expandable cards show period details (justification, tenets, context)

#### Period Comparison (Analytics)
1. Dropdown populated from `/api/periods` (all archived periods)
2. Selection triggers `/api/period-comparison/<period_id>`
3. Comparison logic:
   - Match employees by `associate_id` across current and historical
   - Calculate change: `current_rating - historical_rating`
   - Categorize: improved (>5%), declined (<-5%), stable, new, departed
4. Display summary stats and per-employee comparison table

#### Historical Import
1. Upload old Workday export with Notes field containing rating data
2. Select "Historical Period" import type, provide period_id and name
3. Parser extracts from Notes: rating, justification, tenets, mentors
4. Creates `RatingPeriod` and `EmployeeSnapshot` records
5. Does NOT modify current `Employee` table ratings

### UI Design Iteration

When adding new features, follow this pattern:
1. **Implement** with initial UI (may be verbose)
2. **Gather user feedback** about UI space and usability
3. **Simplify** based on feedback (example: budget override went from separate config panel → inline editable summary stat)
4. **Document** the final pattern for consistency

**Principle**: Minimize UI clutter. If a field can be inline-editable, prefer that over a separate form/panel.

---

## UI/UX Principles

### Hide Implementation Details
- Don't expose internal calculation details unless they help users make decisions
- Example: "Value per Share" was removed from bonus calculation UI because it's an implementation detail that doesn't inform manager decisions
- Show: Base Pool, Override, Adjusted Pool, Final Bonuses
- Hide: Normalization factors, raw shares, internal multipliers

### Prefer Inline Editing
- Make summary stats editable where appropriate (budget override)
- Use tooltips (ⓘ) to explain what fields do
- Provide visual feedback on hover/focus
- Consistent auto-save pattern (2-second debounce)

### Responsive to User Feedback
- Initial implementations may be verbose (separate config panels, extra fields)
- Refine based on "taking too much real estate" feedback
- Final UIs should be as compact as possible while remaining clear

---

## Domain Knowledge

### Performance Rating Philosophy

- **100% = "met all expectations"** (baseline, not average)
- **90-110% is the "solid performer" range** (most employees should be here)
- **130%+ is exceptional** (rare, reserved for truly outstanding work)
- Most teams should center around 100%, not 130%
- Ratings are **period-based**, not necessarily annual
- Rating scale: 0-200% (enforced by validation)

### Bonus Target Philosophy

- Targets are **period-based percentages** of base pay
- Example: 20% target = 20% of base pay for the rating period
- The rating period can be defined by the organization (monthly, quarterly, semi-annual, annual, etc.)
- International employees: bonus targets must be provided in both local currency and USD

### Workday Export Format

#### Required Column Format
- **"Supervisory Organization"** format: `"Supervisory Organization (Manager Name)"`
  - Parse manager name from parentheses: `extract_manager_name()` function
  - Example: `"Engineering (Della Gate)"` → manager = "Della Gate"

#### Column Name Assumptions (see tests/test_workday_format.py)
- `"Associate"` - Employee name
- `"Associate ID"` - Unique identifier (can contain letters/numbers)
- `"Supervisory Organization"` - Org with manager in parentheses
- `"Current Job Profile"` - Job title/role
- `"Current Base Pay All Countries"` - Salary in local currency
- `"Currency"` - ISO currency code (USD, GBP, EUR, CAD, INR)
- `"Annual Bonus Target Percent"` - Interpreted as the bonus target percentage for the rating period
- `"Bonus Target - Local Currency"` - Calculated bonus target in local currency

#### International Employee Handling
- **USD employees**: Only need `"Bonus Target - Local Currency"` column (which IS in USD for them)
  - Workday quirk: The USD column `"Bonus Target - Local Currency (USD)"` is NULL/empty for USD employees
- **International employees**: Require both:
  - `"Bonus Target - Local Currency"` (e.g., in GBP, CAD)
  - `"Bonus Target - Local Currency (USD)"` (converted value)
- **Automatic fallback logic**: Code uses `USD column OR local currency column` (app.py line 780)
  - Tries `"Bonus Target - Local Currency (USD)"` first (for international employees)
  - Falls back to `"Bonus Target - Local Currency"` if USD column is empty (for USD employees)
  - This handles the Workday export quirk automatically
- All calculations use USD values internally
- Display uses local currency where appropriate

#### Optional Columns
- `"Photo"` - Employee photo URL (not currently used)
- `"Grade"` - Internal grade (hidden from managers)
- `"Last Bonus Allocation Percent"` - Previous bonus % (reference only)
- `"Notes"` - Internal notes (not shown to managers)

### Multi-Currency Handling

- **All calculations in USD** (canonical currency)
- **Display in local currency** for employee-facing views
- Conversion happens at import time (Workday provides both values)
- Sample data includes GBP employees for testing international scenarios
- Supported currencies: USD, GBP, EUR, CAD, INR (add more in currency dropdown)

### Manager-Entered Fields

These fields are **preserved** across Workday re-imports:
- `performance_rating` (0-200%)
- `justification` (text explanation)
- `mentors` (who they mentored)
- `mentees` (who mentored them)
- `ai_related_activities` (AI/ML work)

### Analytics & Calibration

- Distribution chart shows rating frequency
- Calibration guidance is **informational only** (not enforced)
- Standard calibration: ~10% top, ~70% solid, ~20% needs improvement
- Each organization may have different calibration targets

### Team Tenets Evaluation

- **Purpose**: Track team strengths and areas for improvement against defined cultural tenets
- **Data model**: JSON arrays stored in `tenets_strengths` and `tenets_improvements` fields
- **Configuration**: Tenets defined in `tenets-sample.json` (version controlled)
- **Visualization**: Diverging butterfly chart showing strengths (green, right) vs weaknesses (red, left)
- **Sorting**: Tenets sorted by net score (strengths - weaknesses) descending
- **Sample data**: Use `--with-tenets` flag when generating sample data
- **Import**: Column indices 20 (Tenets Strengths) and 21 (Tenets Improvements)

### Budget Override

- **Purpose**: Allow managers to adjust total bonus pool when authorized to go over/under budget
- **Design choice**: Proportional scaling (Option 1)
  - Considered alternatives: performance-weighted distribution, targeted individual adjustments
  - Chose proportional scaling because it's fairest and maintains all performance differentials
- **How it works**:
  - Manager enters USD amount (can be positive or negative)
  - `adjusted_pool = base_pool + budget_override`
  - All bonuses scale proportionally by `adjusted_pool / base_pool` multiplier
  - Example: +$50k on $500k pool → everyone's bonus increases by 10%
- **Scope**: Org-level only (applies to entire organization in multi-team mode)
- **Storage**: `BonusSettings` table with `budget_override_usd` field (persisted)
- **UI**: Inline editable field in summary stats (not separate panel)
- **Validation**: None - managers can set any amount (trust-based)

---

## Development Constraints

### Do NOT

#### Architecture & Dependencies
- ❌ Add cloud dependencies or external API calls
- ❌ Add authentication/authorization (intentionally single-user)
- ❌ Store bonus calculation results in database (keep ephemeral)
- ❌ Use absolute file paths (support running from any directory)
- ❌ Add configuration files that need git tracking

#### Data & Privacy
- ❌ Commit `ratings.db`, real Workday export files, or any real employee data
- ❌ Log sensitive employee information (names, salaries, ratings)
- ❌ Add telemetry or analytics that phone home

**CRITICAL: Privacy and Data Protection**

This project handles **real employee compensation data** which is highly sensitive and confidential.

**Safe vs. Private Data:**

SAFE - Auto-generated fictitious data:
- Files generated by `create_sample_data.py`
- Sample data files: `sample-data-*.xlsx`
- Test fixtures in `tests/conftest.py`
- Data in test files using sample fixtures
- ✅ Safe to use in examples, documentation, tests, and git commits

PRIVATE - Real Workday exports:
- `real-*.xlsx` - Workday exports (automatically ignored by git)
- `Compensation_Spreadsheet.xlsx` - compensation export (real data)
- Any XLSX file imported from Workday containing real employee data
- Files with actual employee names, salaries, ratings, or compensation
- ❌ NEVER commit, reference, or include examples from these files

**Strict Rules for Private Data:**

1. NEVER commit private data files
   - Check .gitignore before any git operations
   - Workday export files must remain untracked

2. NEVER use real data in examples
   - Documentation must use fictitious sample data only
   - Code examples should reference sample data generators
   - Test cases must use fixtures with made-up data

3. NEVER put real data in git history
   - No real employee names in commit messages
   - No actual salaries or compensation in code comments
   - No real data in analysis documents that get committed

4. NEVER include real data in tests
   - Tests must use sample fixtures from conftest.py
   - Never hardcode actual employee data in test cases
   - Test data must be clearly fictitious

5. Analysis files with real data must stay local
   - Analysis documents examining real Workday exports: untracked
   - Strategy documents with real examples: untracked
   - Only commit sanitized versions with fictitious examples

6. Be extra cautious with:
   - New features that analyze real data
   - Documentation of import processes
   - Error messages that might log sensitive data
   - Debug output or print statements

**Safe Workflow:**

When asked to analyze real Workday data:
1. ✅ Read and analyze the file locally
2. ✅ Create analysis documents in local directory
3. ✅ Use generic/sanitized examples if needed
4. ❌ Do NOT stage or commit files with real data
5. ❌ Do NOT put real examples in committed documentation
6. ✅ Verify git status before committing anything

**When in doubt**: Keep it local, don't commit it. Real employee data must NEVER leave the local machine or enter version control.

#### Code Changes
- ❌ Change Workday column names without backward compatibility
- ❌ Break the 2-second auto-save debounce pattern
- ❌ Remove normalization guarantee from bonus calculation
- ❌ Change rating scale from 0-200% without updating validation
- ❌ Make manager-entered fields nullable=False (they're initially empty)

#### Documentation
- ❌ Duplicate README content in AGENTS.md
- ❌ Copy user-facing documentation here
- ❌ Add installation/usage instructions to AGENTS.md (those belong in README)

### Do NOT Replicate

**README.md** is for **users** (how to use the system):
- Installation steps
- Usage workflows
- Feature descriptions
- Troubleshooting common issues

**AGENTS.md** is for **developers/AI** (how to modify the system):
- Code patterns and conventions
- Architecture decisions and rationale
- Development workflows
- Common modification patterns

Keep these separate and don't duplicate content.

---

## File Responsibilities

### Core Application

#### `app.py` (Main Flask Application)
- Flask routes and API endpoints
- Business logic for rating, analytics, bonus calculation
- Request handling and validation
- JSON response formatting
- **Do not add**: Database models (belongs in models.py)

#### `models.py` (Database Schema)
- SQLAlchemy ORM models
- Database schema definitions
- Model methods for data conversion (`to_dict()`)
- **Models**:
  - `Employee` - Current employee data and ratings
  - `RatingPeriod` - Archived periods (period_id, name, archived_at)
  - `EmployeeSnapshot` - Historical rating snapshots linked to periods
  - `BonusSettings` - Persisted bonus calculation settings
- **Do not add**: Business logic or calculations (belongs in app.py)

#### `xlsx_utils.py` (Workday XLSX Parsing)
- Excel file reading with openpyxl
- Workday column mapping and detection
- Data transformation and cleaning
- Reusable parsing functions for import endpoints
- Functions: `analyze_xlsx()`, `parse_xlsx_employees()`, `find_column_indices()`

#### `notes_parser.py` (Notes Field Parser)
- Parses structured Notes/Single Description field from Workday exports
- Extracts: performance rating, justification, mentors, mentees, tenets
- Used for historical imports to reconstruct rating data
- Functions: `parse_notes_field()`, `format_notes_field()`

### Data Generation & Sample Data

#### `create_sample_data.py` (Sample Data Generator)
- Generates fictitious employee data
- Creates small (12 employees) or large (50 employees) datasets
- Produces Workday-format XLSX files
- Includes realistic names, salaries, job profiles
- Pre-populated with performance ratings for demo

#### `populate_sample_ratings.py` (Legacy)
- Older script for adding ratings to existing data
- Consider deprecating in favor of create_sample_data.py

### Testing

#### `tests/conftest.py` (Test Fixtures)
- Shared pytest fixtures
- Test database setup with temporary SQLite
- Sample data fixtures (`sample_employees`, `populated_db`)
- Flask app and client fixtures
- **Use these fixtures** in all new tests

#### `tests/test_*.py` (Test Modules)
- `test_models.py` - Employee, Period, RatingSnapshot models (25 tests)
- `test_api.py` - Flask routes and API endpoints (25 tests)
- `test_import_api.py` - Browser-based import API (17 tests)
- `test_multi_org.py` - Multi-organization scenarios (16 tests)
- `test_workday_format.py` - Workday column format validation (13 tests)
- `test_tenets.py` - Team tenets evaluation system (16 tests)
- `test_notes_parser.py` - Notes field parsing (15 tests)
- `test_filters.py` - Employee filtering (12 tests)
- Follow naming convention for pytest discovery

**Important**: Always use test fixtures from `conftest.py` for database operations. Never access production `ratings.db` in tests.

### Templates (HTML/UI)

#### `templates/base.html`
- Base layout for all pages
- Navigation tabs
- Common CSS and JavaScript includes
- Header and footer
- **Employee Modal**: Shared modal for viewing/editing employee details
  - "Current Period" tab: Rating, justification, tenets, mentors
  - "History" tab: Trend chart + expandable period cards
  - Auto-save with unsaved changes warning
- **Filter Panel**: Global employee filtering (managers, titles, individuals)

#### `templates/index.html` (Dashboard)
- Team overview statistics
- Summary of rated/unrated employees
- **Archive Period**: Button to snapshot current ratings and clear for next period
- Quick navigation to other features

#### `templates/rate.html` (Rating Interface)
- Employee list with rating inputs
- Auto-save functionality (2-second debounce)
- Justification text areas
- Mentor/mentee/AI activity fields

#### `templates/analytics.html` (Analytics Dashboard)
- Performance distribution charts (Chart.js)
- Team tenets diverging bar chart (custom butterfly chart)
- Distribution calibration guidance (informational)
- **Period-over-Period Comparison**: Dropdown to compare current vs historical periods
  - Summary stats: improved/stable/declined counts, average change
  - Comparison table with trend badges
- Team rankings table (sortable)
- **Section order**: Distribution → Tenets → Calibration → Period Comparison → Rankings

#### `templates/bonus_calculation.html` (Bonus Calculator)
- Parameter configuration (upside/downside exponents)
- Recalculation trigger
- Results table with individual bonuses (sortable)
- Total pool verification
- **Multi-team support**: Tabbed interface for organizations with multiple teams
  - Tab 1: Overview (organization-level calculation, always visible)
  - Tab 2: Team Comparison (team-level vs org-level normalization comparison)
  - Tab 3: Detailed Breakdown (per-employee side-by-side comparison)
  - Auto-detects multi-team scenario by counting unique supervisory organizations
  - Shows budget flow between teams (gains/losses from normalization)

#### `templates/import.html` (Workday Import)
- Drag-and-drop file upload zone
- Import type selection (Current Period vs Historical Period)
- **Current Period**: Updates Employee table, preserves ratings
  - "Clear existing data" checkbox for switching from test to real data
- **Historical Period**: Creates Period and RatingSnapshot records
  - Parses Notes field for rating data
  - Period ID and name fields
- Pre-import analysis (employee count, bonus column detection)
- Overwrite warning for existing periods

#### `templates/history.html` (Period Browser)
- Period cards grid showing all archived periods
- Click period to view detail with:
  - Summary stats (avg, min, max, full/partial counts)
  - Rating distribution chart
  - Sortable employee snapshot table
- Partial record indicator for historical imports without Notes data
- Deep linking support (/history?period=2024-H2)

### Generated/Temporary Files (Never Commit)

These files are in `.gitignore` and should **never** be committed:
- `ratings.db` - Active database with employee data
- `sample-data-*.xlsx` - Generated sample files
- `real-*.xlsx` - User's Workday exports
- `ratings_export_*.csv` - Legacy pattern (feature removed, kept for historical .gitignore compatibility)
- `__pycache__/` - Python bytecode
- `.pytest_cache/` - Pytest cache

---

## Testing Guidelines

### Running Tests

```bash
# All tests
python3 -m pytest tests/ -v

# Specific module
python3 -m pytest tests/test_api.py -v

# Specific test
python3 -m pytest tests/test_api.py::TestAPIEndpoints::test_rate_employee -v

# With coverage
python3 -m pytest tests/ --cov=. --cov-report=html
```

### Writing New Tests

1. Use fixtures from `conftest.py`:
   - `test_db` - Temporary database
   - `db_session` - Database session
   - `app` - Flask app configured for testing
   - `client` - Flask test client
   - `populated_db` - Database with sample employees

2. Follow naming convention:
   - Test files: `test_*.py`
   - Test classes: `Test*`
   - Test methods: `test_*`

3. Test structure:
   ```python
   def test_feature_scenario_expected_result(client, populated_db):
       # Arrange
       data = {"field": "value"}

       # Act
       response = client.post('/api/endpoint', json=data)

       # Assert
       assert response.status_code == 200
       assert response.json['success'] == True
   ```

4. Test isolation:
   - Each test gets a fresh database
   - Don't rely on execution order
   - Clean up any side effects

---

## Development Best Practices from Recent Sessions

### Complex Visualizations
**Lesson**: When Chart.js doesn't naturally support your visualization (e.g., diverging/butterfly charts):
1. Try the native Chart.js approach first
2. If alignment issues occur, break into independent components
3. Use individual charts per row with CSS Grid for precise layout
4. Simpler is better - don't force a library to do what it wasn't designed for

### Chart.js Segment Styling (Gap Handling)
**Use case**: Trend charts with missing data points (e.g., partial historical records)
**Solution**: Use `segment` callbacks with `spanGaps: true` for dashed bridging lines

```javascript
segment: {
    borderDash: function(segCtx) {
        // Chart.js 4.x uses flat property names: p0DataIndex, p1DataIndex
        // NOT p0.dataIndex (that's undefined in v4)
        if (ratings[segCtx.p0DataIndex] == null || ratings[segCtx.p1DataIndex] == null) {
            return [6, 4];  // Dashed for segments touching null values
        }
        return undefined;  // Solid for normal segments
    }
}
```

**Key gotcha**: With `spanGaps: true`, Chart.js iterates through ALL indices including null points, so check if either endpoint is null (not if there are nulls "between" indices).

### Feature Rollout
**Pattern**: When adding major features (like tenets):
1. Start with data model (add database fields)
2. Update import/export logic
3. Create UI for data entry/display
4. Add analytics/reporting
5. Update sample data generators
6. Write comprehensive tests (data model → import → display → analytics)
7. Document in AGENTS.md for future AI sessions

### Test Database Isolation
**Critical**: Never write tests that touch production `ratings.db`:
- Use test fixtures (`db_session`, `test_db`) from `conftest.py`
- Simulate import logic rather than calling `convert_xlsx_to_db()`
- Each test gets fresh database - no shared state
- This prevents real data pollution during test runs

### Iterative UI Refinement
**Approach**: When refining UX (like analytics page):
1. Start with all information visible
2. Remove redundant sections based on feedback
3. Reorder for logical flow (overview → details)
4. Add interactivity (sortable tables) for better usability
5. Compress/streamline to reduce visual clutter

### Multi-Level Organization Support

**Why This Matters**: When a director manages multiple teams, bonus normalization creates budget shifts between teams. A team with high performers appears to have limited budget when calculated in isolation, but at the org level, surplus budget from underperforming teams flows to high-performing teams. Frontline managers lack visibility into this, leading to confusion when final allocations differ from their expectations. Multi-team views solve this by showing both team-level and org-level calculations.

**Pattern**: When adding features that work differently based on organizational structure:
1. **Auto-detection**: Count unique supervisory organizations to detect multi-team scenario
2. **Progressive Disclosure**: Show simple view for single-team, expanded view for multi-team
3. **Reuse calculation logic**: Extract calculation into helper function, call twice (team-level and org-level)
4. **Tabbed interface**: Use tabs to separate views without overwhelming single-team users
5. **Budget flow visualization**: Show teams gaining/losing budget during normalization (bonus page)
6. **Calibration comparison**: Show per-team and cross-team calibration (analytics page)
7. **Terminology**: Avoid role-specific terms like "director" - use neutral terms like "multi-team" or "organization-level"

**Implementation Notes**:
- Bonus calculation (bonus_calculation.html + app.py:578-711):
  - Helper: `calculate_bonus_for_employees()` encapsulates calculation logic
  - Three tabs: Overview (always), Team Comparison, Detailed Breakdown (only if multi-team)
  - Budget impact: `org_level_allocation - team_level_allocation` per team
- Analytics (analytics.html + app.py:209-295):
  - Helper: `calculate_calibration_for_employees()` encapsulates calibration logic
  - Three tabs: Organization Overview, Per-Team Calibration, Team Comparison Matrix
  - Auto-generated insights: rating variance, calibration health, high-variance teams
- Detection: `len(unique_orgs) > 1` triggers multi-team view
- No database changes needed - all calculations are ephemeral

---

## Common Gotchas

### Issue: Database Locked
**Cause**: Multiple processes accessing SQLite database
**Solution**: Ensure only one Flask instance running, restart app

### Issue: Auto-Save Not Working
**Cause**: JavaScript error or debounce timing
**Check**: Browser console for errors, verify 2-second delay
**Solution**: Check network tab for API calls, ensure `/api/rate` endpoint responding

### Issue: Bonus Pool Doesn't Match Target
**Cause**: Normalization factor calculation error
**Solution**: Verify sum of `bonus_target_usd` equals total pool, check for null values

### Issue: International Employees Missing from Bonus Calc
**Cause**: Missing "Bonus Target - Local Currency (USD)" column for non-USD employees
**Solution**: Ensure Workday export includes USD conversion column for international employees
**Note**: USD employees are handled automatically - they only need the local currency column
**How it works**: Code automatically falls back to local currency column if USD column is empty (see app.py line 780)

### Issue: Workday Re-Import Overwrites Ratings
**Cause**: Bug in preserve logic in convert_xlsx.py
**Should Never Happen**: Manager fields are explicitly preserved (see tests/test_import.py)
**Debug**: Check `convert_xlsx.py` lines handling existing employee updates

### Note: Dual Field Naming Convention
**Pattern**: Database fields use different names depending on context
**Example**: Supervisory organization field has three representations:
- **Database column**: `supervisory_organization` (snake_case)
- **Python attribute**: `employee.supervisory_organization` (snake_case)
- **Dictionary key**: `emp.get('Supervisory Organization')` (Title Case, from `to_dict()`)

**Why**: The `to_dict()` method in `models.py` converts snake_case database fields to Title Case with spaces to match the Workday export column headers. This allows dictionaries to be used interchangeably whether they come from database objects or direct Excel imports.

**When it matters**: When writing SQL queries or accessing employee data as dictionaries in `app.py`. Use `'Supervisory Organization'` (with space) for dictionary keys, `supervisory_organization` for database/ORM access.

---

## Future Enhancements

Potential areas for expansion (not yet implemented):

- [ ] Save multiple parameter configurations
- [ ] Bulk edit capabilities
- [ ] Read-only sharing mode for calibration sessions
- [ ] Database migration system (Alembic)
- [ ] API documentation (Swagger/OpenAPI)

---

## Licensing

While AI-assisted, all code in this repository is owned by the project maintainers and released under the MIT License (see LICENSE file).

---

*This AGENTS.md file serves dual purposes:*
1. *Transparent disclosure of AI involvement in development*
2. *Developer guide for AI agents working on this codebase*

*Following best practices for AI-assisted software development.*
