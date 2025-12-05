# Performance Rating System

A web-based tool for managers to conduct performance reviews and calculate team bonuses with algorithmic fairness.

## Features

- **Performance Rating Interface**: Rate team members on a 0-200% scale with justification
- **Auto-save**: Ratings save automatically as you work (2-second delay)
- **Analytics Dashboard**: View team performance distribution with calibration guidance
- **Bonus Calculation**: Algorithmic bonus allocation with configurable parameters
- **Fixed Pool Guarantee**: Total bonuses always equal your budget (sum of targets)
- **Historical Tracking**: Archive periods and view employee rating history over time
- **Period Comparison**: Compare current ratings with any historical period
- **Trend Analysis**: See performance trends with charts and improving/stable/declining indicators
- **International Support**: Handles multiple currencies (USD, GBP, EUR, CAD, INR)
- **Privacy-Focused**: SQLite database, runs locally, no cloud dependencies

![Bonus Calculation Curve](docs/screenshot-bonus-curve.png)
*Performance-to-bonus allocation curve showing how ratings translate to bonuses with proportional scaling*

## Design Philosophy: Workday as Source of Truth

This tool is designed as a **local companion** to your HR system (Workday, or similar), not a replacement. The architecture maintains a clear separation:

**What comes FROM Workday (import):**
- Employee roster and identifiers
- Salaries and bonus targets
- Job profiles and org structure
- Currency information

**What stays LOCAL (manager-entered):**
- Performance ratings (0-200%)
- Justifications explaining ratings
- Team tenets evaluation
- Mentor/mentee relationships

**What goes BACK to Workday (export):**
- Final bonus allocations
- Rating justifications (for HR records)

**Why this matters:**
- **No duplicate data entry**: Employee info is maintained in one place (your HR system)
- **Safe re-imports**: Refreshing from Workday updates salaries and org changes without overwriting your ratings
- **Audit trail**: Your HR system remains the official record; this tool helps you get there
- **Portability**: Works with any HR system that can export to Excel

The workflow is: **Import → Rate → Calculate → Export**. Your HR system handles the before (employee data) and after (final allocations). This tool handles the middle (the actual performance evaluation work).

## Quick Start with Sample Data

Try the system immediately with fictitious demo data. Choose either:

### Option 1: Small Team (Recommended for First-Time Users)
Perfect for learning the system - 12 employees under one manager with sample ratings/justifications.

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate small team Workday data (salaries, bonus targets, org structure)
python3 scripts/create_sample_data.py

# 3. Start the web server
python3 app.py

# 4. Open browser to http://localhost:5000

# 5. Go to Import tab, upload sample-data-small.xlsx

# 6. Populate sample ratings and justifications
python3 scripts/populate_sample_ratings.py small
```

### Option 2: Large Multi-Manager Organization
Test multi-org scenarios - 50 employees across 5 managers with sample ratings.

```bash
# 2. Generate large org Workday data
python3 scripts/create_sample_data.py --large

# 3-5. Start server, import sample-data-large.xlsx via Import tab

# 6. Populate sample ratings and justifications
python3 scripts/populate_sample_ratings.py large
```

**Sample Data Details:**
- **Small**: 12 employees (Software Developers & SREs), 1 manager (Della Gate)
- **Large**: 50 employees across 5 managers (Della Gate, Rhoda Map, Kay P. Eye, Agie Enda, Mai Stone)
- Both include international employees (GBP) for testing multi-currency support

### Option 3: With Historical Data (Testing History Features)
Generate sample historical data to test period-over-period comparison and employee history features.

```bash
# Generate large org plus 6 quarters of historical data
python3 scripts/create_sample_data.py --large --historical

# This creates:
# - sample-data-large.xlsx (current period)
# - samples/sample-historical-2023-Q3.xlsx through samples/sample-historical-2024-Q4.xlsx
```

**To test historical features:**
1. Start server and import `sample-data-large.xlsx` as **Current Period**
2. Populate current ratings: `python3 scripts/populate_sample_ratings.py large`
3. Import each historical file as **Historical Period** (oldest first):
   - Upload `samples/sample-historical-2023-Q3.xlsx`, enter Period ID `2023-Q3` and Period Name `Q3 2023`
   - Repeat for 2023-Q4, 2024-Q1, 2024-Q2, 2024-Q3, 2024-Q4
4. Click any employee name to view their **History** tab with trend chart
5. Visit **Analytics** to see **Period-over-Period Comparison**

**Architecture Note**: Sample data generation follows the same pattern as real usage:
1. **Workday export** (scripts/create_sample_data.py) contains ONLY HR data: salaries, bonus targets, org structure
2. **Manager ratings** (scripts/populate_sample_ratings.py) adds performance ratings and justifications to the DATABASE
3. This separation mirrors reality: Workday data vs. local manager-entered ratings

**What you get:**
- ✅ Complete Workday employee data (salary, bonus targets, job profiles)
- ✅ Sample performance ratings (45-185% range) and justifications
- ✅ Empty mentor/mentee/AI fields for you to fill in
- ✅ Ready for immediate bonus calculation
- ✅ Mix of high performers, solid performers, and those needing improvement

You can now explore all features:
- **Dashboard**: See team overview with ratings
- **Rate Team**: View/modify existing ratings or practice adding new ones
- **Analytics**: Explore distribution and calibration guidance
- **Bonus Calculation**: Run algorithmic bonus distribution immediately

## Using Your Own Team Data

### Step 1: Export from Workday

Export your team data from Workday with these required columns:

**Required Columns:**
- Associate (employee name)
- Associate ID (unique identifier)
- Supervisory Organization
- Current Job Profile
- Current Base Pay All Countries
- Currency
- Annual Bonus Target Percent
- Bonus Target - Local Currency

**Additional Columns for International Teams:**
- Current Base Pay All Countries (USD)
- Bonus Target - Local Currency (USD)

**Optional Columns:**
- Photo
- Errors
- Grade (internal use, not shown to managers)
- Last Bonus Allocation Percent
- Notes

Save the export as `real-workday-export.xlsx` (or any name starting with `real-` - these are automatically ignored by git to protect your data)

### Step 2: Import Your Data

1. Start the web server: `python3 app.py`
2. Open http://localhost:5000
3. Navigate to **Import** tab
4. Upload your Workday export file
5. Choose **Current Period** import type
6. If switching from sample data, check **"Clear existing data before import"**
7. Click **Import Data**

This will:
- Import all employee records from Workday
- Initialize empty performance rating fields
- Optionally clear any existing sample data

### Step 3: Start Rating

Navigate to **Rate Team** to begin entering performance ratings.

## Workflow

### 1. Rate Your Team
- Navigate to **Rate Team** tab
- For each employee:
  - Enter performance rating (0-200%, where 100% = met expectations)
  - Add justification explaining the rating
  - Optionally note mentors and mentees
- Ratings auto-save after 2 seconds of inactivity

### 2. Review Analytics
- Navigate to **Analytics** tab
- Review performance distribution across team
- Check calibration guidance (informational, not a requirement)
- View breakdowns by department and job profile

### 3. Calculate Bonuses
- Navigate to **Bonus Calculation** tab
- Review default parameters:
  - **Upside Exponent** (1.35): Rewards for ratings ≥ 100%
  - **Downside Exponent** (1.9): Penalties for ratings < 100%
- Adjust parameters if needed
- Click **Recalculate** to see results
- Review individual bonuses and % of target

### 4. Archive the Period
When you've completed ratings for a period:
- Navigate to **Dashboard**
- Click **Archive Period** button
- Enter a Period ID (e.g., `2024-H2`) and Name (e.g., `Second Half 2024`)
- Click **Archive Period**

This:
- Creates a snapshot of all current ratings
- Clears all ratings to prepare for the next period
- Preserves historical data for comparison

### 5. View Historical Data
- Click any employee name to open their detail modal
- Switch to the **History** tab to see:
  - Performance trend chart across periods
  - Trend indicator (improving/stable/declining)
  - Period-by-period breakdown with justifications

### 6. Compare Periods
- Navigate to **Analytics** tab
- In the **Period-over-Period Comparison** section:
  - Select a historical period from the dropdown
  - View who improved, declined, or stayed stable
  - See average rating changes across the team

### 7. Export Results

Currently manual (copy from UI). Future versions will support CSV export.

## Performance Rating Scale

| Rating | Meaning |
|--------|---------|
| 0-60% | Significant performance concerns |
| 60-90% | Needs improvement |
| 90-110% | Met expectations (solid performance) |
| 110-130% | Exceeded expectations |
| 130-200% | Exceptional performance |

**Note**: 100% is the baseline for "met all expectations". Most solid performers should be in the 90-110% range.

![Performance Calibration](docs/screenshot-perf-calibration.png)
*Analytics dashboard showing performance distribution with calibration guidance to help ensure fair ratings across the team*

## Bonus Calculation Algorithm

See [BONUS_CALCULATION_README.md](docs/BONUS_CALCULATION_README.md) for detailed explanation.

**Summary**:
1. Total Pool = Sum of all bonus targets from Workday (USD)
2. Performance Multiplier = Split curve (different exponents for above/below 100%)
3. Raw Share = Target × Perf Multiplier
4. Final Bonus = Raw Share × Normalization Factor (ensures total = pool)

## Technology Stack

- **Backend**: Python 3, Flask
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: HTML, CSS, JavaScript (vanilla)
- **Charts**: Chart.js
- **Excel**: openpyxl for Workday imports

## File Structure

```
bonuses/
├── app.py                          # Flask application (main server)
├── models.py                       # SQLAlchemy database models
├── xlsx_utils.py                   # Workday XLSX parsing utilities
├── notes_parser.py                 # Notes field parser for historical imports
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── docs/                           # Documentation and images
│   ├── BONUS_CALCULATION_README.md # Manager's guide to bonuses
│   └── *.png                       # Screenshots for README
├── AGENTS.md                       # Developer/AI guide and patterns
├── ratings.db                      # SQLite database (created on first run)
├── sample-data-small.xlsx          # Generated sample data (not in repo)
├── real-workday-export.xlsx        # Your Workday export (not in repo)
├── scripts/                        # Utility scripts
│   ├── create_sample_data.py       # Sample data generator
│   └── populate_sample_ratings.py  # Populate DB with sample ratings
├── samples/                        # Sample data files
│   ├── tenets-sample.json          # Example tenets configuration
│   └── sample-historical-*.xlsx    # Generated historical data
├── templates/                      # HTML templates
│   ├── base.html                   # Base layout
│   ├── index.html                  # Dashboard
│   ├── rate.html                   # Rating interface
│   ├── analytics.html              # Analytics & calibration
│   ├── bonus_calculation.html      # Bonus calculator
│   ├── export.html                 # Export to Workday
│   └── import.html                 # Import from Workday
└── tests/                          # Unit tests
    └── test_*.py                   # Test suite
```

## Testing

Run the test suite:

```bash
python3 -m pytest tests/ -v
```

Tests cover database operations, rating validation, bonus calculations, multi-org scenarios, Workday import/export, and historical data preservation.

## Privacy & Security

- **Local-only**: All data stays on your machine
- **No cloud**: SQLite database, no external dependencies
- **No telemetry**: No data sent to external services
- **Git-safe**: `.gitignore` excludes sensitive files:
  - `ratings.db` (your data)
  - `real-*.xlsx` (Workday exports)

## Common Issues

### "No such file or directory" when importing Workday data
- You need to export from Workday first, OR
- Use sample data: `python3 scripts/create_sample_data.py` then import via the Import tab

### "Only 6 employees showing in bonus calculation"
- Employees need bonus target data in Workday export
- For international employees, ensure "Bonus Target - Local Currency (USD)" column is included
- For US employees, ensure "Bonus Target - Local Currency" column has values

### "Performance ratings not saving"
- Check browser console for errors
- Ensure the web server is running (`python3 app.py`)
- Try refreshing the page

### "Database locked" error
- Close any other processes accessing `ratings.db`
- Restart the Flask app

## Updating Data

To refresh data from Workday:

1. Export fresh data from Workday
2. Navigate to **Import** tab
3. Upload the new export file
4. Choose **Current Period** (do NOT check "Clear existing data")
5. Click **Import Data**

**Important**: Re-importing updates Workday fields (salary, job title, etc.) but **preserves** your performance ratings and justifications.

## Future Enhancements

See [TODO.md](TODO.md) for planned features and enhancements.

## Contributing

This is a manager tool for internal use. Contributions welcome:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues or questions:
- Check this README and [BONUS_CALCULATION_README.md](docs/BONUS_CALCULATION_README.md)
- Review test suite for examples: `tests/test_app.py`
- Open an issue on GitHub

## Credits

Built for engineering managers who need a fair, transparent, and efficient way to conduct performance reviews and bonus calculations.
