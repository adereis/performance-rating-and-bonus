"""
Regression tests for export page sync detection logic.

These tests verify the "needs sync" system that determines which employees
have pending changes for Workday. The system has two tiers:

1. tool_additions_modified: Any of 6 tracked fields (rating, justification,
   mentor, mentees, tenets_strengths, tenets_improvements) differ from their
   _original value imported from Workday.

2. bonus_allocation_differs: The tool's calculated bonus % differs from
   Workday's Proposed Percent of Target Bonus column.

Combined: needs_sync = tool_additions_modified OR bonus_allocation_differs

REGRESSION CONTEXT: During a refactoring, the Tool Additions box was shown
for ALL employees (gated on tool_additions_text being non-empty) instead of
only those with actual modifications (tool_additions_modified=true). This
caused every employee to appear as having pending changes after a fresh
import, even though their _original fields matched perfectly. The fix gates
the Tool Additions box on tool_additions_modified and hides description
content for bonus-only differences when "Show pending only" is active.
"""
import json
import re

from models import Employee


class TestSyncDetectionFreshImport:
    """Verify that a fresh import with no user changes shows no tool changes.

    After importing a Workday file, all _original fields should match their
    current values. tool_additions_modified must be false for every employee.
    Only bonus_allocation_differs should trigger needs_sync (when the tool's
    curve calculation differs from Workday's proposed bonus).
    """

    def _make_employee(self, db_session, associate_id, rating, proposed_bonus,
                       justification='Good work', mentor='', mentees='',
                       strengths=None, improvements=None):
        """Create an employee simulating a fresh Workday import.

        All _original fields are set to match current values, as the import
        handler does when processing a Workday file for the first time.
        """
        strengths_json = json.dumps(strengths) if strengths else None
        improvements_json = json.dumps(improvements) if improvements else None

        emp = Employee(
            associate_id=associate_id,
            associate=f'Test Employee {associate_id}',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=rating,
            performance_rating_percent_original=rating,
            justification=justification,
            justification_original=justification,
            mentor=mentor,
            mentor_original=mentor,
            mentees=mentees,
            mentees_original=mentees,
            tenets_strengths=strengths_json,
            tenets_strengths_original=strengths_json,
            tenets_improvements=improvements_json,
            tenets_improvements_original=improvements_json,
            proposed_percent_of_target_bonus=proposed_bonus,
        )
        db_session.add(emp)
        return emp

    def test_fresh_import_no_tool_additions_modified(self, client, db_session):
        """After a fresh import, no employee should have tool_additions_modified.

        REGRESSION: Previously the Tool Additions box appeared for every
        employee because it was gated on tool_additions_text (non-empty)
        rather than tool_additions_modified (fields actually changed).
        """
        self._make_employee(db_session, 'E001', 100.0, 100.0,
                            justification='Met all expectations')
        self._make_employee(db_session, 'E002', 110.0, 110.0,
                            mentor='Jane Lead',
                            strengths=['t1', 't2', 't3'],
                            improvements=['t4', 't5'])
        self._make_employee(db_session, 'E003', 90.0, 90.0,
                            mentees='New Hire',
                            justification='Growing steadily')
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        # No row should have data-tool-sync="true"
        assert 'data-tool-sync="true"' not in html, \
            'Fresh import should have no tool additions needing sync'

        # All rows should have data-tool-sync="false"
        tool_sync_false_count = html.count('data-tool-sync="false"')
        assert tool_sync_false_count == 3, \
            f'Expected 3 employees with tool-sync=false, got {tool_sync_false_count}'

    def test_fresh_import_no_tool_additions_box_rendered(self, client, db_session):
        """The Tool Additions box should not render when originals match.

        REGRESSION: The box was previously gated on {% if item.tool_additions_text %}
        which is true for any employee with content (rating, tenets, etc.).
        Now gated on {% if item.tool_additions_modified %}.
        """
        self._make_employee(db_session, 'E001', 105.0, 105.0,
                            justification='Solid contributor',
                            mentor='Senior Dev',
                            strengths=['t1', 't2', 't3'],
                            improvements=['t4', 't5'])
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        # The tool-additions section should not be in the HTML at all
        assert 'class="tool-additions"' not in html, \
            'Tool Additions box should not render when originals match current values'

        # The NEEDS SYNC badge should not appear in any bonus export row
        # (check within the exportTableBody, not the whole page which has
        # CSS/JS definitions and talent export section that may contain it)
        table_match = re.search(
            r'id="exportTableBody">(.*?)</tbody>',
            html,
            re.DOTALL
        )
        if table_match:
            table_html = table_match.group(1)
            assert 'NEEDS SYNC' not in table_html, \
                'NEEDS SYNC badge should not appear in bonus export rows for unmodified employees'

    def test_fresh_import_bonus_matches_no_sync(self, client, db_session):
        """When calculated bonus matches Workday proposed, needs_sync=false.

        Single employee at 100% rating → calculated bonus is exactly 100%.
        With proposed_percent_of_target_bonus=100, they should match.
        """
        self._make_employee(db_session, 'E001', 100.0, 100.0)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        # With a single employee at 100% and proposed=100, nothing should need sync
        assert 'data-needs-sync="true"' not in html, \
            'Employee at 100% with matching proposed bonus should not need sync'
        assert 'data-bonus-differs="true"' not in html, \
            'Bonus should not differ when calculated matches proposed'


class TestSyncDetectionModifiedFields:
    """Verify that modifying specific fields correctly triggers sync flags."""

    def test_rating_modified_triggers_sync(self, client, db_session):
        """Changing performance_rating after import triggers rating_modified."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            # Rating changed from 100 to 110 after import
            performance_rating_percent=110.0,
            performance_rating_percent_original=100.0,
            justification='Updated review',
            justification_original='Updated review',
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        assert 'data-tool-sync="true"' in html, \
            'Modified rating should set tool-sync=true'
        assert 'data-needs-sync="true"' in html, \
            'Modified rating should set needs-sync=true'
        # Tool Additions box should render with NEEDS SYNC badge
        assert 'class="tool-additions"' in html, \
            'Tool Additions box should render for modified employee'
        assert 'NEEDS SYNC' in html, \
            'NEEDS SYNC badge should appear for modified tool additions'
        # Per-field badge for rating
        assert 'Rating needs sync' in html or '⟳</span>Rating' in html, \
            'Rating field-sync-badge should appear'

    def test_justification_modified_triggers_sync(self, client, db_session):
        """Changing justification after import triggers justification_modified."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            proposed_percent_of_target_bonus=100.0,
            justification='New justification text',
            justification_original='Original justification',
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        assert 'data-tool-sync="true"' in html
        assert 'Justification needs sync' in html or \
            '⟳</span>Justification' in html

    def test_mentor_modified_triggers_sync(self, client, db_session):
        """Adding a mentor after import triggers mentor_modified."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            proposed_percent_of_target_bonus=100.0,
            # Mentor added after import (original was empty)
            mentor='New Mentor',
            mentor_original=None,
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        assert 'data-tool-sync="true"' in html
        assert 'Mentor needs sync' in html or \
            '⟳</span>Mentor' in html

    def test_tenets_modified_triggers_sync(self, client, db_session):
        """Changing tenets after import triggers tenets_modified."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            proposed_percent_of_target_bonus=100.0,
            tenets_strengths=json.dumps(['t1', 't2', 't3']),
            tenets_strengths_original=json.dumps(['t1', 't2']),  # Was only 2
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        assert 'data-tool-sync="true"' in html
        assert 'Strengths need sync' in html or \
            '⟳</span>Strengths' in html

    def test_unmodified_employee_among_modified(self, client, db_session):
        """An unmodified employee should not show tool-sync even if others do."""
        # Modified employee
        emp1 = Employee(
            associate_id='E001',
            associate='Alice Modified',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=120.0,
            performance_rating_percent_original=100.0,  # Changed
            proposed_percent_of_target_bonus=100.0,
        )
        # Unmodified employee (originals match)
        emp2 = Employee(
            associate_id='E002',
            associate='Bob Unchanged',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            proposed_percent_of_target_bonus=100.0,
            justification='Same',
            justification_original='Same',
        )
        db_session.add_all([emp1, emp2])
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        # Should have exactly 1 tool-sync=true (Alice) and 1 tool-sync=false (Bob)
        assert html.count('data-tool-sync="true"') == 1
        assert html.count('data-tool-sync="false"') == 1


class TestBonusAllocationDiffers:
    """Verify the bonus allocation comparison logic."""

    def test_bonus_differs_flag_set(self, client, db_session):
        """When calculated bonus differs from Workday, bonus_allocation_differs=true."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            # Workday has a different value than what the tool calculates
            proposed_percent_of_target_bonus=85.0,
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        assert 'data-bonus-differs="true"' in html, \
            'Bonus should be flagged as differing when calculated != proposed'

    def test_bonus_no_workday_value_differs(self, client, db_session):
        """When Workday has no proposed bonus, bonus_allocation_differs=true."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            # No Workday proposed bonus
            proposed_percent_of_target_bonus=None,
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        assert 'data-bonus-differs="true"' in html, \
            'Missing Workday proposed bonus should flag as needing sync'

    def test_bonus_matches_no_flag(self, client, db_session):
        """When calculated bonus matches Workday, bonus_allocation_differs=false."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            # Single employee at 100% → calculated is exactly 100%
            proposed_percent_of_target_bonus=100.0,
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        assert 'data-bonus-differs="false"' in html, \
            'Matching bonus should not be flagged as differing'

    def test_bonus_sync_badge_rendered(self, client, db_session):
        """The ⟳ sync badge should appear next to bonus % when it differs."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            proposed_percent_of_target_bonus=85.0,
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        assert 'Bonus allocation differs from Workday' in html, \
            'Bonus sync badge tooltip should appear when bonus differs'

    def test_bonus_sync_badge_not_rendered_when_matches(self, client, db_session):
        """The ⟳ sync badge should NOT appear when bonus matches Workday."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            proposed_percent_of_target_bonus=100.0,
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        assert 'Bonus allocation differs from Workday' not in html, \
            'Bonus sync badge should NOT appear when bonus matches'


class TestNeedsSyncCombined:
    """Verify the combined needs_sync flag and status bar count."""

    def test_needs_sync_false_when_nothing_changed(self, client, db_session):
        """needs_sync=false when originals match AND bonus matches."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            proposed_percent_of_target_bonus=100.0,
            justification='Solid',
            justification_original='Solid',
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        assert 'data-needs-sync="false"' in html
        assert 'data-needs-sync="true"' not in html
        # Status bar should show 0 pending
        assert '>0</span> of 1 employees need sync' in html or \
            '0</span> of 1' in html

    def test_needs_sync_true_bonus_only(self, client, db_session):
        """needs_sync=true when only bonus differs (tool additions unchanged)."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            proposed_percent_of_target_bonus=85.0,  # Differs
            justification='Same',
            justification_original='Same',
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        # needs_sync should be true (bonus differs)
        assert 'data-needs-sync="true"' in html
        # But tool_additions_modified should be false
        assert 'data-tool-sync="false"' in html
        # Tool Additions box should NOT render (only bonus changed)
        assert 'class="tool-additions"' not in html

    def test_needs_sync_true_tool_additions_only(self, client, db_session):
        """needs_sync=true when only tool additions changed (bonus matches)."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=110.0,
            performance_rating_percent_original=100.0,  # Rating changed
            proposed_percent_of_target_bonus=None,  # Will differ too
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        assert 'data-needs-sync="true"' in html
        assert 'data-tool-sync="true"' in html
        # Tool Additions box SHOULD render
        assert 'class="tool-additions"' in html

    def test_status_bar_count(self, client, db_session):
        """Status bar should count only employees that need sync."""
        # Employee 1: nothing changed
        emp1 = Employee(
            associate_id='E001',
            associate='No Changes',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            proposed_percent_of_target_bonus=100.0,
        )
        # Employee 2: rating changed
        emp2 = Employee(
            associate_id='E002',
            associate='Rating Changed',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=120.0,
            performance_rating_percent_original=100.0,
            proposed_percent_of_target_bonus=100.0,
        )
        db_session.add_all([emp1, emp2])
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        # Depending on whether the pool normalization changes emp1's bonus,
        # at minimum emp2 should need sync. Check the count is reasonable.
        # With 2 employees (100% and 120%), pool normalization will adjust
        # both, so emp1's bonus may now differ from 100. Accept 1 or 2.
        sync_count_match = re.search(
            r'>(\d+)</span>\s*of\s*2\s*employees\s*need\s*sync',
            html
        )
        assert sync_count_match, 'Status bar should show count of 2 employees'
        count = int(sync_count_match.group(1))
        assert count >= 1, 'At least the modified employee should need sync'


class TestDescriptionContentVisibility:
    """Verify that description content is structured for pending-only filtering.

    REGRESSION: The description text (Copy Description box) was always visible,
    even for employees whose only pending change was the bonus allocation.
    Now wrapped in .description-content div so JS can hide it when
    "Show pending only" is active and the employee has no tool additions changes.
    """

    def test_description_content_wrapper_present(self, client, db_session):
        """Description text should be wrapped in .description-content div."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            proposed_percent_of_target_bonus=100.0,
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        assert 'class="description-content"' in html, \
            'Description text should be wrapped in .description-content for JS filtering'

    def test_data_attributes_present_for_js_filtering(self, client, db_session):
        """Each row must have data-needs-sync, data-tool-sync, data-bonus-differs."""
        emp = Employee(
            associate_id='E001',
            associate='Test Employee',
            supervisory_organization='Engineering (Test Manager)',
            current_job_profile='Software Engineer',
            current_base_pay_manager_currency=100000.0,
            currency='USD',
            bonus_target_local_currency=15000.0,
            performance_rating_percent=100.0,
            performance_rating_percent_original=100.0,
            proposed_percent_of_target_bonus=100.0,
        )
        db_session.add(emp)
        db_session.commit()

        response = client.get('/export')
        html = response.data.decode()

        # All three data attributes must be present for the JS filter to work
        assert 'data-needs-sync=' in html, \
            'data-needs-sync attribute required for pending filter'
        assert 'data-tool-sync=' in html, \
            'data-tool-sync attribute required for effective-needs-sync calculation'
        assert 'data-bonus-differs=' in html, \
            'data-bonus-differs attribute required for hide-bonus-changes interaction'


