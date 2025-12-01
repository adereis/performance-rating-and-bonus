# Global Employee Filtering Feature - Implementation Guide

**Status:** Implementation attempted, needs troubleshooting
**Use Case:** Hide employees during calibration screen-share calls for privacy

## Problem Statement

During calibration calls, managers share screens to review performance data and calibration distributions. Sometimes the people being discussed are in the call (e.g., other managers, senior ICs), creating an awkward situation where their performance data is visible to them.

**Solution:** Global filtering system to temporarily hide employees from all reports and charts.

## Requirements

1. **Filter Types:**
   - Quick filter: Exclude people with direct reports (actual managers)
   - By job title: Exclude specific job profiles
   - By name: Exclude specific individuals

2. **User Experience:**
   - Floating filter panel (always accessible, doesn't block content)
   - Visual feedback showing which filters are active
   - Banner showing count of hidden employees
   - Filters persist across page navigation during same session
   - Clear indication when filters are configured but not yet applied

3. **Privacy-First:**
   - Filtering happens on backend (data never sent to client)
   - Applied before all calculations (ratings, bonuses, calibration)

4. **Session Persistence:**
   - Filters saved to sessionStorage (survive page navigation)
   - Cleared when browser session ends
   - URL parameters carry filters for direct links/bookmarks

## Architecture Design

### Backend (app.py)

```python
def apply_employee_filters(employees, filters):
    """
    Apply filters to employee list for privacy during screen shares.

    Args:
        employees: List of employee dicts
        filters: Dict with keys:
            - exclude_managers: bool (excludes employees who have direct reports)
            - exclude_job_titles: list of job profile strings to exclude
            - exclude_names: list of employee names to exclude

    Returns:
        Tuple of (filtered_list, excluded_count)
    """
    if not filters:
        return employees, 0

    original_count = len(employees)
    filtered = employees

    # Exclude managers (people with direct reports)
    if filters.get('exclude_managers'):
        # Find all people who have direct reports by checking supervisory_organization field
        managers_with_reports = set()
        for emp in employees:
            org = emp.get('Supervisory Organization', '')
            # Extract manager name from format: "Supervisory Organization (Manager Name)"
            import re
            match = re.search(r'\(([^)]+)\)', org)
            if match:
                managers_with_reports.add(match.group(1))

        # Filter out employees whose names appear as managers
        filtered = [e for e in filtered
                   if e.get('Associate') not in managers_with_reports]

    # Exclude by job title
    excluded_titles = filters.get('exclude_job_titles', [])
    if excluded_titles:
        filtered = [e for e in filtered
                   if e.get('Current Job Profile') not in excluded_titles]

    # Exclude by name
    excluded_names = filters.get('exclude_names', [])
    if excluded_names:
        filtered = [e for e in filtered
                   if e.get('Associate') not in excluded_names]

    excluded_count = original_count - len(filtered)
    return filtered, excluded_count


def get_filters_from_request():
    """Extract filter parameters from request query string."""
    return {
        'exclude_managers': request.args.get('exclude_managers') == 'true',
        'exclude_job_titles': request.args.getlist('exclude_job_titles'),
        'exclude_names': request.args.getlist('exclude_names')
    }


def get_available_filter_options(employees):
    """
    Get lists of unique job titles and names for filter dropdowns.

    Returns:
        Dict with 'job_titles' and 'names' lists (sorted)
    """
    job_titles = set()
    names = set()

    for emp in employees:
        job_title = emp.get('Current Job Profile')
        if job_title:
            job_titles.add(job_title)

        name = emp.get('Associate')
        if name:
            names.add(name)

    return {
        'job_titles': sorted(job_titles),
        'names': sorted(names)
    }
```

### Route Integration

```python
@app.route('/analytics')
def analytics():
    """Analytics and reports page."""
    team_data = get_all_employees()

    # Apply filters for privacy during screen shares
    filters = get_filters_from_request()
    filter_options = get_available_filter_options(team_data)
    team_data, excluded_count = apply_employee_filters(team_data, filters)

    # ... rest of analytics logic uses filtered team_data ...

    return render_template('analytics.html',
                          # ... existing params ...
                          active_filters=filters,
                          excluded_count=excluded_count,
                          filter_options=filter_options)
```

Apply same pattern to:
- `/analytics` route
- `/bonus-calculation` route
- Any other routes that display employee data

### Frontend (templates/base.html)

#### HTML Structure

```html
<!-- Filter Panel (sticky top-right) -->
<div id="filter-panel" class="filter-panel collapsed">
    <div class="filter-header" onclick="toggleFilterPanel()">
        <span>🔍 Filters</span>
        <span id="filter-count" class="badge" style="display: none;"></span>
        <span class="toggle-icon">▼</span>
    </div>

    <div class="filter-body">
        <div class="filter-section">
            <h4>Quick Filters</h4>
            <label class="filter-checkbox">
                <input type="checkbox" id="exclude-managers" onchange="updateFilters()">
                <span>Exclude people with direct reports</span>
            </label>
        </div>

        <div class="filter-section">
            <h4>By Job Title</h4>
            <div id="job-title-filters" class="filter-tags"></div>
            <select id="job-title-select" class="filter-select" onchange="addJobTitleFilter(this)">
                <option value="">+ Add job title...</option>
                <!-- Populated dynamically from filter_options -->
            </select>
        </div>

        <div class="filter-section">
            <h4>By Name</h4>
            <div id="name-filters" class="filter-tags"></div>
            <select id="name-select" class="filter-select" onchange="addNameFilter(this)">
                <option value="">+ Add person...</option>
                <!-- Populated dynamically from filter_options -->
            </select>
        </div>

        <div class="filter-actions">
            <button onclick="clearFilters()" class="btn-secondary">Clear All</button>
            <button onclick="applyFilters()" class="btn-primary" id="apply-filters-btn">Apply Filters</button>
        </div>
        <div id="unapplied-notice" style="display: none; margin-top: 12px; padding: 8px; background: #fff3cd; border-radius: 4px; font-size: 12px; color: #856404;">
            ⚠️ Click "Apply Filters" to activate
        </div>
    </div>
</div>

<!-- Active Filter Banner -->
{% if excluded_count is defined and excluded_count > 0 %}
<div class="filter-banner">
    ⚠️ <strong>{{ excluded_count }} employee(s) hidden by filters</strong>
    (Showing {{ total_employees - excluded_count if total_employees is defined else 'remaining' }} of {{ total_employees if total_employees is defined else 'total' }})
    <a href="?" style="margin-left: 10px; color: #856404; text-decoration: underline;">Clear filters</a>
</div>
{% endif %}
```

#### CSS

```css
/* Filter Panel Styles */
.filter-panel {
    position: fixed;
    top: 80px;
    right: 20px;
    width: 320px;
    background: white;
    border: 1px solid #ddd;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    z-index: 1000;
    transition: all 0.3s ease;
}

.filter-panel.collapsed .filter-body {
    display: none;
}

.filter-panel.collapsed .toggle-icon {
    transform: rotate(-90deg);
}

.filter-header {
    padding: 12px 16px;
    background: #f8f9fa;
    border-bottom: 1px solid #ddd;
    border-radius: 8px 8px 0 0;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    user-select: none;
}

.filter-header:hover {
    background: #e9ecef;
}

.toggle-icon {
    transition: transform 0.3s ease;
    font-size: 12px;
}

.filter-body {
    padding: 16px;
    max-height: 70vh;
    overflow-y: auto;
}

.filter-section {
    margin-bottom: 20px;
}

.filter-section h4 {
    font-size: 13px;
    font-weight: 600;
    color: #2c3e50;
    margin-bottom: 10px;
}

.filter-checkbox {
    display: flex;
    align-items: center;
    cursor: pointer;
    padding: 6px 0;
}

.filter-select {
    width: 100%;
    padding: 8px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
}

.filter-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;
    min-height: 24px;
}

.filter-tag {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    background: #667eea;
    color: white;
    border-radius: 12px;
    font-size: 12px;
}

.filter-tag-remove {
    margin-left: 6px;
    cursor: pointer;
    font-weight: bold;
    opacity: 0.8;
}

.filter-tag-remove:hover {
    opacity: 1;
}

.badge {
    background: #dc3545;
    color: white;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
}

.filter-banner {
    background: #fff3cd;
    color: #856404;
    padding: 12px 20px;
    text-align: center;
    border-bottom: 2px solid #ffc107;
    font-size: 14px;
}

@keyframes pulse {
    0%, 100% {
        box-shadow: 0 0 0 0 rgba(102, 126, 234, 0.7);
    }
    50% {
        box-shadow: 0 0 0 8px rgba(102, 126, 234, 0);
    }
}
```

#### JavaScript

```javascript
// Filter Management System
const FilterManager = {
    // Load filters from sessionStorage
    load: function() {
        const saved = sessionStorage.getItem('employeeFilters');
        return saved ? JSON.parse(saved) : {
            exclude_managers: false,
            exclude_job_titles: [],
            exclude_names: []
        };
    },

    // Save filters to sessionStorage
    save: function(filters) {
        sessionStorage.setItem('employeeFilters', JSON.stringify(filters));
    },

    // Build URL with filter parameters
    buildFilteredUrl: function(baseUrl, filters) {
        const url = new URL(baseUrl, window.location.origin);

        if (filters.exclude_managers) {
            url.searchParams.set('exclude_managers', 'true');
        }

        filters.exclude_job_titles.forEach(title => {
            url.searchParams.append('exclude_job_titles', title);
        });

        filters.exclude_names.forEach(name => {
            url.searchParams.append('exclude_names', name);
        });

        return url.toString();
    }
};

// Toggle filter panel
function toggleFilterPanel() {
    document.getElementById('filter-panel').classList.toggle('collapsed');
}

// Add job title filter
function addJobTitleFilter(select) {
    const value = select.value;
    if (!value) return;

    const tag = document.createElement('div');
    tag.className = 'filter-tag';
    tag.dataset.value = value;
    tag.innerHTML = `<span>${value}</span><span class="filter-tag-remove" onclick="removeTag(this)">×</span>`;

    document.getElementById('job-title-filters').appendChild(tag);
    select.value = '';
    updateFilters();
}

// Add name filter
function addNameFilter(select) {
    const value = select.value;
    if (!value) return;

    const tag = document.createElement('div');
    tag.className = 'filter-tag';
    tag.dataset.value = value;
    tag.innerHTML = `<span>${value}</span><span class="filter-tag-remove" onclick="removeTag(this)">×</span>`;

    document.getElementById('name-filters').appendChild(tag);
    select.value = '';
    updateFilters();
}

// Remove filter tag
function removeTag(element) {
    element.parentElement.remove();
    updateFilters();
}

// Update filter state
function updateFilters() {
    const filters = {
        exclude_managers: document.getElementById('exclude-managers').checked,
        exclude_job_titles: Array.from(document.querySelectorAll('#job-title-filters .filter-tag')).map(t => t.dataset.value),
        exclude_names: Array.from(document.querySelectorAll('#name-filters .filter-tag')).map(t => t.dataset.value)
    };

    FilterManager.save(filters);
    updateFilterCount(filters);
    checkForUnappliedChanges(filters);
}

// Update filter count badge
function updateFilterCount(filters) {
    if (!filters) filters = FilterManager.load();

    let count = 0;
    if (filters.exclude_managers) count++;
    count += filters.exclude_job_titles.length;
    count += filters.exclude_names.length;

    const badge = document.getElementById('filter-count');
    if (count > 0) {
        badge.textContent = count;
        badge.style.display = 'inline-block';
    } else {
        badge.style.display = 'none';
    }
}

// Check if there are unapplied filter changes
function checkForUnappliedChanges(currentFilters) {
    const urlParams = new URLSearchParams(window.location.search);
    const urlFilters = {
        exclude_managers: urlParams.get('exclude_managers') === 'true',
        exclude_job_titles: urlParams.getAll('exclude_job_titles'),
        exclude_names: urlParams.getAll('exclude_names')
    };

    const hasChanges =
        currentFilters.exclude_managers !== urlFilters.exclude_managers ||
        JSON.stringify(currentFilters.exclude_job_titles.sort()) !== JSON.stringify(urlFilters.exclude_job_titles.sort()) ||
        JSON.stringify(currentFilters.exclude_names.sort()) !== JSON.stringify(urlFilters.exclude_names.sort());

    const notice = document.getElementById('unapplied-notice');
    const applyBtn = document.getElementById('apply-filters-btn');

    if (hasChanges) {
        notice.style.display = 'block';
        applyBtn.style.animation = 'pulse 2s infinite';
    } else {
        notice.style.display = 'none';
        applyBtn.style.animation = 'none';
    }
}

// Apply filters (reload page with parameters)
function applyFilters() {
    const filters = {
        exclude_managers: document.getElementById('exclude-managers').checked,
        exclude_job_titles: Array.from(document.querySelectorAll('#job-title-filters .filter-tag')).map(t => t.dataset.value),
        exclude_names: Array.from(document.querySelectorAll('#name-filters .filter-tag')).map(t => t.dataset.value)
    };

    FilterManager.save(filters);
    window.location.href = FilterManager.buildFilteredUrl(window.location.pathname, filters);
}

// Clear all filters
function clearFilters() {
    sessionStorage.removeItem('employeeFilters');
    window.location.href = window.location.pathname;
}

// Initialize filter panel on page load
document.addEventListener('DOMContentLoaded', function() {
    const filters = FilterManager.load();

    // Populate filter options from backend
    {% if filter_options is defined %}
    const jobTitleSelect = document.getElementById('job-title-select');
    const nameSelect = document.getElementById('name-select');

    {% if filter_options.job_titles %}
    {% for title in filter_options.job_titles %}
    const jobOption = document.createElement('option');
    jobOption.value = {{ title | tojson }};
    jobOption.textContent = {{ title | tojson }};
    jobTitleSelect.appendChild(jobOption);
    {% endfor %}
    {% endif %}

    {% if filter_options.names %}
    {% for name in filter_options.names %}
    const nameOption = document.createElement('option');
    nameOption.value = {{ name | tojson }};
    nameOption.textContent = {{ name | tojson }};
    nameSelect.appendChild(nameOption);
    {% endfor %}
    {% endif %}
    {% endif %}

    // Restore filter UI state from sessionStorage
    document.getElementById('exclude-managers').checked = filters.exclude_managers;

    // Restore job title filter tags
    filters.exclude_job_titles.forEach(title => {
        const tag = document.createElement('div');
        tag.className = 'filter-tag';
        tag.dataset.value = title;
        tag.innerHTML = `<span>${title}</span><span class="filter-tag-remove" onclick="removeTag(this)">×</span>`;
        document.getElementById('job-title-filters').appendChild(tag);
    });

    // Restore name filter tags
    filters.exclude_names.forEach(name => {
        const tag = document.createElement('div');
        tag.className = 'filter-tag';
        tag.dataset.value = name;
        tag.innerHTML = `<span>${name}</span><span class="filter-tag-remove" onclick="removeTag(this)">×</span>`;
        document.getElementById('name-filters').appendChild(tag);
    });

    updateFilterCount(filters);
    checkForUnappliedChanges(filters);
});
```

## User Workflow

1. **Open filter panel**: Click "🔍 Filters" button (top-right)
2. **Configure filters**:
   - Check "Exclude people with direct reports" OR
   - Select job titles from dropdown (creates filter tags) OR
   - Select names from dropdown (creates filter tags)
3. **Visual feedback**: Badge shows count (e.g., "2"), warning appears: "⚠️ Click 'Apply Filters' to activate"
4. **Apply filters**: Click "Apply Filters" button (will be pulsing)
5. **Page reloads**: With filter parameters in URL
6. **Confirmation**: Orange banner shows "X employee(s) hidden"
7. **Persistence**: Filters remain active when navigating to other pages
8. **Clear**: Click "Clear filters" link or "Clear All" button

## Known Issues (Troubleshooting Needed)

1. **Manager filter not working correctly**
   - Issue: Filter configured but managers still visible
   - Possible causes:
     - Regex pattern not matching Supervisory Organization format
     - Manager names don't match exactly between fields
     - Case sensitivity issues
     - Special characters in names

2. **UX confusion**
   - Users don't realize they need to click "Apply" button
   - Solution implemented: Warning notice + pulse animation
   - May need more prominent "Apply" button

3. **Filter dropdown population**
   - Need to verify filter_options is passed to all templates
   - Check if Jinja2 template conditionals work correctly

## Testing Checklist

- [ ] Verify `apply_employee_filters()` works with test data
- [ ] Test URL parameter extraction
- [ ] Test sessionStorage save/load
- [ ] Verify filter banner appears with correct count
- [ ] Test filter persistence across page navigation
- [ ] Test "Clear All" button
- [ ] Test manager filter with actual managers in database
- [ ] Test job title filter with various titles
- [ ] Test name filter with special characters
- [ ] Verify no regressions in existing tests

## Files Modified

1. **app.py**:
   - Add `apply_employee_filters()` function
   - Add `get_filters_from_request()` function
   - Add `get_available_filter_options()` function
   - Update `/analytics` route
   - Update `/bonus-calculation` route

2. **templates/base.html**:
   - Add filter panel HTML
   - Add filter CSS (173 lines)
   - Add filter JavaScript (177 lines)
   - Add filter banner

## Future Enhancements

1. **Auto-apply filters**: Remove "Apply" button, apply on change
2. **Filter presets**: Save/load common filter combinations
3. **More filter types**: By grade level, salary range, tenure
4. **Export with filters**: CSV/PDF export respects active filters
5. **Filter history**: Track which filters were used in past sessions
6. **Multi-user filters**: Share filter URLs with other managers

## Notes

- Backend filtering ensures privacy (data never sent to client)
- Filters are ephemeral (no database changes)
- Works with existing data model (no schema changes)
- Compatible with multi-team views
- All 83 existing tests pass (as of last successful run)
