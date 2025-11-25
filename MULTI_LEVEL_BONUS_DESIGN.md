# Multi-Level Organization Bonus Calculation Design

**Status:** ✅ IMPLEMENTED (2025-11-25)

## Problem Statement

**Current System:**
- Works perfectly for a single frontline manager with one team
- Shows bonus calculation with normalization across that one team
- Single normalization factor ensures total bonuses = total pool

**Multi-Level Challenge:**
- Directors manage multiple teams (each with their own frontline manager)
- Frontline managers see their team in isolation with their own normalization factor
- Director's normalization factor differs when calculating across all teams
- Budget "shifts" between teams during director-level normalization
- Frontline managers lack visibility into how director-level calculation affects their team

**Example Scenario:**
```
Director has 3 teams:
- Team A (Manager Alice): 5 high performers (avg 130% rating)
- Team B (Manager Bob): 10 solid performers (avg 100% rating)
- Team C (Manager Carol): 5 low performers (avg 70% rating)

Alice's view (Team A only):
- High concentration of top performers
- Low normalization factor (lots of raw shares vs pool)
- Appears to have limited budget to reward top performers

Director's view (All teams):
- Team C has surplus budget (low performers = low raw shares)
- Normalization across all teams redistributes Team C's surplus
- Team A actually gets MORE budget than Alice's calculation showed
- Alice doesn't see this until director's final allocation
```

## Proposed Reports for Directors

### Report 1: **Per-Team vs Director-Level Comparison**

**Purpose:** Show how each team's bonuses change when calculated in isolation vs. at director level

**Table Columns:**
| Team | Total Pool | Avg Rating | Team-Level Norm Factor | Director-Level Norm Factor | Budget Impact | Team Status |
|------|------------|------------|------------------------|---------------------------|---------------|-------------|
| Team A | $50K | 130% | 0.85 | 1.10 | +$7,500 | Budget Gain |
| Team B | $100K | 100% | 1.00 | 1.00 | $0 | Neutral |
| Team C | $50K | 70% | 1.45 | 1.10 | -$7,500 | Budget Loss |

**Metrics:**
- **Team-Level Norm Factor**: What frontline manager sees
- **Director-Level Norm Factor**: Actual factor when all teams combined
- **Budget Impact**: Dollar amount gained/lost from team-level to director-level
- **Team Status**: Visual indicator (green = gain, yellow = neutral, red = loss)

**Implementation:**
```python
def calculate_multi_level_bonus():
    # 1. Calculate bonus for each team independently
    for team in teams:
        team.team_level_results = calculate_bonus(team.employees)
        team.team_level_norm = team.total_pool / team.total_raw_shares

    # 2. Calculate bonus across all teams
    all_employees = flatten(teams)
    director_results = calculate_bonus(all_employees)
    director_norm = total_pool / total_raw_shares

    # 3. Compare and calculate impact
    for team in teams:
        team.budget_impact = sum(director_results[emp] - team_results[emp]
                                 for emp in team.employees)
```

---

### Report 2: **Detailed Team Breakdown**

**Purpose:** For each team, show side-by-side comparison of bonuses under both calculations

**Per Team:**
```
Team A (Manager: Alice) - 5 employees

Employee View:
┌─────────────┬────────┬──────────────┬────────────────┬───────────────┬────────┐
│ Name        │ Rating │ Team-Level $ │ Director-Level │ $ Difference  │ Status │
├─────────────┼────────┼──────────────┼────────────────┼───────────────┼────────┤
│ Alice Top   │ 150%   │ $12,000      │ $15,500        │ +$3,500       │   ↑    │
│ Bob High    │ 130%   │ $10,500      │ $13,600        │ +$3,100       │   ↑    │
│ Carol Good  │ 120%   │ $9,800       │ $12,700        │ +$2,900       │   ↑    │
│ Dave Solid  │ 110%   │ $9,200       │ $11,900        │ +$2,700       │   ↑    │
│ Eve Mid     │ 90%    │ $7,500       │ $9,700         │ +$2,200       │   ↑    │
└─────────────┴────────┴──────────────┴────────────────┴───────────────┴────────┘
Team Total: $49,000 → $63,400 (+$14,400 from other teams)
```

**Implementation Note:** This is essentially running the bonus calculation twice:
1. Once with `team.employees` only
2. Once with all `director.all_employees`

Then showing both results side-by-side per employee.

---

### Report 3: **Budget Flow Visualization**

**Purpose:** Show where budget is flowing between teams visually

**Chart:**
```
Team Budget Transfers (Director-Level Normalization)

Team C (Low Performers)  ─────[$7,500]────→  Team A (High Performers)
      ↓
   [-$7,500]                                      [+$7,500]

Team B (Balanced)  ──────────[±$0]──────────→   (No change)
```

**Metrics Table:**
| From Team | To Team | Amount | Reason |
|-----------|---------|--------|--------|
| Team C | Team A | +$7,500 | Surplus from low performers redistributed to high performers |
| - | Team B | $0 | Balanced team, no transfer |

---

### Report 4: **What-If Scenarios for Directors**

**Purpose:** Allow director to simulate impact of rating changes before finalizing

**Interactive Controls:**
- "Adjust Team A ratings by +/- 10%"
- "Move Employee X from Team B to Team A"
- "Set all Team C to 100% (hypothetical)"

**Shows:**
- How normalization factor changes
- How budget flows change between teams
- Impact on individual bonuses across all teams

---

### Report 5: **Fairness Check Report**

**Purpose:** Identify potential issues where team-level appears unfair to frontline managers

**Flags:**
| Team | Issue | Description | Impact |
|------|-------|-------------|--------|
| Team A | Large Gain | +30% budget vs team-level | Frontline manager underestimated available budget |
| Team C | Large Loss | -15% budget vs team-level | Frontline manager had inflated expectations |
| Team D | Rating Inflation | Avg 140% vs org avg 105% | Possible calibration issue |

**Auto-Detection:**
- Budget shift > 20%: Highlight for review
- Team avg rating > org avg + 25%: Possible rating inflation
- All high/low performers: Calibration discussion needed

---

## Implementation Recommendations

### Option 1: **Tabbed View on Bonus Calculation Page**

Add tabs to existing page:
- **Tab 1:** "Team-Level View" (current functionality, default for frontline managers)
- **Tab 2:** "Director View" (multi-level comparison, only visible if multiple teams)
- **Tab 3:** "Detailed Breakdown" (per-team side-by-side)

**Detection Logic:**
```python
def get_user_level():
    orgs = get_unique_supervisory_orgs()
    if len(orgs) == 1:
        return "frontline_manager"  # Show Tab 1 only
    else:
        return "director"  # Show all 3 tabs
```

### Option 2: **Separate Director Dashboard**

Create new route `/director-bonus-calculation`:
- Shows all reports consolidated
- Dropdown to select team for detailed view
- Comparison charts (team-level vs director-level)
- Export to CSV/PDF for sharing with frontline managers

**Navigation:**
- Auto-detect: If >1 supervisory org, show "Director View" button
- Allows drilling down: Director → Team → Individual

### Option 3: **Enhanced Single Page with Collapsible Sections**

Keep single bonus calculation page, add:
- **Section 1:** Overall summary (always visible)
- **Section 2:** Per-team breakdown (collapsible, auto-expands if director)
- **Section 3:** Team vs Director comparison (only if >1 team)

**Advantages:**
- Single page, progressive disclosure
- Frontline managers see simple view
- Directors see expanded view with comparisons

---

## Recommended Approach: **Option 1 (Tabbed View)**

**Why:**
1. **Backwards Compatible:** Frontline managers see no change (Tab 1 is default)
2. **Scalable:** Easy to add more tabs later (what-if scenarios, etc.)
3. **Clear Separation:** Each tab has focused purpose
4. **Progressive Disclosure:** Directors only see complexity when they need it

**Implementation Steps:**

### Phase 1: Detection & Tab Structure
```python
@app.route('/bonus-calculation')
def bonus_calculation():
    # ... existing code ...

    # Detect if user is director
    orgs = get_unique_orgs(team_data)
    is_director = len(orgs) > 1

    # If frontline manager, return existing view
    if not is_director:
        return render_template('bonus_calculation.html', ...)

    # If director, calculate multi-level
    teams = group_by_org(team_data)
    team_comparisons = calculate_team_vs_director(teams)

    return render_template('bonus_calculation.html',
                          is_director=True,
                          teams=teams,
                          comparisons=team_comparisons,
                          ...)
```

### Phase 2: Team-Level Calculations
```python
def calculate_team_vs_director(teams):
    """
    Calculate bonuses twice:
    1. Per-team (what frontline manager sees)
    2. Director-level (actual allocation)
    """
    comparisons = []

    # Calculate per-team
    for team in teams:
        team_calc = calculate_bonus_for_employees(
            team['employees'],
            params
        )
        team['team_level_calc'] = team_calc
        team['team_norm_factor'] = team_calc['value_per_share']

    # Calculate director-level
    all_employees = [emp for team in teams for emp in team['employees']]
    director_calc = calculate_bonus_for_employees(
        all_employees,
        params
    )
    director_norm_factor = director_calc['value_per_share']

    # Compare
    for team in teams:
        team_pool = sum(e['bonus_target_usd'] for e in team['employees'])
        team_allocated_team_level = sum(
            r['final_bonus'] for r in team['team_level_calc']['results']
        )
        team_allocated_director_level = sum(
            director_calc['results_by_id'][e['Associate ID']]['final_bonus']
            for e in team['employees']
        )

        budget_impact = team_allocated_director_level - team_allocated_team_level

        comparisons.append({
            'team_name': team['name'],
            'team_pool': team_pool,
            'team_norm': team['team_norm_factor'],
            'director_norm': director_norm_factor,
            'budget_impact': budget_impact,
            'impact_percent': (budget_impact / team_pool * 100) if team_pool > 0 else 0
        })

    return comparisons
```

### Phase 3: UI Template Updates
```html
<!-- Tab Navigation (only show if is_director) -->
{% if is_director %}
<div class="tabs">
    <button class="tab active" data-tab="overview">Overview</button>
    <button class="tab" data-tab="team-comparison">Team Comparison</button>
    <button class="tab" data-tab="detailed">Detailed Breakdown</button>
</div>
{% endif %}

<!-- Tab 1: Overview (existing view) -->
<div class="tab-content active" id="overview">
    <!-- Existing bonus calculation table -->
</div>

<!-- Tab 2: Team Comparison (new) -->
{% if is_director %}
<div class="tab-content" id="team-comparison">
    <table class="team-comparison-table">
        <thead>
            <tr>
                <th>Team</th>
                <th>Total Pool</th>
                <th>Avg Rating</th>
                <th>Team-Level Norm</th>
                <th>Director-Level Norm</th>
                <th>Budget Impact</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
            {% for comparison in comparisons %}
            <tr>
                <td><strong>{{ comparison.team_name }}</strong></td>
                <td>${{ "{:,.0f}".format(comparison.team_pool) }}</td>
                <td>{{ comparison.avg_rating }}%</td>
                <td>{{ "%.3f".format(comparison.team_norm) }}</td>
                <td>{{ "%.3f".format(comparison.director_norm) }}</td>
                <td class="{{ 'gain' if comparison.budget_impact > 0 else 'loss' if comparison.budget_impact < 0 else 'neutral' }}">
                    {% if comparison.budget_impact > 0 %}+{% endif %}
                    ${{ "{:,.0f}".format(comparison.budget_impact) }}
                    ({{ "%+.1f"|format(comparison.impact_percent) }}%)
                </td>
                <td>
                    {% if comparison.budget_impact > 0 %}
                    <span class="status-gain">↑ Budget Gain</span>
                    {% elif comparison.budget_impact < 0 %}
                    <span class="status-loss">↓ Budget Loss</span>
                    {% else %}
                    <span class="status-neutral">= Neutral</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endif %}
```

---

## Data Requirements

**No database changes needed!** Everything can be calculated on-the-fly from existing data:
- `supervisory_organization`: Already identifies team
- `performance_rating_percent`: Already has ratings
- `bonus_target_local_currency_usd`: Already has targets

**Runtime Calculation:**
1. Group employees by `supervisory_organization`
2. Run bonus calculation per team
3. Run bonus calculation for all teams combined
4. Compare results

---

## Benefits

### For Directors:
✅ **Visibility:** See how budget flows between teams
✅ **Fairness:** Identify teams with inflated/deflated expectations
✅ **Communication:** Can explain to frontline managers why their numbers differ
✅ **Planning:** Understand org-wide normalization impact before finalizing

### For Frontline Managers:
✅ **No Change:** Default view remains simple and focused
✅ **Optional Insight:** Can see director view if they want context
✅ **Transparency:** Understand why final numbers differ from their calculations

### For System:
✅ **No Breaking Changes:** Existing functionality untouched
✅ **No DB Changes:** Uses existing data
✅ **Progressive Disclosure:** Complexity only shown when needed
✅ **Scalable:** Works with 2 teams or 20 teams

---

## Open Questions

1. **Should frontline managers see the director view?**
   - Pros: Transparency, better understanding
   - Cons: Might cause confusion or disputes
   - Recommendation: Yes, but in read-only mode with explanation

2. **How to handle 3+ levels (Director of Directors)?**
   - Current design handles 2 levels (Manager → Director)
   - For 3+ levels: Recurse the same logic
   - Show hierarchical tree: VP → Director → Manager

3. **Should we cache calculations?**
   - Pro: Faster for large orgs
   - Con: Adds complexity
   - Recommendation: Start without caching, add if performance issues

4. **Export format for directors?**
   - CSV: One row per employee with team indicator
   - Excel: Multiple sheets (one per team + summary)
   - PDF: Formatted report for leadership
   - Recommendation: Start with CSV, add Excel later

---

## Next Steps

If you approve this design, I recommend:

1. **Validate with sample data:** Use multi-org test data to verify the math
2. **Build Tab 1 (Overview):** Ensure no regression for existing users
3. **Build Tab 2 (Team Comparison):** Add the comparison table
4. **Test with real data:** Verify normalization factors are correct
5. **Build Tab 3 (Detailed):** Add per-employee side-by-side view
6. **Add export functionality:** CSV download for director reports

**Estimated Effort:** 1-2 days for core functionality (Tabs 1-2), additional day for Tab 3 and polish.
