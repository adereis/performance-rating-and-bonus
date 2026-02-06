/**
 * Sidebar employee index navigation.
 *
 * Shared between rate.html and calibrate.html. Provides search filtering,
 * scroll-to-employee, and team header visibility management.
 *
 * Note: The two pages use different data attributes on cards:
 *   - rate.html:      data-associate-id on .employee-card
 *   - calibrate.html: data-employee-id on .employee-card
 * Both pages use data-employee-id on .index-item sidebar entries.
 * scrollToEmployee() tries both attributes to find the target card.
 */

function scrollToEmployee(associateId) {
    // Try both attribute conventions used across pages
    const card = document.querySelector(`.employee-card[data-associate-id="${associateId}"]`)
              || document.querySelector(`.employee-card[data-employee-id="${associateId}"]`);
    if (!card) return;

    // Ensure parent team group is expanded (for multi-team view)
    const teamContent = card.closest('.team-group-content');
    if (teamContent && teamContent.classList.contains('collapsed')) {
        const teamHeader = teamContent.previousElementSibling;
        if (teamHeader) {
            teamHeader.classList.remove('collapsed');
            teamContent.classList.remove('collapsed');
        }
    }

    // Scroll to card
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Highlight in index
    document.querySelectorAll('.index-item').forEach(item => item.classList.remove('active'));
    const indexItem = document.querySelector(`.index-item[data-employee-id="${associateId}"]`);
    if (indexItem) {
        indexItem.classList.add('active');
        setTimeout(() => indexItem.classList.remove('active'), 2000);
    }
}

function filterIndex(searchTerm) {
    const term = searchTerm.toLowerCase().trim();
    const items = document.querySelectorAll('.index-item');
    const teamHeaders = document.querySelectorAll('.index-team-header');

    // Track which teams have visible items
    const visibleTeams = new Set();

    items.forEach(item => {
        const name = item.querySelector('.name')?.textContent?.toLowerCase() || '';
        const matches = term === '' || name.includes(term);
        item.style.display = matches ? 'flex' : 'none';

        if (matches) {
            const prevHeader = findPreviousTeamHeader(item);
            if (prevHeader) {
                visibleTeams.add(prevHeader);
            }
        }
    });

    // Show/hide team headers based on visible items
    teamHeaders.forEach(header => {
        header.style.display = (term === '' || visibleTeams.has(header)) ? 'block' : 'none';
    });
}

function findPreviousTeamHeader(item) {
    let prev = item.previousElementSibling;
    while (prev) {
        if (prev.classList.contains('index-team-header')) {
            return prev;
        }
        prev = prev.previousElementSibling;
    }
    return null;
}
