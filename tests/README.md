# Test suite

Run the suite from the repository root using the project Python environment.
Keep temporary databases under the project's required temporary directory:

```bash
mkdir -p ~/tmp
TMPDIR="$HOME/tmp" python3 -m pytest tests/ -v
```

Run a focused area while iterating:

```bash
TMPDIR="$HOME/tmp" python3 -m pytest tests/test_migrations.py -q
TMPDIR="$HOME/tmp" python3 -m pytest tests/test_import_api.py tests/test_workday_format.py -q
TMPDIR="$HOME/tmp" python3 -m pytest tests/test_api.py -q -k TestNumericInputValidation
```

## Shared fixtures and isolation

Use [conftest.py](conftest.py) for database and Flask tests. It sets `TESTING=true`
before importing the application, preventing production database initialization.
The real `models.get_db()` also rejects unpatched access in testing mode.

- `test_db` creates and disposes an isolated SQLite database per test.
- `db_session` provides a session against that database.
- `app` and `client` patch database access and render with Jinja
  `StrictUndefined`, catching missing template context.
- `populated_db` and `populated_db_with_tenets` supply fictitious employees.
- `sample_tenets` supplies the sample tenets without writing `tenets.json`.
- `talent_xlsx_file` supplies a generated talent workbook.

Test employees default to current bonus-cycle membership; explicitly pass
`in_current_bonus_cycle=False` when testing exclusions. For legacy nullable
columns, use SQL where necessary to bypass SQLAlchemy insertion defaults.
Never point tests at `ratings.db` or use real employee exports.

## Coverage areas

| Modules | Responsibility |
| --- | --- |
| `test_models.py`, `test_migrations.py` | Persistence, schema upgrades, startup data preservation |
| `test_api.py`, `test_employee_modal.py` | API validation, partial updates, server-rendered pages |
| `test_import_api.py`, `test_workday_format.py`, `test_notes_parser.py` | Workbook formats, currency, imports, round-tripping |
| `test_export_sync.py`, `test_export_snapshot.py`, `test_archive.py` | Export modification tracking, snapshots, history |
| Talent, tenet, mentorship, filter, and multi-org modules | Domain rules and reporting |
| `test_demo_mode.py` | Session IDs, cookies, database lifecycle helpers |
| `test_scripts.py` | Sample generation and command-line tools |

Use pytest collection output for the current test count. Python dependencies
are specified in [requirements.txt](../requirements.txt).

Pytest does not execute browser JavaScript or establish safety across multiple
server processes. After UI changes, follow
[INTERACTIVE_TESTING.md](../docs/INTERACTIVE_TESTING.md). Known gaps and remaining
architecture findings are recorded in
[ARCHITECTURE_REVIEW.md](../docs/ARCHITECTURE_REVIEW.md).
