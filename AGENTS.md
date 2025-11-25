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

The Quarterly Performance Rating System was built through an iterative collaboration between human direction and AI implementation:

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
- ✅ Multi-currency support (USD, GBP, EUR, CAD, INR)
- ✅ Workday Excel import functionality
- ✅ Sample data generation for demo purposes

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

### Model Information

- **AI Model**: Claude Sonnet 4.5 (claude-sonnet-4-5@20250929)
- **Platform**: Claude Code CLI (Anthropic)
- **Development Period**: November 2025
- **Total Test Coverage**: 86 unit tests
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
- Import flow: Workday XLSX → `convert_xlsx.py` → SQLite → Flask API → Web UI

### Key Design Decisions

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
- **Never commit** `ratings.db` or `bonus-from-wd.xlsx` (privacy - already in .gitignore)
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

---

## Domain Knowledge

### Performance Rating Philosophy

- **100% = "met all expectations"** (baseline, not average)
- **90-110% is the "solid performer" range** (most employees should be here)
- **130%+ is exceptional** (rare, reserved for truly outstanding work)
- Most teams should center around 100%, not 130%
- Ratings are **quarterly**, not annual (changed from original spec)
- Rating scale: 0-200% (enforced by validation)

### Bonus Target Philosophy

- Targets are **quarterly percentages** of base pay (not annual)
- Example: 20% quarterly target = 20% of quarterly base pay
- This changed from annual to quarterly - update docs if referenced
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
- `"Annual Bonus Target Percent"` - Now interpreted as **quarterly** percentage
- `"Bonus Target - Local Currency"` - Calculated bonus target in local currency

#### International Employee Handling
- **USD employees**: Only need local currency columns (Currency = "USD")
- **International employees**: Require both:
  - `"Bonus Target - Local Currency"` (e.g., in GBP)
  - `"Bonus Target - Local Currency (USD)"` (converted value)
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
- ❌ Commit `ratings.db`, `bonus-from-wd.xlsx`, or any real employee data
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
- `bonus-from-wd.xlsx` - quarterly bonus export (already in .gitignore)
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
- **Do not add**: Business logic or calculations (belongs in app.py)

#### `convert_xlsx.py` (Workday Import)
- Excel file reading with openpyxl
- Workday column mapping
- Data transformation and cleaning
- Manager name extraction from org field
- Database population with Workday data
- **Preserves**: Existing manager-entered fields (ratings, justifications)

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
- `test_models.py` - Employee model and database operations (14 tests)
- `test_api.py` - Flask routes and API endpoints (22 tests)
- `test_import.py` - Excel import functionality (6 tests)
- `test_multi_org.py` - Multi-organization scenarios (16 tests)
- `test_workday_format.py` - Workday column format validation (13 tests)
- `test_tenets.py` - Team tenets evaluation system (16 tests)
- Follow naming convention for pytest discovery

**Important**: When writing import tests, never use `convert_xlsx_to_db()` directly as it writes to the production `ratings.db`. Instead, simulate the import logic using test database fixtures to avoid polluting the real database.

### Templates (HTML/UI)

#### `templates/base.html`
- Base layout for all pages
- Navigation tabs
- Common CSS and JavaScript includes
- Header and footer

#### `templates/index.html` (Dashboard)
- Team overview statistics
- Summary of rated/unrated employees
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
- Team rankings table (sortable)
- **Section order**: Performance Distribution → Team Tenets → Calibration → Rankings

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

### Generated/Temporary Files (Never Commit)

These files are in `.gitignore` and should **never** be committed:
- `ratings.db` - Active database with employee data
- `sample-data-*.xlsx` - Generated sample files
- `bonus-from-wd.xlsx` - User's Workday export
- `ratings_export_*.csv` - CSV exports with timestamps
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
**Pattern**: When adding features that work differently based on organizational structure:
1. **Auto-detection**: Count unique supervisory organizations to detect multi-team scenario
2. **Progressive Disclosure**: Show simple view for single-team, expanded view for multi-team
3. **Reuse calculation logic**: Extract bonus calculation into helper function, call twice (team-level and org-level)
4. **Tabbed interface**: Use tabs to separate views without overwhelming single-team users
5. **Budget flow visualization**: Show teams gaining/losing budget during normalization
6. **Terminology**: Avoid role-specific terms like "director" - use neutral terms like "multi-team" or "organization-level"

**Implementation Notes** (bonus_calculation.html + app.py:500-617):
- Helper function `calculate_bonus_for_employees()` encapsulates calculation logic
- Detection: `len(unique_orgs) > 1` triggers multi-team view
- Three tabs: Overview (always), Team Comparison, Detailed Breakdown (only if multi-team)
- Budget impact calculated as: `org_level_allocation - team_level_allocation` per team
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
**Cause**: Missing "Bonus Target - Local Currency (USD)" column
**Solution**: Ensure Workday export includes USD conversion columns for non-USD employees

### Issue: Workday Re-Import Overwrites Ratings
**Cause**: Bug in preserve logic in convert_xlsx.py
**Should Never Happen**: Manager fields are explicitly preserved (see tests/test_import.py)
**Debug**: Check `convert_xlsx.py` lines handling existing employee updates

---

## Future Enhancements

Potential areas for expansion (not yet implemented):

- [ ] CSV export from Bonus Calculation page
- [ ] Save multiple parameter configurations
- [ ] Historical rating comparison (quarter-over-quarter)
- [ ] Bulk edit capabilities
- [ ] PDF export for HR submission
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
