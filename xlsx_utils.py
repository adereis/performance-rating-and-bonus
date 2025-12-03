"""
Utilities for parsing Workday XLSX exports.

This module provides functions for:
- Analyzing XLSX files (counting employees, detecting columns)
- Parsing employee data from Workday exports
- Creating Employee records from parsed data
"""
import openpyxl
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime


def parse_float(val) -> Optional[float]:
    """Safely parse a value to float."""
    try:
        return float(val) if val else None
    except (ValueError, TypeError):
        return None


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

        if len(rows) < 2:
            return {
                'success': False,
                'error': 'Not enough data in Excel file'
            }

        # Row 1 (index 1) contains the actual headers
        headers = [str(h).strip() if h else '' for h in rows[1]]

        # Count employees (data rows)
        employee_count = 0
        notes_count = 0
        partial_count = 0

        # Find column indices
        col_indices = find_column_indices(headers)

        for row in rows[2:]:
            if not row or (col_indices['associate'] is not None and not row[col_indices['associate']]):
                continue

            employee_count += 1

            # Check for notes
            notes_idx = col_indices.get('notes')
            if notes_idx is not None and row[notes_idx]:
                notes_count += 1

            # Check for partial data (has bonus allocation but no notes)
            bonus_idx = col_indices.get('proposed_percent_of_target')
            if bonus_idx is not None and row[bonus_idx]:
                if notes_idx is None or not row[notes_idx]:
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

    Args:
        headers: List of header strings

    Returns:
        Dict mapping field names to column indices (or None if not found)
    """
    # Normalize headers for matching
    normalized = [h.lower().strip() if h else '' for h in headers]

    indices = {}

    # Map of field name -> possible header variations
    field_mappings = {
        'associate': ['associate'],
        'associate_id': ['associate id'],
        'supervisory_org': ['supervisory organization'],
        'job_profile': ['current job profile'],
        'photo': ['photo'],
        'errors': ['errors'],
        'base_pay': ['current base pay - all countries', 'current base pay all countries'],
        'base_pay_usd': ['current base pay - all countries (usd)', 'current base pay all countries (usd)'],
        'currency': ['currency'],
        'grade': ['grade'],
        'annual_bonus_target': ['annual bonus target %', 'annual bonus target percent'],
        'last_bonus_allocation': ['last bonus allocation %', 'last bonus allocation percent'],
        'bonus_target_local': ['bonus target - local currency', 'bonus target local currency'],
        'bonus_target_usd': ['bonus target - local currency (usd)', 'bonus target local currency (usd)'],
        'proposed_bonus': ['proposed bonus amount'],
        'proposed_bonus_usd': ['proposed bonus amount (usd)'],
        'proposed_percent_of_target': ['proposed % of target bonus', 'proposed percent of target bonus'],
        'notes': ['notes', 'single description'],
        'zero_bonus': ['zero bonus allocated'],
    }

    for field, variations in field_mappings.items():
        for var in variations:
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

        if len(rows) < 2:
            return False, [], 'Not enough data in Excel file'

        # Row 1 (index 1) contains the actual headers
        headers = [str(h).strip() if h else '' for h in rows[1]]
        col_indices = find_column_indices(headers)

        employees = []

        for i, row in enumerate(rows[2:], start=2):
            # Skip empty rows
            associate_idx = col_indices.get('associate')
            if not row or (associate_idx is not None and not row[associate_idx]):
                continue

            # Get associate ID (required)
            assoc_id_idx = col_indices.get('associate_id')
            if assoc_id_idx is not None and row[assoc_id_idx]:
                associate_id = str(row[assoc_id_idx])
            else:
                associate_id = f"TEMP_{i}"

            # Build employee dict
            emp = {
                'associate_id': associate_id,
                'associate': str(row[associate_idx]) if associate_idx is not None and row[associate_idx] else '',
                'supervisory_organization': _get_str(row, col_indices.get('supervisory_org')),
                'current_job_profile': _get_str(row, col_indices.get('job_profile')),
                'photo': _get_str(row, col_indices.get('photo')),
                'errors': _get_str(row, col_indices.get('errors')),
                'current_base_pay_all_countries': parse_float(_get_val(row, col_indices.get('base_pay'))),
                'current_base_pay_all_countries_usd': parse_float(_get_val(row, col_indices.get('base_pay_usd'))),
                'currency': _get_str(row, col_indices.get('currency')),
                'grade': _get_str(row, col_indices.get('grade')),
                'annual_bonus_target_percent': parse_float(_get_val(row, col_indices.get('annual_bonus_target'))),
                'last_bonus_allocation_percent': parse_float(_get_val(row, col_indices.get('last_bonus_allocation'))),
                'bonus_target_local_currency': parse_float(_get_val(row, col_indices.get('bonus_target_local'))),
                'bonus_target_local_currency_usd': parse_float(_get_val(row, col_indices.get('bonus_target_usd'))),
                'proposed_bonus_amount': parse_float(_get_val(row, col_indices.get('proposed_bonus'))),
                'proposed_bonus_amount_usd': parse_float(_get_val(row, col_indices.get('proposed_bonus_usd'))),
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
