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


def _find_header_row(rows: List[tuple]) -> Optional[int]:
    """
    Find the header row by looking for required Workday column names.

    Scans rows until it finds one containing 'Associate' and 'Associate ID'
    (case-insensitive), which are required columns in Workday exports.

    Args:
        rows: List of row tuples from the spreadsheet

    Returns:
        Index of the header row, or None if not found
    """
    required_headers = {'associate', 'associate id'}

    for idx, row in enumerate(rows):
        if not row:
            continue
        # Normalize cell values for comparison
        normalized = {str(cell).lower().strip() for cell in row if cell}
        if required_headers.issubset(normalized):
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
    """
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True)
        sheet = wb.active

        rows = list(sheet.iter_rows(values_only=True))

        # Find the header row dynamically
        header_idx = _find_header_row(rows)
        if header_idx is None:
            wb.close()
            return {
                'success': False,
                'error': 'Could not find header row with required columns (Associate, Associate ID)'
            }

        if header_idx >= len(rows) - 1:
            wb.close()
            return {
                'success': False,
                'error': 'No data rows found after header'
            }

        headers = [str(h).strip() if h else '' for h in rows[header_idx]]

        # Count employees (data rows start after header)
        employee_count = 0
        notes_count = 0
        partial_count = 0

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

            # Check for partial data (has bonus allocation but no notes)
            bonus_idx = col_indices.get('proposed_percent_of_target')
            if bonus_idx is not None and bonus_idx < len(row) and row[bonus_idx]:
                if notes_idx is None or notes_idx >= len(row) or not row[notes_idx]:
                    partial_count += 1

        wb.close()

        return {
            'success': True,
            'employee_count': employee_count,
            'has_bonus_column': col_indices.get('proposed_percent_of_target') is not None,
            'notes_count': notes_count,
            'partial_count': partial_count,
            'columns': headers
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
        if header_idx is None:
            wb.close()
            return False, [], 'Could not find header row with required columns (Associate, Associate ID)'

        if header_idx >= len(rows) - 1:
            wb.close()
            return False, [], 'No data rows found after header'

        headers = [str(h).strip() if h else '' for h in rows[header_idx]]
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
