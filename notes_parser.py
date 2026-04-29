"""
Parser for the Single Description / Notes field format.

This module parses the structured text format used in exports to Workday
and reconstructs the original rating data for historical imports.

Export format:

    Tool Additions - Parsed on re-import:
        [Performance Rating: 125%]
        [Override: 50%, Paternity leave Apr-Sep]  (optional, reason optional)
        [Strengths: Tenet Name 1; Tenet Name 2; Tenet Name 3]
        [Improvements: Tenet Name 1; Tenet Name 2]
        [Mentor: Name of mentor]
        [Mentees: Name1; Name2]

        Justification:
        Multi-line text describing the rating.
        Can span multiple paragraphs.

Format notes:
    - Single-value fields use brackets [Field: value] for unambiguous parsing
    - Justification uses section header format (allows multi-line, any characters)
    - The [Performance Rating] field is the source of truth for calculations
"""

import re
from typing import Optional


def parse_notes_field(notes_text: Optional[str]) -> dict:
    """
    Parse structured Notes field into components.

    Args:
        notes_text: The raw text from the Notes/Single Description field

    Returns:
        dict with keys:
            - performance_rating: float or None (e.g., 125.0 for "125%")
            - justification: str or None
            - tenets_strengths: str or None (comma-separated names)
            - tenets_improvements: str or None (comma-separated names)
            - mentors: str or None
            - mentees: str or None
            - bonus_override_percent: float or None (e.g., 50.0 for "50%")
            - special_case_notes: str or None (e.g., "Paternity leave Apr-Sep")

    Handles variations in formatting gracefully. Missing fields return None.
    """
    if not notes_text or not notes_text.strip():
        return {
            'performance_rating': None,
            'justification': None,
            'tenets_strengths': None,
            'tenets_improvements': None,
            'mentors': None,
            'mentees': None,
            'bonus_override_percent': None,
            'special_case_notes': None,
        }

    result = {
        'performance_rating': None,
        'justification': None,
        'tenets_strengths': None,
        'tenets_improvements': None,
        'mentors': None,
        'mentees': None,
        'bonus_override_percent': None,
        'special_case_notes': None,
    }

    # Normalize line endings
    text = notes_text.replace('\r\n', '\n').replace('\r', '\n')

    # Parse Performance Rating: [Performance Rating: X%]
    rating_match = re.search(r'\[Performance\s+Rating:\s*([\d.]+)\s*%\]', text, re.IGNORECASE)
    if rating_match:
        try:
            result['performance_rating'] = float(rating_match.group(1))
        except ValueError:
            pass

    # Parse Mentor: [Mentor: X]
    mentor_match = re.search(r'\[Mentor:\s*([^\]]+)\]', text, re.IGNORECASE)
    if mentor_match:
        mentor_value = mentor_match.group(1).strip()
        if mentor_value:
            result['mentors'] = mentor_value

    # Parse Mentees: [Mentees: X; Y]
    mentees_match = re.search(r'\[Mentees?:\s*([^\]]+)\]', text, re.IGNORECASE)
    if mentees_match:
        mentees_value = mentees_match.group(1).strip()
        if mentees_value:
            result['mentees'] = mentees_value

    # Parse Strengths: [Strengths: X; Y]
    strengths_match = re.search(r'\[Strengths?:\s*([^\]]+)\]', text, re.IGNORECASE)
    if strengths_match:
        strengths_value = strengths_match.group(1).strip()
        if strengths_value:
            result['tenets_strengths'] = strengths_value

    # Parse Improvements: [Improvements: X; Y]
    improvements_match = re.search(r'\[Improvements?:\s*([^\]]+)\]', text, re.IGNORECASE)
    if improvements_match:
        improvements_value = improvements_match.group(1).strip()
        if improvements_value:
            result['tenets_improvements'] = improvements_value

    # [Override: 50%] or [Override: 50%, Paternity leave Apr-Sep]
    # Combined format: percentage required, reason optional after comma
    override_match = re.search(r'\[Override:\s*([\d.]+)\s*%(?:,\s*([^\]]+))?\]', text, re.IGNORECASE)
    if override_match:
        try:
            result['bonus_override_percent'] = float(override_match.group(1))
            if override_match.group(2):
                result['special_case_notes'] = override_match.group(2).strip()
        except ValueError:
            pass

    # --- Parse Justification (multi-line, at the end) ---
    # Format 1: Section header - "Justification:" on its own line, followed by content
    # Format 2: Inline - "Justification: content" on one line (may continue on next lines)
    # Try section header format first
    justification_match = re.search(r'^Justification:\s*$\n(.+)', text, re.MULTILINE | re.IGNORECASE | re.DOTALL)
    if not justification_match:
        # Fallback to inline format: Justification: <content until end, next field, or bracket marker>
        justification_match = re.search(
            r'^Justification:\s*(.+?)(?=^(?:Mentor|Mentees?|Strengths?|Areas?\s+for|Improvements?):|\n\[|\Z)',
            text,
            re.MULTILINE | re.IGNORECASE | re.DOTALL
        )
    if justification_match:
        justification_value = justification_match.group(1).strip()
        if justification_value:
            result['justification'] = justification_value

    return result


def format_notes_field(
    performance_rating: Optional[float] = None,
    justification: Optional[str] = None,
    mentor: Optional[str] = None,
    mentees: Optional[str] = None,
    tenets_strengths: Optional[str] = None,
    tenets_improvements: Optional[str] = None,
    bonus_override_percent: Optional[float] = None,
    special_case_notes: Optional[str] = None,
) -> str:
    """
    Format rating data into the canonical Notes field format.

    This is the inverse of parse_notes_field - it creates the text that will
    be exported to Workday and later parsed back for historical imports.

    Args:
        performance_rating: The rating percentage (e.g., 125.0)
        justification: The justification text
        mentor: Who mentored this employee
        mentees: Who this employee mentored
        tenets_strengths: Comma-separated tenet names for strengths
        tenets_improvements: Comma-separated tenet names for improvements
        bonus_override_percent: Override bonus % for special cases (e.g., 50.0)
        special_case_notes: Reason for override (e.g., "Paternity leave Apr-Sep")

    Returns:
        Formatted string suitable for the Notes field
    """
    lines = []

    # Bracketed fields (tool additions) - order matches app.py export
    if performance_rating is not None:
        lines.append(f"[Performance Rating: {performance_rating:g}%]")

    # Special case override (pro-rata leave, retention, etc.)
    if bonus_override_percent is not None:
        override_fmt = f"{bonus_override_percent:g}"
        if special_case_notes:
            lines.append(f"[Override: {override_fmt}%, {special_case_notes}]")
        else:
            lines.append(f"[Override: {override_fmt}%]")

    if tenets_strengths:
        lines.append(f"[Strengths: {tenets_strengths}]")

    if tenets_improvements:
        lines.append(f"[Improvements: {tenets_improvements}]")

    if mentor:
        lines.append(f"[Mentor: {mentor}]")

    if mentees:
        # Normalize to semicolon-separated for consistency with tenets
        normalized_mentees = '; '.join(m.strip() for m in mentees.replace(';', ',').split(',') if m.strip())
        lines.append(f"[Mentees: {normalized_mentees}]")

    # Justification uses section header format (allows multi-line, any characters)
    if justification:
        lines.append('')  # Blank line before section
        lines.append('Justification:')
        lines.append(justification)

    return '\n'.join(lines)
