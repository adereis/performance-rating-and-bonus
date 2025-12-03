# Test Suite for Performance Rating System

This directory contains comprehensive unit tests for the performance rating system.

## Test Coverage

The test suite includes **42 tests** organized into 3 test modules:

### 1. `test_models.py` - Employee Model Tests (14 tests)
Tests for SQLAlchemy Employee model and database operations:

- **CRUD Operations**: Create, Read, Update, Delete employee records
- **Query Operations**: Query by name, grade, filter rated/unrated employees
- **Data Conversion**: to_dict() method for JSON serialization
- **Data Integrity**: Nullable fields, float precision, timestamps
- **Ordering**: Sort employees by performance rating

### 2. `test_api.py` - Flask API Tests (22 tests)
Tests for Flask routes and API endpoints:

#### API Endpoints:
- **Rating API** (`/api/rate`):
  - Successfully rating an employee
  - Updating existing ratings
  - Validation (missing name, not found, invalid values)
  - Boundary testing (0, 200)
  - Decimal ratings
  - Empty rating (un-rating)
  - Manager input fields

#### Web Routes:
- Dashboard (`/`) - statistics display
- Rating page (`/rate`)
- Analytics dashboard (`/analytics`) - distribution, averages
- Export endpoint (`/export`) - CSV generation

#### Validation Tests:
- Rating must be between 0-200
- Negative values rejected
- Values > 200 rejected
- Invalid format (non-numeric) rejected
- Empty values allowed (un-rating)

### 3. `test_import.py` - Excel Import Tests (6 tests)
Tests for Workday Excel import functionality:

- **Import Operations**: Valid Excel file import
- **Update Logic**: Re-import updates Workday fields
- **Data Preservation**: Manager inputs preserved on re-import
- **Edge Cases**: Empty cells, missing values
- **Initialization**: New employees get empty manager fields
- **Error Handling**: Nonexistent file

## Running Tests

### Run All Tests
```bash
python -m pytest tests/ -v
```

### Run Specific Test Module
```bash
python -m pytest tests/test_models.py -v
python -m pytest tests/test_api.py -v
python -m pytest tests/test_import.py -v
```

### Run Specific Test Class
```bash
python -m pytest tests/test_models.py::TestEmployeeModel -v
python -m pytest tests/test_api.py::TestAPIEndpoints -v
```

### Run Specific Test
```bash
python -m pytest tests/test_models.py::TestEmployeeModel::test_create_employee -v
```

### Run with Coverage Report
```bash
pip install pytest-cov
python -m pytest tests/ --cov=. --cov-report=html
```

## Test Fixtures

The test suite uses pytest fixtures defined in `conftest.py`:

- **`test_db`**: Temporary SQLite database for each test
- **`db_session`**: Database session for a test
- **`sample_employee_data`**: Single employee data
- **`sample_employees`**: Multiple employees with varied ratings
- **`app`**: Flask app configured for testing
- **`client`**: Flask test client for HTTP requests
- **`populated_db`**: Database pre-populated with sample employees

## Test Database

Tests use isolated temporary SQLite databases:
- Each test gets a fresh database
- No interference between tests
- Automatic cleanup after each test
- No impact on production `ratings.db`

## Test Results

All 42 tests currently pass:

```
============================= test session starts ==============================
collected 42 items

tests/test_api.py::TestAPIEndpoints::test_index_route PASSED             [  2%]
tests/test_api.py::TestAPIEndpoints::test_rate_page_route PASSED         [  4%]
...
tests/test_models.py::TestEmployeeModel::test_order_by_rating PASSED     [100%]

=============================== 42 passed =========================
```

## Key Test Scenarios

### Performance Rating Validation
- ✅ Valid range: 0-200
- ✅ Boundary values: 0, 200
- ✅ Decimal values: 123.5
- ✅ Empty values (un-rating)
- ❌ Negative values: -10
- ❌ Too high: 250
- ❌ Invalid format: "abc"

### Data Preservation
- ✅ Manager inputs preserved on Workday re-import
- ✅ Workday fields updated on re-import
- ✅ Ratings, justifications, mentor/mentee data maintained

### Edge Cases
- ✅ Empty database operations
- ✅ Null/empty Excel cells
- ✅ Missing employee lookup
- ✅ Float precision maintained

## Dependencies

Required packages (in `requirements.txt`):
```
pytest==7.4.3
pytest-flask==1.3.0
```

## Future Test Additions

Potential areas for additional test coverage:
- Integration tests for full workflow (import → rate → export)
- Performance tests with large datasets (1000+ employees)
- Concurrent access tests
- JavaScript client-side validation tests
- Template rendering tests
