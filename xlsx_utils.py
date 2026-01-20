"""
Utilities for parsing Workday XLSX exports.

This module provides functions for:
- Analyzing XLSX files (counting employees, detecting columns)
- Parsing employee data from Workday exports
- Creating Employee records from parsed data

Note on currency columns:
Workday exports include columns like "Bonus Target - Local Currency (XXX)" where
XXX is the manager's home currency (USD, AUD, EUR, etc.). For employees in the
manager's country, this column is empty. For international employees, it contains
the converted value. The code matches any 3-letter currency code pattern.
"""
import openpyxl
import re
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime


def parse_float(val) -> Optional[float]:
    """Safely parse a value to float."""
    try:
        return float(val) if val else None
    except (ValueError, TypeError):
        return None


def get_current_period_name() -> str:
    """
    Get the current period name in Workday format (e.g., "CY25 Q1").

    Uses calendar year (CY) and quarter based on current date.
    Q1 = Jan-Mar, Q2 = Apr-Jun, Q3 = Jul-Sep, Q4 = Oct-Dec
    """
    now = datetime.now()
    year_short = now.year % 100  # e.g., 2025 -> 25
    quarter = (now.month - 1) // 3 + 1  # 1-4
    return f"CY{year_short:02d} Q{quarter}"


def detect_import_type(period_name: str) -> Dict[str, Any]:
    """
    Suggest import type based on period from metadata.

    Compares the file's period to the current quarter to suggest whether
    this is likely a current period import or historical archive.
    The user should confirm the suggested import type.

    Args:
        period_name: Period name from metadata (e.g., "CY25 Q3")

    Returns:
        Dict with:
            - suggested_type: "current" or "historical"
            - period_id: Suggested period ID (e.g., "2025-Q3")
            - period_display: Period display name (e.g., "CY25 Q3")
            - current_period: The current period for reference
            - is_current_period: Whether file period matches current
    """
    current_period = get_current_period_name()

    # Parse period_name to generate period_id
    # Format: "CY25 Q3" or "CY25-Q3" → "2025-Q3"
    period_id = None
    if period_name:
        match = re.match(r'CY(\d{2})\s*[-]?\s*([QH]\d)', period_name)
        if match:
            year = 2000 + int(match.group(1))
            period_suffix = match.group(2)  # Q1, Q2, H1, etc.
            period_id = f"{year}-{period_suffix}"

    is_current = period_name == current_period if period_name else False

    return {
        'suggested_type': 'current' if is_current else 'historical',
        'period_id': period_id,
        'period_display': period_name or 'Unknown',
        'current_period': current_period,
        'is_current_period': is_current
    }


def extract_workday_metadata(rows: List[tuple], header_idx: int) -> Dict[str, Any]:
    """
    Extract metadata from Workday export header rows.

    The extended Workday format includes:
    - Row 1: Report title with period info (e.g., "Associate Awards:: ... Bonus - CY25 Q3")
    - Row 4: Budget summary (type, total spend, "of", total pool, %, style, currency)

    Args:
        rows: All rows from the spreadsheet
        header_idx: Index of the header row (metadata is above this)

    Returns:
        Dict with:
            - period_name: str or None (e.g., "CY25 Q3")
            - total_pool: float or None (budget amount)
            - currency: str or None (e.g., "USD")
            - report_title: str or None (full title from row 1)
    """
    metadata = {
        'period_name': None,
        'total_pool': None,
        'currency': None,
        'report_title': None,
    }

    if not rows or header_idx < 1:
        return metadata

    # Row 1: Extract report title and period name
    if len(rows) > 0 and rows[0]:
        title = rows[0][0]
        if title and isinstance(title, str):
            metadata['report_title'] = title.strip()
            # Extract period from patterns like "Bonus - CY25 Q3" or "Bonus CY25-H1"
            # Look for common period patterns at the end of the title
            period_patterns = [
                r'[-–]\s*([A-Z]{2}\d{2}\s+[A-Z]\d)',      # "- CY25 Q3"
                r'[-–]\s*([A-Z]{2}\d{2}-[A-Z]\d)',        # "- CY25-Q3"
                r'[-–]\s*(\d{4}\s+[A-Z]\d)',              # "- 2025 Q3"
                r'[-–]\s*(\d{4}-[A-Z]\d)',                # "- 2025-Q3"
                r'[-–]\s*([A-Z]{2}\d{2}\s+H\d)',          # "- CY25 H1"
                r'[-–]\s*(\d{4}\s+H\d)',                  # "- 2025 H1"
            ]
            for pattern in period_patterns:
                match = re.search(pattern, title)
                if match:
                    metadata['period_name'] = match.group(1).strip()
                    break

    # Row 4 (index 3): Budget summary row
    # Format: [type, total_spend, "of", total_pool, %, style, currency, ...]
    if len(rows) > 3 and rows[3]:
        budget_row = rows[3]

        # Check if this looks like the budget row (first cell is "Bonus" or similar)
        if budget_row[0] and isinstance(budget_row[0], str):
            first_cell = budget_row[0].lower().strip()
            if first_cell in ('bonus', 'merit', 'compensation'):
                # Extract total pool (column 4, index 3)
                if len(budget_row) > 3 and budget_row[3]:
                    pool_val = budget_row[3]
                    if isinstance(pool_val, (int, float)):
                        metadata['total_pool'] = float(pool_val)
                    elif isinstance(pool_val, str):
                        # Parse formatted number like "210,910.07"
                        try:
                            cleaned = pool_val.replace(',', '').strip()
                            metadata['total_pool'] = float(cleaned)
                        except (ValueError, TypeError):
                            pass

                # Extract currency (column 7, index 6)
                if len(budget_row) > 6 and budget_row[6]:
                    currency = budget_row[6]
                    if isinstance(currency, str) and len(currency) == 3 and currency.isalpha():
                        metadata['currency'] = currency.upper()

    return metadata


def validate_workday_format(rows: List[tuple], header_idx: Optional[int], headers: List[str], metadata: Dict[str, Any] = None) -> Tuple[bool, str]:
    """
    Validate that the file is a proper Workday export with required metadata.

    Checks:
    1. Header row was found
    2. Required columns exist (Associate, Associate ID)
    3. At least one data row exists
    4. Workday metadata present (period name, bonus pool) - new format required

    Args:
        rows: All rows from the spreadsheet
        header_idx: Index of the header row (or None if not found)
        headers: List of header strings (empty if header_idx is None)
        metadata: Optional pre-extracted metadata dict

    Returns:
        Tuple of (is_valid, error_message)
    """
    if header_idx is None:
        # Try to give a helpful error message
        sample_headers = []
        for row in rows[:5]:
            if row:
                non_empty = [str(c)[:30] for c in row[:5] if c]
                if non_empty:
                    sample_headers = non_empty
                    break

        return False, (
            "Could not find expected Workday columns.\n\n"
            "Expected columns: Associate, Associate ID, Supervisory Organization, "
            "Current Job Profile, Currency, Bonus Target - Local Currency\n\n"
            f"Found in file: {', '.join(sample_headers) if sample_headers else '(empty)'}\n\n"
            "Please export from Workday using the standard bonus allocation report."
        )

    # Check for required columns
    # Note: Talent reports use 'Worker' instead of 'Associate'
    normalized = [h.lower().strip() for h in headers if h]

    missing = []
    if 'associate' not in normalized and 'worker' not in normalized:
        missing.append('Associate (or Worker)')
    if 'associate id' not in normalized:
        missing.append('Associate ID')

    if missing:
        return False, f"Missing required columns: {', '.join(missing)}"

    # Check for data rows
    data_rows = 0
    for row in rows[header_idx + 1:]:
        if not _is_empty_row(row):
            data_rows += 1
            if data_rows >= 1:
                break

    if data_rows == 0:
        return False, "No employee data found after header row"

    # Check for required metadata (new Workday format)
    # Old format files without metadata are no longer supported
    if metadata is not None:
        if not metadata.get('total_pool'):
            return False, (
                "Missing bonus pool metadata.\n\n"
                "This file appears to be using an old export format that lacks required metadata.\n\n"
                "Please export a fresh file from Workday - the current export format includes:\n"
                "  • Row 1: Report title with period (e.g., 'Associate Awards:: ... Bonus - CY25 Q1')\n"
                "  • Row 4: Budget summary with total pool amount\n\n"
                "The bonus pool from Workday metadata is required for accurate calculations."
            )

    return True, ''


def _find_header_row(rows: List[tuple]) -> Optional[int]:
    """
    Find the header row by looking for required Workday column names.

    Scans rows until it finds one containing 'Associate ID' and either
    'Associate' or 'Worker' (case-insensitive). Bonus reports use 'Associate',
    while talent reports use 'Worker'.

    Args:
        rows: List of row tuples from the spreadsheet

    Returns:
        Index of the header row, or None if not found
    """
    for idx, row in enumerate(rows):
        if not row:
            continue
        # Normalize cell values for comparison
        normalized = {str(cell).lower().strip() for cell in row if cell}

        # Must have 'associate id' AND either 'associate' OR 'worker'
        has_id = 'associate id' in normalized
        has_name = 'associate' in normalized or 'worker' in normalized

        if has_id and has_name:
            return idx

    return None


def _is_empty_row(row: tuple) -> bool:
    """
    Check if a row is empty (all cells are None or whitespace-only strings).

    Args:
        row: Row tuple from the spreadsheet

    Returns:
        True if the row is empty, False otherwise
    """
    if not row:
        return True
    return all(cell is None or (isinstance(cell, str) and not cell.strip()) for cell in row)


def analyze_xlsx(file_path: str) -> Dict[str, Any]:
    """
    Analyze an XLSX file and return metadata about its contents.

    Args:
        file_path: Path to the XLSX file

    Returns:
        Dict with:
            - success: bool
            - employee_count: int
            - has_bonus_column: bool (has 'Proposed Percent of Target Bonus')
            - notes_count: int (employees with Notes field)
            - partial_count: int (employees with bonus but no notes/rating)
            - columns: list of column headers
            - error: str (if success is False)
            - metadata: dict with period_name, total_pool, currency, report_title
    """
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True)
        sheet = wb.active

        rows = list(sheet.iter_rows(values_only=True))

        # Find the header row dynamically
        header_idx = _find_header_row(rows)
        headers = [str(h).strip() if h else '' for h in rows[header_idx]] if header_idx is not None else []

        # Detect spreadsheet type (talent vs bonus)
        spreadsheet_type = detect_spreadsheet_type(headers) if headers else 'bonus'

        # Extract metadata from header rows (needed for validation of bonus files)
        metadata = extract_workday_metadata(rows, header_idx) if header_idx is not None else {}

        # Validate the file format
        # For talent files, skip metadata validation (they don't have bonus pool)
        validation_metadata = None if spreadsheet_type == 'talent' else metadata
        is_valid, validation_error = validate_workday_format(rows, header_idx, headers, validation_metadata)
        if not is_valid:
            wb.close()
            return {
                'success': False,
                'error': validation_error
            }

        # Count employees (data rows start after header)
        employee_count = 0
        notes_count = 0
        allocation_count = 0  # Employees with proposed bonus allocation

        # Find column indices
        col_indices = find_column_indices(headers)

        for row in rows[header_idx + 1:]:
            # Skip empty rows
            if _is_empty_row(row):
                continue

            # Skip rows without an associate value
            associate_idx = col_indices.get('associate')
            if associate_idx is not None:
                associate_val = row[associate_idx] if associate_idx < len(row) else None
                if not associate_val or (isinstance(associate_val, str) and not associate_val.strip()):
                    continue

            employee_count += 1

            # Check for notes
            notes_idx = col_indices.get('notes')
            if notes_idx is not None and notes_idx < len(row) and row[notes_idx]:
                notes_count += 1

            # Check for bonus allocation
            bonus_idx = col_indices.get('proposed_percent_of_target')
            if bonus_idx is not None and bonus_idx < len(row) and row[bonus_idx]:
                allocation_count += 1

        wb.close()

        # Suggest import type based on period
        import_detection = detect_import_type(metadata.get('period_name'))

        return {
            'success': True,
            'employee_count': employee_count,
            'spreadsheet_type': spreadsheet_type,  # 'talent' or 'bonus'
            'has_bonus_column': col_indices.get('proposed_percent_of_target') is not None,
            'notes_count': notes_count,
            'allocation_count': allocation_count,
            'columns': headers,
            'metadata': metadata,
            'import_detection': import_detection
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def find_column_indices(headers: List[str]) -> Dict[str, Optional[int]]:
    """
    Find column indices for known Workday export fields.

    Workday exports use the MANAGER'S home currency for conversion columns.
    For example, an Australian manager sees "(AUD)" columns, a US manager
    sees "(USD)" columns. This function uses regex to match any 3-letter
    currency code in parentheses.

    Args:
        headers: List of header strings

    Returns:
        Dict mapping field names to column indices (or None if not found)
    """
    # Normalize headers for matching
    normalized = [h.lower().strip() if h else '' for h in headers]

    indices = {}

    # Map of field name -> possible header variations
    # Variations with currency codes use regex patterns (marked with 're:' prefix)
    field_mappings = {
        'associate': ['associate'],
        'associate_id': ['associate id'],
        'supervisory_org': ['supervisory organization'],
        'job_profile': ['current job profile'],
        'photo': ['photo'],
        'errors': ['errors'],
        'base_pay': ['current base pay - all countries', 'current base pay all countries'],
        # Match any 3-letter currency code: (USD), (AUD), (GBP), (EUR), etc.
        'base_pay_converted': [
            're:current base pay - all countries \\([a-z]{3}\\)',
            're:current base pay all countries \\([a-z]{3}\\)'
        ],
        'currency': ['currency'],
        'grade': ['grade'],
        'annual_bonus_target': ['annual bonus target %', 'annual bonus target percent'],
        'last_bonus_allocation': ['last bonus allocation %', 'last bonus allocation percent'],
        'bonus_target_local': ['bonus target - local currency', 'bonus target local currency'],
        'bonus_target_converted': [
            're:bonus target - local currency \\([a-z]{3}\\)',
            're:bonus target local currency \\([a-z]{3}\\)'
        ],
        'proposed_bonus': ['proposed bonus amount'],
        'proposed_bonus_converted': ['re:proposed bonus amount \\([a-z]{3}\\)'],
        'proposed_percent_of_target': ['proposed % of target bonus', 'proposed percent of target bonus'],
        'notes': ['notes', 'single description'],
        'zero_bonus': ['zero bonus allocated'],
    }

    for field, variations in field_mappings.items():
        for var in variations:
            if var.startswith('re:'):
                # Regex pattern matching
                pattern = var[3:]  # Remove 're:' prefix
                for idx, header in enumerate(normalized):
                    if re.match(pattern, header):
                        indices[field] = idx
                        break
                if field in indices:
                    break
            else:
                # Exact string matching
                try:
                    idx = normalized.index(var)
                    indices[field] = idx
                    break
                except ValueError:
                    continue
        if field not in indices:
            indices[field] = None

    return indices


def parse_xlsx_employees(file_path: str) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Parse all employee data from a Workday XLSX export.

    Args:
        file_path: Path to the XLSX file

    Returns:
        Tuple of (success, employees_list, error_message)
        employees_list contains dicts with all parsed fields
    """
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True)
        sheet = wb.active

        rows = list(sheet.iter_rows(values_only=True))

        # Find the header row dynamically
        header_idx = _find_header_row(rows)
        headers = [str(h).strip() if h else '' for h in rows[header_idx]] if header_idx is not None else []

        # Extract metadata from header rows (needed for validation)
        metadata = extract_workday_metadata(rows, header_idx) if header_idx is not None else {}

        # Validate the file format (including metadata check)
        is_valid, validation_error = validate_workday_format(rows, header_idx, headers, metadata)
        if not is_valid:
            wb.close()
            return False, [], validation_error

        col_indices = find_column_indices(headers)

        employees = []

        for i, row in enumerate(rows[header_idx + 1:], start=header_idx + 1):
            # Skip empty rows
            if _is_empty_row(row):
                continue

            # Skip rows without an associate value
            associate_idx = col_indices.get('associate')
            if associate_idx is not None:
                associate_val = row[associate_idx] if associate_idx < len(row) else None
                if not associate_val or (isinstance(associate_val, str) and not associate_val.strip()):
                    continue

            # Get associate ID (required)
            assoc_id_idx = col_indices.get('associate_id')
            if assoc_id_idx is not None and assoc_id_idx < len(row) and row[assoc_id_idx]:
                associate_id = str(row[assoc_id_idx])
            else:
                associate_id = f"TEMP_{i}"

            # Build employee dict
            emp = {
                'associate_id': associate_id,
                'associate': str(row[associate_idx]) if associate_idx is not None and associate_idx < len(row) and row[associate_idx] else '',
                'supervisory_organization': _get_str(row, col_indices.get('supervisory_org')),
                'current_job_profile': _get_str(row, col_indices.get('job_profile')),
                'photo': _get_str(row, col_indices.get('photo')),
                'errors': _get_str(row, col_indices.get('errors')),
                'current_base_pay_all_countries': parse_float(_get_val(row, col_indices.get('base_pay'))),
                'current_base_pay_manager_currency': parse_float(_get_val(row, col_indices.get('base_pay_converted'))),
                'currency': _get_str(row, col_indices.get('currency')),
                'grade': _get_str(row, col_indices.get('grade')),
                'annual_bonus_target_percent': parse_float(_get_val(row, col_indices.get('annual_bonus_target'))),
                'last_bonus_allocation_percent': parse_float(_get_val(row, col_indices.get('last_bonus_allocation'))),
                'bonus_target_local_currency': parse_float(_get_val(row, col_indices.get('bonus_target_local'))),
                'bonus_target_manager_currency': parse_float(_get_val(row, col_indices.get('bonus_target_converted'))),
                'proposed_bonus_amount': parse_float(_get_val(row, col_indices.get('proposed_bonus'))),
                'proposed_bonus_amount_manager_currency': parse_float(_get_val(row, col_indices.get('proposed_bonus_converted'))),
                'proposed_percent_of_target_bonus': parse_float(_get_val(row, col_indices.get('proposed_percent_of_target'))),
                'notes': _get_str(row, col_indices.get('notes')),
                'zero_bonus_allocated': _get_str(row, col_indices.get('zero_bonus')),
            }

            employees.append(emp)

        wb.close()
        return True, employees, ''

    except Exception as e:
        return False, [], str(e)


def _get_val(row: tuple, idx: Optional[int]) -> Any:
    """Safely get a value from a row by index."""
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def _get_str(row: tuple, idx: Optional[int]) -> str:
    """Safely get a string value from a row by index."""
    val = _get_val(row, idx)
    return str(val) if val else ''


# ═══════════════════════════════════════════════════════════════════════════════
# TALENT CALIBRATION IMPORT SUPPORT
# ═══════════════════════════════════════════════════════════════════════════════

# Markers used to detect spreadsheet type
TALENT_MARKERS = ['Performance: What', 'Performance: How', 'Future Talent', 'Movement Readiness']
BONUS_MARKERS = ['Bonus Target', 'Annual Bonus Target Percent', 'Current Base Pay', 'Proposed Bonus Amount']


def detect_spreadsheet_type(headers: List[str]) -> str:
    """
    Detect whether a spreadsheet is a talent calibration or bonus report.

    Uses marker columns to determine the type. Talent reports have columns like
    "Performance: What" and "Movement Readiness". Bonus reports have columns
    like "Bonus Target" and "Proposed Bonus Amount".

    Args:
        headers: List of column header strings

    Returns:
        'talent' or 'bonus'
    """
    text = ' '.join(str(h) for h in headers if h)
    talent_score = sum(1 for m in TALENT_MARKERS if m in text)
    bonus_score = sum(1 for m in BONUS_MARKERS if m in text)
    return 'talent' if talent_score > bonus_score else 'bonus'


# Talent column mappings (Spec §5.2)
# Maps Workday column headers to database field names
TALENT_COLUMN_MAP = {
    # Identity (Worker and Associate both map to associate)
    'Associate ID': 'associate_id',
    'Worker': 'associate',
    'Associate': 'associate',

    # Standard context (shared with bonus)
    'Supervisory Organization': 'supervisory_organization',
    'Job Profile': 'current_job_profile',
    'Current Job Profile': 'current_job_profile',

    # Performance Assessment
    'Performance: What': 'talent_perf_what',
    'Performance: How': 'talent_perf_how',
    'Overall Performance Rating': 'talent_overall_perf',
    'Last Talent Assessment Cycle: Overall Performance Rating': 'talent_last_overall_perf',

    # Future Talent
    'Future Talent: Growth Agility': 'talent_growth_agility',
    'Future Talent: Change Agility': 'talent_change_agility',
    'Identified as Future Talent?': 'talent_identified_future',
    'Last Talent Assessment Cycle: Identified as Future Talent?': 'talent_last_identified_future',

    # Movement & Career
    'Movement Readiness': 'talent_movement_readiness',
    'Last Talent Assessment Cycle: Movement Readiness': 'talent_last_movement_readiness',
    'Proposed Talent Actions': 'talent_proposed_actions',

    # Promotion
    'Promotions: Proposed Job Profile & Code': 'talent_promo_job_profile',
    'Promotions: Business Need': 'talent_promo_business_need',
    'Promotions: Expanded Role Scope': 'talent_promo_role_scope',
    'Promotions: Associate Readiness': 'talent_promo_readiness',

    # Extended Identity Context
    'Time in Job Profile': 'time_in_job_profile',
    'Management Level': 'management_level',
    'Job Category': 'job_category',
    'Hire Date': 'hire_date',
    'Length of Service - Worker': 'length_of_service',
    'Region - Location Based': 'region',
    'Country': 'country',

    # Metadata
    'Calibration Status': 'talent_calibration_status',
}


def find_talent_column_indices(headers: List[str]) -> Dict[str, Optional[int]]:
    """
    Find column indices for talent calibration fields.

    Uses TALENT_COLUMN_MAP to map Workday column headers to field names.

    Args:
        headers: List of header strings

    Returns:
        Dict mapping field names to column indices (or None if not found)
    """
    indices = {}

    # Normalize headers for matching
    header_lower = [h.lower().strip() if h else '' for h in headers]
    header_exact = [h.strip() if h else '' for h in headers]

    for workday_col, field_name in TALENT_COLUMN_MAP.items():
        # Try exact match first (case-sensitive for Workday columns)
        if workday_col in header_exact:
            idx = header_exact.index(workday_col)
            # Don't overwrite if already found (first match wins)
            if field_name not in indices:
                indices[field_name] = idx
        else:
            # Fall back to case-insensitive match
            workday_col_lower = workday_col.lower()
            if workday_col_lower in header_lower:
                idx = header_lower.index(workday_col_lower)
                if field_name not in indices:
                    indices[field_name] = idx

    return indices


def parse_talent_xlsx_employees(file_path: str) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Parse employee talent calibration data from a Workday XLSX export.

    Unlike bonus imports, talent imports:
    - Don't require bonus pool metadata
    - Map different columns (Performance What/How, Movement Readiness, etc.)
    - Can create new employees if associate_id not found in database

    Args:
        file_path: Path to the XLSX file

    Returns:
        Tuple of (success, employees_list, error_message)
        employees_list contains dicts with talent calibration fields
    """
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True)
        sheet = wb.active

        rows = list(sheet.iter_rows(values_only=True))

        # Find the header row dynamically
        header_idx = _find_header_row(rows)
        if header_idx is None:
            wb.close()
            return False, [], "Could not find header row with Associate and Associate ID columns"

        headers = [str(h).strip() if h else '' for h in rows[header_idx]]

        # Verify this is a talent spreadsheet
        spreadsheet_type = detect_spreadsheet_type(headers)
        if spreadsheet_type != 'talent':
            wb.close()
            return False, [], (
                "This appears to be a bonus spreadsheet, not a talent calibration report.\n\n"
                "Expected columns like: Performance: What, Performance: How, Movement Readiness\n\n"
                "Please import this file through the standard import process."
            )

        col_indices = find_talent_column_indices(headers)

        employees = []

        for i, row in enumerate(rows[header_idx + 1:], start=header_idx + 1):
            # Skip empty rows
            if _is_empty_row(row):
                continue

            # Get associate value (required)
            associate_idx = col_indices.get('associate')
            if associate_idx is not None:
                associate_val = row[associate_idx] if associate_idx < len(row) else None
                if not associate_val or (isinstance(associate_val, str) and not associate_val.strip()):
                    continue

            # Get associate ID (required)
            assoc_id_idx = col_indices.get('associate_id')
            if assoc_id_idx is not None and assoc_id_idx < len(row) and row[assoc_id_idx]:
                associate_id = str(row[assoc_id_idx])
            else:
                associate_id = f"TEMP_{i}"

            # Parse hire_date as datetime if present
            hire_date_val = _get_val(row, col_indices.get('hire_date'))
            hire_date = None
            if hire_date_val:
                if isinstance(hire_date_val, datetime):
                    hire_date = hire_date_val
                elif isinstance(hire_date_val, str):
                    try:
                        # Try common date formats
                        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                            try:
                                hire_date = datetime.strptime(hire_date_val.strip(), fmt)
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass

            # Parse boolean for identified_future
            identified_future_val = _get_val(row, col_indices.get('talent_identified_future'))
            talent_identified_future = None
            if identified_future_val is not None:
                if isinstance(identified_future_val, bool):
                    talent_identified_future = identified_future_val
                elif isinstance(identified_future_val, str):
                    val_lower = identified_future_val.strip().lower()
                    if val_lower in ('yes', 'true', '1'):
                        talent_identified_future = True
                    elif val_lower in ('no', 'false', '0'):
                        talent_identified_future = False

            # Parse last_identified_future similarly
            last_identified_val = _get_val(row, col_indices.get('talent_last_identified_future'))
            talent_last_identified_future = None
            if last_identified_val is not None:
                if isinstance(last_identified_val, bool):
                    talent_last_identified_future = last_identified_val
                elif isinstance(last_identified_val, str):
                    val_lower = last_identified_val.strip().lower()
                    if val_lower in ('yes', 'true', '1'):
                        talent_last_identified_future = True
                    elif val_lower in ('no', 'false', '0'):
                        talent_last_identified_future = False

            # Build employee dict
            emp = {
                'associate_id': associate_id,
                'associate': str(row[associate_idx]) if associate_idx is not None and associate_idx < len(row) and row[associate_idx] else '',
                'supervisory_organization': _get_str(row, col_indices.get('supervisory_organization')),
                'current_job_profile': _get_str(row, col_indices.get('current_job_profile')),

                # Extended identity
                'management_level': _get_str(row, col_indices.get('management_level')),
                'job_category': _get_str(row, col_indices.get('job_category')),
                'hire_date': hire_date,
                'length_of_service': _get_str(row, col_indices.get('length_of_service')),
                'time_in_job_profile': _get_str(row, col_indices.get('time_in_job_profile')),
                'region': _get_str(row, col_indices.get('region')),
                'country': _get_str(row, col_indices.get('country')),

                # Performance Assessment
                'talent_perf_what': _get_str(row, col_indices.get('talent_perf_what')),
                'talent_perf_how': _get_str(row, col_indices.get('talent_perf_how')),
                'talent_overall_perf': _get_str(row, col_indices.get('talent_overall_perf')),
                'talent_last_overall_perf': _get_str(row, col_indices.get('talent_last_overall_perf')),

                # Future Talent
                'talent_growth_agility': _get_str(row, col_indices.get('talent_growth_agility')),
                'talent_change_agility': _get_str(row, col_indices.get('talent_change_agility')),
                'talent_identified_future': talent_identified_future,
                'talent_last_identified_future': talent_last_identified_future,

                # Movement & Career
                'talent_movement_readiness': _get_str(row, col_indices.get('talent_movement_readiness')),
                'talent_last_movement_readiness': _get_str(row, col_indices.get('talent_last_movement_readiness')),
                'talent_proposed_actions': _get_str(row, col_indices.get('talent_proposed_actions')),

                # Promotion
                'talent_promo_job_profile': _get_str(row, col_indices.get('talent_promo_job_profile')),
                'talent_promo_business_need': _get_str(row, col_indices.get('talent_promo_business_need')),
                'talent_promo_role_scope': _get_str(row, col_indices.get('talent_promo_role_scope')),
                'talent_promo_readiness': _get_str(row, col_indices.get('talent_promo_readiness')),

                # Metadata
                'talent_calibration_status': _get_str(row, col_indices.get('talent_calibration_status')),
            }

            employees.append(emp)

        wb.close()
        return True, employees, ''

    except Exception as e:
        return False, [], str(e)
