/**
 * Employee form schema + the modal's collect/submit.
 *
 * Single source of truth for which fields the bonus and talent cycles save,
 * shared by the modal's two save paths (saveEmployeeModal +
 * autoSaveAndCloseModal). Because the modal can only send the fields named in
 * the schema, it can no longer accidentally send a field it doesn't render —
 * the bug that nulled out promotion data whenever the modal was closed with
 * unsaved changes (the two paths had drifted apart).
 *
 * Modal input id convention: 'modal_' + <api key> (e.g. modal_rating_percent).
 * Depends on window.App from common.js (App.fetchJSON).
 */
(function () {
    'use strict';
    const App = (window.App = window.App || {});

    // Plain-value fields, by their /api key.
    const BONUS_FIELDS = [
        'rating_percent', 'justification', 'mentor', 'mentees',
        'bonus_override_percent', 'special_case_notes',
    ];
    const TALENT_FIELDS = [
        'talent_perf_what', 'talent_perf_how', 'talent_growth_agility',
        'talent_change_agility', 'talent_movement_readiness',
        'talent_mentor', 'talent_mentees', 'talent_proposed_actions',
    ];

    function readModal(key) {
        const el = document.getElementById('modal_' + key);
        return el ? (el.value || '') : '';
    }

    function modalTenets() {
        const modal = document.getElementById('employeeModal');
        const checked = (type) => Array.from(
            modal.querySelectorAll('input[data-tenet-type="' + type + '"]:checked')
        ).map((cb) => cb.value);
        return { tenets_strengths: checked('strengths'), tenets_improvements: checked('improvements') };
    }

    /** Build the two API payloads from the modal, restricted to the schema fields. */
    function collectFromModal(associateId) {
        const bonusData = { associate_id: associateId };
        BONUS_FIELDS.forEach((k) => { bonusData[k] = readModal(k); });
        Object.assign(bonusData, modalTenets());

        const talentData = { associate_id: associateId };
        TALENT_FIELDS.forEach((k) => { talentData[k] = readModal(k); });
        return { bonusData, talentData };
    }

    function resultError(label, result) {
        if (result.status === 'rejected') {
            return label + ': Network error - ' + ((result.reason && result.reason.message) || result.reason);
        }
        if (!result.value || !result.value.success) {
            return label + ': ' + ((result.value && result.value.error) || 'Unknown error');
        }
        return null;
    }

    /** POST bonus + talent in parallel; resolves to { errors: [...] } (empty on success). */
    function submit(bonusData, talentData) {
        return Promise.allSettled([
            App.fetchJSON('/api/rate', { method: 'POST', body: JSON.stringify(bonusData) }),
            App.fetchJSON('/api/calibrate', { method: 'POST', body: JSON.stringify(talentData) }),
        ]).then((results) => {
            const errors = [];
            const be = resultError('Bonus', results[0]); if (be) errors.push(be);
            const te = resultError('Talent', results[1]); if (te) errors.push(te);
            return { errors: errors };
        });
    }

    App.EmployeeForm = { BONUS_FIELDS, TALENT_FIELDS, collectFromModal, submit };
})();
