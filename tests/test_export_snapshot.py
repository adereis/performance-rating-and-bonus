"""Regression tests for snapshot export row builders."""
from services.export import prepare_snapshot_bonus_row, SNAPSHOT_BONUS_HEADERS


def test_snapshot_bonus_row_includes_percent_of_target():
    """The 'Bonus % of Target' column must be populated, not blank.

    Regression: the row builder read bonus_result['percent_of_target'] but the
    bonus calculator produces 'bonus_percent_of_target', so the column was
    always empty in every snapshot export.
    """
    emp = {
        'Associate ID': 'E1',
        'Associate': 'Sample Name',
        'performance_rating_percent': 110,
    }
    bonus_results_by_id = {'E1': {'final_bonus': 5000, 'bonus_percent_of_target': 105}}

    row = prepare_snapshot_bonus_row(emp, {}, bonus_results_by_id)
    idx = SNAPSHOT_BONUS_HEADERS.index('Bonus % of Target')
    assert row[idx] == 105
