/**
 * Placeholder detection for mentor/mentee fields.
 *
 * Shared between rate.html and calibrate.html. Values matching common
 * placeholder patterns (TBD, N/A, None, etc.) trigger a warning and
 * are normalized to empty on save by the server.
 */

const PLACEHOLDER_PATTERNS = new Set([
    'none', 'n/a', 'na', 'tbd', 'tbc', 'tba', '-', '?', 'null', 'nil', 'unknown',
    'not applicable', 'not assigned', 'pending', 'to be determined', 'to be confirmed',
]);

function isPlaceholderValue(value) {
    if (!value) return false;
    return PLACEHOLDER_PATTERNS.has(value.trim().toLowerCase());
}

function showPlaceholderWarning(input) {
    let warning = input.parentElement.querySelector('.placeholder-warning');
    if (!warning) {
        warning = document.createElement('div');
        warning.className = 'placeholder-warning';
        warning.style.cssText = 'font-size: 11px; color: #e67e22; margin-top: 4px;';
        input.parentElement.appendChild(warning);
    }
    warning.textContent = '\u26A0 Placeholder values like "TBD" or "None" will be cleared on save';
    warning.style.display = 'block';
}

function hidePlaceholderWarning(input) {
    const warning = input.parentElement.querySelector('.placeholder-warning');
    if (warning) {
        warning.style.display = 'none';
    }
}
