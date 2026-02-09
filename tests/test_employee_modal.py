"""
Tests for the employee detail modal.

The modal opens when clicking any employee name in the dashboard, rate, or
calibrate pages. It loads data via /api/employee/<id>, renders a multi-tab
form with bonus + talent fields, and saves via /api/rate + /api/calibrate.

These tests guard against JS scoping and structural regressions:

1. API contract — every field the modal JS reads is present in the response
2. Save roundtrip — all editable fields persist correctly via the save APIs
3. Template structure — rendered HTML contains all expected modal input IDs
4. JS consistency — variables used in event wiring are declared in scope
"""
import json
import re

import pytest
from models import Employee


# ---------------------------------------------------------------------------
# Fields the modal JavaScript reads from the API response
# (from renderEmployeeModal and setupModalChangeTracking in base.html)
# ---------------------------------------------------------------------------
MODAL_REQUIRED_FIELDS = [
    'Associate ID',
    'Associate',
    'Current Job Profile',
    'Supervisory Organization',
    'Currency',
    'performance_rating_percent',
    'justification',
    'mentor',
    'mentees',
    'tenets_strengths',
    'tenets_improvements',
    'bonus_override_percent',
    'special_case_notes',
    'talent_perf_what',
    'talent_perf_how',
    'talent_growth_agility',
    'talent_change_agility',
    'talent_movement_readiness',
    'talent_mentor',
    'talent_mentees',
    'talent_proposed_actions',
]

# DOM IDs that the modal JS references via getElementById
MODAL_INPUT_IDS = [
    'modal_rating_percent',
    'modal_justification',
    'modal_mentor',
    'modal_mentees',
    'modal_bonus_override_percent',
    'modal_special_case_notes',
    'modal_talent_perf_what',
    'modal_talent_perf_how',
    'modal_talent_growth_agility',
    'modal_talent_change_agility',
    'modal_talent_movement_readiness',
    'modal_talent_mentor',
    'modal_talent_mentees',
    'modal_talent_proposed_actions',
]


class TestModalAPIContract:
    """Verify /api/employee/<id> returns all fields the modal needs."""

    def test_response_contains_all_required_fields(self, client, populated_db):
        """Every field read by renderEmployeeModal must be in the response."""
        response = client.get('/api/employee/EMP001')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

        employee = result['employee']
        missing = [f for f in MODAL_REQUIRED_FIELDS if f not in employee]
        assert missing == [], f"Modal expects these fields but API omits them: {missing}"

    def test_response_fields_with_populated_data(self, client, populated_db_with_tenets):
        """Fields with data are returned with correct values."""
        response = client.get('/api/employee/EMP001')
        result = json.loads(response.data)
        employee = result['employee']

        assert employee['Associate'] == 'Paige Duty'
        assert employee['performance_rating_percent'] == 120.0
        assert employee['justification'] == 'Excellent performance on key projects'

        # Tenets should be parseable JSON strings
        strengths = json.loads(employee['tenets_strengths'])
        assert len(strengths) == 3

    def test_response_fields_with_empty_data(self, client, populated_db):
        """Fields with no data return None or empty string (not KeyError)."""
        response = client.get('/api/employee/EMP004')
        result = json.loads(response.data)
        employee = result['employee']

        # Unrated employee — nullable fields return None, text fields empty
        assert employee['performance_rating_percent'] is None
        assert employee['justification'] == '' or employee['justification'] is None

    def test_history_endpoint_succeeds(self, client, populated_db):
        """The /history endpoint that the modal calls in parallel must work."""
        response = client.get('/api/employee/EMP001/history')
        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert 'history' in result


class TestModalSaveRoundtrip:
    """Verify all editable modal fields save and read back correctly."""

    def test_save_bonus_fields_via_api(self, client, populated_db):
        """All bonus cycle fields in saveEmployeeModal() persist."""
        save_data = {
            'associate_id': 'EMP004',
            'rating_percent': '115',
            'justification': 'Strong quarter',
            'mentor': 'Alice Johnson',
            'mentees': 'Charlie Brown',
            'tenets_strengths': ['tenet1', 'tenet2', 'tenet3'],
            'tenets_improvements': ['tenet4', 'tenet5'],
        }
        save_response = client.post('/api/rate',
                                    data=json.dumps(save_data),
                                    content_type='application/json')
        assert save_response.status_code == 200
        assert json.loads(save_response.data)['success'] is True

        # Read back via the modal's API endpoint
        get_response = client.get('/api/employee/EMP004')
        employee = json.loads(get_response.data)['employee']

        assert employee['performance_rating_percent'] == 115.0
        assert employee['justification'] == 'Strong quarter'
        assert employee['mentor'] == 'Alice Johnson'
        assert employee['mentees'] == 'Charlie Brown'
        assert json.loads(employee['tenets_strengths']) == ['tenet1', 'tenet2', 'tenet3']

    def test_save_talent_fields_via_api(self, client, populated_db_with_tenets):
        """All talent calibration fields in saveEmployeeModal() persist."""
        save_data = {
            'associate_id': 'EMP001',
            'talent_perf_what': 'Surpasses Expectations',
            'talent_perf_how': 'Meets Expectations',
            'talent_growth_agility': 'Always/Most of the Time',
            'talent_change_agility': 'Sometimes',
            'talent_movement_readiness': 'Ready Now to be promoted in current role',
            'talent_mentor': 'Justin Time',
            'talent_mentees': 'Devin Null',
            'talent_proposed_actions': 'Stretch assignment in Q3',
        }
        response = client.post('/api/calibrate',
                               data=json.dumps(save_data),
                               content_type='application/json')
        assert response.status_code == 200

        employee = json.loads(client.get('/api/employee/EMP001').data)['employee']
        assert employee['talent_perf_what'] == 'Surpasses Expectations'
        assert employee['talent_movement_readiness'] == 'Ready Now to be promoted in current role'
        assert employee['talent_proposed_actions'] == 'Stretch assignment in Q3'

    def test_save_special_case_override(self, client, populated_db):
        """Special case override fields save correctly through modal API."""
        save_data = {
            'associate_id': 'EMP003',
            'bonus_override_percent': '50',
            'special_case_notes': 'Paternity leave Apr-Sep',
        }
        response = client.post('/api/rate',
                               data=json.dumps(save_data),
                               content_type='application/json')
        assert response.status_code == 200

        employee = json.loads(client.get('/api/employee/EMP003').data)['employee']
        assert employee['bonus_override_percent'] == 50.0
        assert employee['special_case_notes'] == 'Paternity leave Apr-Sep'


class TestModalTemplateStructure:
    """Verify rendered pages contain all modal input elements.

    The modal HTML is generated by renderEmployeeModal() in base.html using
    template literals. These tests confirm the page loads and the static
    modal shell (container, script) is present.
    """

    def test_dashboard_contains_modal_container(self, client, populated_db):
        """Dashboard page includes the modal overlay and container."""
        response = client.get('/')
        html = response.data.decode()
        assert 'id="employeeModal"' in html
        assert 'id="employeeModalTitle"' in html
        assert 'id="employeeModalBody"' in html

    def test_rate_page_contains_modal_container(self, client, populated_db):
        """Rate page includes the modal overlay and container."""
        response = client.get('/rate')
        html = response.data.decode()
        assert 'id="employeeModal"' in html

    def test_calibrate_page_contains_modal_container(self, client, populated_db_with_tenets):
        """Calibrate page includes the modal overlay and container."""
        response = client.get('/calibrate')
        html = response.data.decode()
        assert 'id="employeeModal"' in html

    def test_modal_js_contains_all_input_ids(self, client, populated_db):
        """Every modal input ID referenced by save/tracking JS exists in the template."""
        response = client.get('/')
        html = response.data.decode()

        for input_id in MODAL_INPUT_IDS:
            assert input_id in html, (
                f"Modal input '{input_id}' not found in rendered HTML. "
                f"renderEmployeeModal() or setupModalChangeTracking() will crash."
            )

    def test_modal_js_contains_render_function(self, client, populated_db):
        """The renderEmployeeModal function is defined in the page."""
        response = client.get('/')
        html = response.data.decode()
        assert 'function renderEmployeeModal' in html

    def test_modal_js_contains_save_function(self, client, populated_db):
        """The saveEmployeeModal function is defined in the page."""
        response = client.get('/')
        html = response.data.decode()
        assert 'function saveEmployeeModal' in html

    def test_modal_js_contains_change_tracking(self, client, populated_db):
        """The setupModalChangeTracking function is defined in the page."""
        response = client.get('/')
        html = response.data.decode()
        assert 'function setupModalChangeTracking' in html


class TestModalJSConsistency:
    """Parse the JavaScript to catch scoping bugs in modal change tracking.

    The setupModalChangeTracking() function has two scopes:
    1. Inner: checkForChanges closure — reads form values for comparison
    2. Outer: event listener wiring — attaches listeners to DOM elements

    Variables used in the outer scope for addEventListener must be declared
    there (not only inside the inner closure).
    """

    @pytest.fixture
    def base_html(self):
        """Read base.html and return its content."""
        import os
        base_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'templates', 'base.html'
        )
        with open(base_path, 'r') as f:
            return f.read()

    def _extract_function(self, html, func_name):
        """Extract a JS function body by tracking brace depth."""
        pattern = rf'function\s+{func_name}\s*\('
        match = re.search(pattern, html)
        if not match:
            return None

        # Find opening brace
        start = html.index('{', match.end())
        depth = 1
        i = start + 1
        while depth > 0 and i < len(html):
            if html[i] == '{':
                depth += 1
            elif html[i] == '}':
                depth -= 1
            i += 1
        return html[start:i]

    def test_event_listener_vars_declared_in_outer_scope(self, base_html):
        """Every variable used in addEventListener wiring must be declared
        in the outer scope of setupModalChangeTracking, not just inside
        the checkForChanges closure.

        """
        func_body = self._extract_function(base_html, 'setupModalChangeTracking')
        assert func_body is not None, "setupModalChangeTracking not found in base.html"

        # Find the checkForChanges closure boundary
        closure_match = re.search(r'const\s+checkForChanges\s*=\s*\(\)\s*=>\s*\{', func_body)
        assert closure_match is not None, "checkForChanges closure not found"

        # Find end of closure by tracking braces from its opening
        closure_start = closure_match.end() - 1  # position of '{'
        depth = 1
        i = closure_start + 1
        while depth > 0 and i < len(func_body):
            if func_body[i] == '{':
                depth += 1
            elif func_body[i] == '}':
                depth -= 1
            i += 1
        closure_end = i

        # The outer scope is everything AFTER the closure
        outer_scope = func_body[closure_end:]

        # Find all variables used in addEventListener calls in the outer scope
        listener_vars = re.findall(
            r'if\s*\((\w+)\)\s*\w+\.addEventListener',
            outer_scope
        )
        assert len(listener_vars) > 0, "No addEventListener patterns found in outer scope"

        # Find all const/let declarations in the outer scope
        declared_vars = set(re.findall(
            r'(?:const|let)\s+(\w+)\s*=',
            outer_scope
        ))

        # Every variable used in an addEventListener guard must be declared
        undeclared = [v for v in listener_vars if v not in declared_vars]
        assert undeclared == [], (
            f"Variables used in addEventListener wiring but not declared in "
            f"outer scope of setupModalChangeTracking: {undeclared}. "
            f"This causes 'X is not defined' crash when the modal opens."
        )

    def test_all_modal_inputs_have_change_listeners(self, base_html):
        """Every modal input ID should have a change/input listener
        in setupModalChangeTracking to enable the Save button."""
        func_body = self._extract_function(base_html, 'setupModalChangeTracking')
        assert func_body is not None

        # IDs that should have listeners (editable fields the user can modify)
        tracked_ids = [
            'modal_rating_percent',
            'modal_justification',
            'modal_mentor',
            'modal_mentees',
            'modal_bonus_override_percent',
            'modal_special_case_notes',
            'modal_talent_perf_what',
            'modal_talent_perf_how',
            'modal_talent_growth_agility',
            'modal_talent_change_agility',
            'modal_talent_movement_readiness',
            'modal_talent_mentor',
            'modal_talent_mentees',
            'modal_talent_proposed_actions',
        ]

        for input_id in tracked_ids:
            assert input_id in func_body, (
                f"'{input_id}' is not referenced in setupModalChangeTracking(). "
                f"Changes to this field won't enable the Save button."
            )

    def test_save_function_reads_all_modal_inputs(self, base_html):
        """saveEmployeeModal must read every editable modal input."""
        func_body = self._extract_function(base_html, 'saveEmployeeModal')
        assert func_body is not None

        save_ids = [
            'modal_rating_percent',
            'modal_justification',
            'modal_mentor',
            'modal_mentees',
            'modal_bonus_override_percent',
            'modal_special_case_notes',
            'modal_talent_perf_what',
            'modal_talent_perf_how',
            'modal_talent_growth_agility',
            'modal_talent_change_agility',
            'modal_talent_movement_readiness',
            'modal_talent_mentor',
            'modal_talent_mentees',
            'modal_talent_proposed_actions',
        ]

        for input_id in save_ids:
            assert input_id in func_body, (
                f"'{input_id}' is not read by saveEmployeeModal(). "
                f"User changes to this field will be silently lost on save."
            )
