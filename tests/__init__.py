"""
Test suite for the Performance Rating System.
"""
import os

# CRITICAL: Set testing flag BEFORE any test module imports app/models.
# Python loads __init__.py first when importing from a package, guaranteeing
# this runs before test_*.py module-level imports like "from app import ...".
#
# This complements the same protection in conftest.py (for pytest runs).
os.environ['TESTING'] = 'true'
