"""Regression coverage for startup migrations using isolated test databases."""

import pytest
from sqlalchemy import text

from migrations import (
    migrate_add_new_columns,
    migrate_backfill_bonus_cycle_flag,
)
from models import Employee


def test_startup_preserves_explicit_cycle_exclusions(db_session):
    employee = Employee(
        associate_id='MIGRATION001',
        associate='Fictional Former Participant',
        bonus_target_local_currency=1000,
        in_current_bonus_cycle=False,
    )
    db_session.add(employee)
    db_session.commit()

    migrate_backfill_bonus_cycle_flag(db_session.get_bind())

    db_session.refresh(employee)
    assert employee.in_current_bonus_cycle is False


@pytest.mark.parametrize('local_target,manager_target,expected', [
    (1000, None, True),
    (None, 1000, True),
    (0, None, True),
    (None, None, False),
])
def test_legacy_cycle_membership_is_backfilled_once(
    db_session, local_target, manager_target, expected,
):
    employee = Employee(
        associate_id='MIGRATION002',
        associate='Fictional Legacy Participant',
        bonus_target_local_currency=local_target,
        bonus_target_manager_currency=manager_target,
    )
    db_session.add(employee)
    db_session.commit()
    engine = db_session.get_bind()
    # Simulate an existing database from before cycle membership was added.
    with engine.begin() as connection:
        connection.execute(text(
            'ALTER TABLE employees DROP COLUMN in_current_bonus_cycle'
        ))

    migrate_add_new_columns(engine)
    migrate_backfill_bonus_cycle_flag(engine)

    db_session.refresh(employee)
    assert employee.in_current_bonus_cycle is expected

    # A subsequent import can exclude the employee without losing targets.
    employee.in_current_bonus_cycle = False
    db_session.commit()
    migrate_add_new_columns(engine)
    migrate_backfill_bonus_cycle_flag(engine)
    db_session.refresh(employee)
    assert employee.in_current_bonus_cycle is False
