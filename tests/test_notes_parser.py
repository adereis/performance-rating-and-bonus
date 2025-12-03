"""
Tests for the notes_parser module.
"""

import pytest
from notes_parser import parse_notes_field, format_notes_field


class TestParseNotesField:
    """Tests for parse_notes_field function."""

    def test_parse_complete_notes(self):
        """Test parsing a complete notes field with all fields."""
        notes = """Performance Rating: 125.5%
Justification: Great performance, delivered feature X, Y and Z. Role model to the team.
Mentor: Alice Chen
Mentees: Bob Jones, Carol White
Strengths: Customer Obsession, Ownership, Bias for Action
Areas for Improvement: Earn Trust, Dive Deep"""

        result = parse_notes_field(notes)

        assert result['performance_rating'] == 125.5
        assert result['justification'] == "Great performance, delivered feature X, Y and Z. Role model to the team."
        assert result['mentors'] == "Alice Chen"
        assert result['mentees'] == "Bob Jones, Carol White"
        assert result['tenets_strengths'] == "Customer Obsession, Ownership, Bias for Action"
        assert result['tenets_improvements'] == "Earn Trust, Dive Deep"

    def test_parse_rating_only(self):
        """Test parsing notes with only performance rating."""
        notes = "Performance Rating: 100%"

        result = parse_notes_field(notes)

        assert result['performance_rating'] == 100.0
        assert result['justification'] is None
        assert result['mentors'] is None
        assert result['mentees'] is None
        assert result['tenets_strengths'] is None
        assert result['tenets_improvements'] is None

    def test_parse_multiline_justification(self):
        """Test parsing multi-line justification text."""
        notes = """Performance Rating: 130%
Justification: This employee demonstrated exceptional performance.
They led the API redesign project which reduced latency by 40%.
Additionally, they mentored two junior engineers.
Mentor: Senior Dev"""

        result = parse_notes_field(notes)

        assert result['performance_rating'] == 130.0
        assert "exceptional performance" in result['justification']
        assert "API redesign" in result['justification']
        assert "junior engineers" in result['justification']
        assert result['mentors'] == "Senior Dev"

    def test_parse_empty_notes(self):
        """Test parsing empty notes returns None for all fields."""
        result = parse_notes_field("")

        assert result['performance_rating'] is None
        assert result['justification'] is None
        assert result['mentors'] is None
        assert result['mentees'] is None
        assert result['tenets_strengths'] is None
        assert result['tenets_improvements'] is None

    def test_parse_none_notes(self):
        """Test parsing None returns None for all fields."""
        result = parse_notes_field(None)

        assert result['performance_rating'] is None
        assert result['justification'] is None

    def test_parse_case_insensitive(self):
        """Test that field names are case-insensitive."""
        notes = """PERFORMANCE RATING: 110%
justification: good work
MENTOR: Boss
strengths: Leadership"""

        result = parse_notes_field(notes)

        assert result['performance_rating'] == 110.0
        assert result['justification'] == "good work"
        assert result['mentors'] == "Boss"
        assert result['tenets_strengths'] == "Leadership"

    def test_parse_rating_with_decimal(self):
        """Test parsing rating with decimal places."""
        notes = "Performance Rating: 115.75%"

        result = parse_notes_field(notes)

        assert result['performance_rating'] == 115.75

    def test_parse_without_rating(self):
        """Test parsing notes without performance rating."""
        notes = """Justification: Solid performance this period.
Strengths: Teamwork, Communication"""

        result = parse_notes_field(notes)

        assert result['performance_rating'] is None
        assert result['justification'] == "Solid performance this period."
        assert result['tenets_strengths'] == "Teamwork, Communication"

    def test_parse_alternate_improvement_phrasings(self):
        """Test parsing various phrasings for improvements."""
        notes1 = "Improvements: Time Management"
        notes2 = "Areas to Improve: Focus"

        result1 = parse_notes_field(notes1)
        result2 = parse_notes_field(notes2)

        assert result1['tenets_improvements'] == "Time Management"
        assert result2['tenets_improvements'] == "Focus"

    def test_parse_windows_line_endings(self):
        """Test parsing notes with Windows line endings."""
        notes = "Performance Rating: 100%\r\nJustification: Test\r\nMentor: Alice"

        result = parse_notes_field(notes)

        assert result['performance_rating'] == 100.0
        assert result['justification'] == "Test"
        assert result['mentors'] == "Alice"

    def test_parse_real_world_example(self):
        """Test parsing a real-world example from the export page."""
        notes = """Performance Rating: 155.0%
Justification: Great performance, delivered feature X, Y and Z. Role model to the team.
Mentor: Rhoda Map
Mentees: Mai Stone
Strengths: We Serve Our Customers, We Champion Ownership, We Start with Trust
Areas for Improvement: We Embrace Transparency, We Navigate Change with Resilience"""

        result = parse_notes_field(notes)

        assert result['performance_rating'] == 155.0
        assert "feature X, Y and Z" in result['justification']
        assert result['mentors'] == "Rhoda Map"
        assert result['mentees'] == "Mai Stone"
        assert "We Serve Our Customers" in result['tenets_strengths']
        assert "We Navigate Change with Resilience" in result['tenets_improvements']


class TestFormatNotesField:
    """Tests for format_notes_field function."""

    def test_format_complete_notes(self):
        """Test formatting with all fields."""
        result = format_notes_field(
            performance_rating=125.0,
            justification="Great work this quarter.",
            mentor="Alice",
            mentees="Bob, Carol",
            tenets_strengths="Leadership, Teamwork",
            tenets_improvements="Communication"
        )

        assert "Performance Rating: 125.0%" in result
        assert "Justification: Great work this quarter." in result
        assert "Mentor: Alice" in result
        assert "Mentees: Bob, Carol" in result
        assert "Strengths: Leadership, Teamwork" in result
        assert "Areas for Improvement: Communication" in result

    def test_format_partial_notes(self):
        """Test formatting with only some fields."""
        result = format_notes_field(
            performance_rating=100.0,
            justification="Met expectations."
        )

        assert "Performance Rating: 100.0%" in result
        assert "Justification: Met expectations." in result
        assert "Mentor:" not in result
        assert "Strengths:" not in result

    def test_format_empty_notes(self):
        """Test formatting with no fields returns empty string."""
        result = format_notes_field()

        assert result == ""

    def test_roundtrip_parse_format(self):
        """Test that formatting then parsing returns original values."""
        original = {
            'performance_rating': 125.5,
            'justification': "Outstanding work.",
            'mentor': "Alice Chen",
            'mentees': "Bob Jones",
            'tenets_strengths': "Leadership, Innovation",
            'tenets_improvements': "Documentation"
        }

        formatted = format_notes_field(
            performance_rating=original['performance_rating'],
            justification=original['justification'],
            mentor=original['mentor'],
            mentees=original['mentees'],
            tenets_strengths=original['tenets_strengths'],
            tenets_improvements=original['tenets_improvements']
        )

        parsed = parse_notes_field(formatted)

        assert parsed['performance_rating'] == original['performance_rating']
        assert parsed['justification'] == original['justification']
        assert parsed['mentors'] == original['mentor']
        assert parsed['mentees'] == original['mentees']
        assert parsed['tenets_strengths'] == original['tenets_strengths']
        assert parsed['tenets_improvements'] == original['tenets_improvements']
