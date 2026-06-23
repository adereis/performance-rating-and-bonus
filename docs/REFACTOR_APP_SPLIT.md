# Refactor plan: split app.py into blueprints + finish the services migration

Status: **planned, not started.** A durable, executable plan for the second
high-impact architectural change (the first was the frontend module layer — see
git history around `static/js/common.js` / `employee-form.js`).

## Why

`app.py` is a 4,449-line god-module: 32 routes mixing thin wrappers with heavy
business logic, plus request hooks, filters, and app-local helpers. The cost is
the same duplication-induced drift we keep fixing:

- `import_current()` is one ~720-line route handler.
- `export_snapshot_xlsx()` (~315 lines) and `export_snapshot_csv()` (~300) are
  near-duplicate row-builders **in the route layer** (~600 lines).
- the tenet-parse block (`tenets_map` + `json.loads`) appears ~33×; snapshot row
  writes (`ws_bonus/ws_talent.cell`) ~38× — inline instead of one builder.
- Several bugs fixed this session were server-side copies that drifted: the blank
  `Bonus % of Target` export column (wrong key in 3 places), the tenet-parse
  blocks that logged employee names.

**Goal:** routes become thin (parse request → call a service → shape response);
business logic lives in `services/` (which already exists and is half-used);
routes are grouped into Flask blueprints so the file is navigable and the
duplication has one home.

## Principles (do not violate)

1. **Behavior-preserving.** This is a *move*, not a rewrite. No endpoint, payload,
   or response-shape changes. The 540-test suite must stay green at every commit.
2. **Incremental, one blueprint per commit.** Never a big-bang. Each commit is a
   self-contained, reviewable move.
3. **Blueprints register on the EXISTING `app`.** You do NOT need an app factory
   first — `app.register_blueprint(bp)` works on the module-level `app`. The
   factory (`create_app()`) is the LAST phase, optional, and only to clean up
   config/globals.
4. **Single source of truth.** When two routes build the same thing (the export
   row builders, the tenet parse), collapse into one `services/` function as you
   move them — that's where the value is, not the file split alone.
5. **Test-gated.** `python3 -m pytest tests/` after every commit, plus the
   interactive smoke tour (`docs/INTERACTIVE_TESTING.md`) — most of this code is
   exercised only through rendered pages and JS the Python suite can't see.
6. **Clean, reviewable history.** Run principle 5's gate *before* committing each
   phase, so when a test breaks because the move is intentional, its fix folds
   into that same commit — not a separate "oops" commit. If churn slips in anyway
   (a bug you introduce, then fix), `git rebase -i` / fixup / squash it into its
   logical parent before the work is done. The final history should read as **one
   coherent commit per blueprint/dedup** telling the story of the split, not the
   messy path you took to get there. Do **not** push until the human asks.

## ⚠️ The gotcha that WILL bite you: endpoint renaming

Moving `def index()` into a `core` blueprint renames its endpoint from `index`
to `core.index`. That silently breaks:

- **`url_for('index')`** everywhere (templates use `url_for('rate_page')`,
  `url_for('export_page')`, etc. — grep `url_for(` in `templates/`).
- **`request.endpoint == 'rate_page'`** checks — e.g. the nav active-state in
  `base.html` and the filter-toggle visibility gate
  (`request.endpoint not in ['history_page']`).
- **`redirect(url_for(...))`** inside handlers (e.g. `demo_init` → `rate_page`).

Mitigations, in order of preference:
1. Keep endpoint **names stable** by passing `name=` when registering routes, or
   name blueprint view functions to match, OR
2. Update every `url_for('X')` → `url_for('bp.X')` and every
   `request.endpoint == 'X'` → `'bp.X'` in the same commit that moves the route.
   Grep both `templates/` and `app.py`/blueprints for the old endpoint name.

There is a regression test for this risk class already: the nav/active-state and
filter-visibility are covered by `tests/test_filter_integration.py` and the
interactive smoke tour — run both after each move.

## Target structure

```
app.py                      # create_app() (final phase) or thin: app + register_blueprint calls
blueprints/
  __init__.py
  core.py        # /, /health, /demo/<type>, /api/demo/reset
  rate.py        # /rate, /api/rate, /api/bonus-settings[, verify-pool], /api/tenets, /api/employee/<id>[/history]
  calibrate.py   # /calibrate, /api/calibrate, /api/calibrate/status
  bonus.py       # /bonus-calculation
  analytics.py   # /analytics
  export.py      # /export, /export/csv, /export/xlsx, /export/talent[/csv], /export/snapshot/{xlsx,csv}
  import_.py     # /import, /api/import/{analyze,current,historical}
  history.py     # /history, /api/archive-period, /api/periods, /api/period/<id>, /api/period-comparison/<id>
services/        # existing — logic lands here (analytics, bonus, export, import_handler, db_helpers, employee_utils)
config.py        # Config class (final phase)
```

**Stays app-level (registered once, not in a blueprint):** the 3 template filters
(`format_currency`, `pct`, `fromjson`), the context processor
(`inject_global_context`), the request hooks (`log_demo_request`,
`add_demo_session_cookie`), and the error handlers. The app-local helper functions
(`get_all_employees`, `get_manager_currency`, `get_employee_by_id`,
`get_bonus_settings`, `update_bonus_settings`, `get_filter_params`,
`apply_employee_filters`) should move into `services/db_helpers.py` (several already
have equivalents there) so blueprints import them instead of from `app`.

## Sequencing (lowest-risk / highest-value first)

Each phase = one or a few commits, tests + smoke tour green before moving on.

- **Phase 0 — Dedupe the snapshot export builders (no route move).** Collapse
  `export_snapshot_xlsx`/`export_snapshot_csv` onto shared row-builders in
  `services/export.py` (it already has `prepare_snapshot_bonus_row` /
  `prepare_snapshot_talent_row` — the routes just don't all call them). ~600
  lines of drift-prone duplication retired. **Best first slice: high value, low
  risk, no endpoint changes.** Verify: `/export/snapshot/{xlsx,csv}` download and
  match prior output; `tests/test_export_sync.py` + snapshot tests green.

- **Phase 1 — Move app-local helpers into `services/db_helpers.py`.** No route
  moves yet; just relocate the 7 helper functions and update `app.py` imports.
  Unblocks blueprints (they'll import helpers from services, not app). Pure move.

- **Phase 2 — `export` blueprint.** All `/export/*` routes (self-contained,
  already call `services/export`; cleaner after Phase 0). First real blueprint —
  establishes the pattern. Watch `url_for('export_page')` in nav.

- **Phase 3 — `history` blueprint.** history/periods routes (fairly isolated).

- **Phase 4 — `import_` blueprint.** The import routes. `import_current()` (~720
  lines) is the biggest win: push its field-comparison/apply logic into
  `services/import_handler.py` (which already has `update_*_field`/`apply_*`
  helpers it doesn't fully use). High value, higher risk — lean on
  `tests/test_import_api.py` + a real upload via the SOP.

- **Phase 5 — `analytics` + `bonus` blueprints.** Mostly read-only render routes.

- **Phase 6 — `rate` + `calibrate` + employee-detail blueprints.** These share the
  most helpers and the modal endpoints; do them after the helpers are in services.

- **Phase 7 — `core` blueprint + app factory + `Config`.** Move `/`, `/health`,
  demo routes; introduce `create_app(config)` and a `Config` class that
  **fails fast if `SECRET_KEY` is unset in production** (currently a silent dev
  default). This also fixes the test monkeypatching seen in the demo-cookie and
  import-gating tests (they patch module globals like `app.DEMO_MODE` — a config
  object passed to `create_app` is cleaner). Update `conftest.py` to build the
  test app via the factory.

## Per-commit definition of done

- `python3 -m pytest tests/ -q` green.
- Interactive smoke tour green (8 pages, 0 pageerrors) per `docs/INTERACTIVE_TESTING.md`.
- For any moved route: its page/endpoint still works (click through it), and
  `grep -rn "url_for('<old_endpoint>')\|endpoint == '<old_endpoint>'"` returns
  nothing stale.
- Commit message states what moved and that behavior is unchanged.
- After finishing a phase, its history is clean: one coherent commit per
  blueprint/dedup, any introduced-then-fixed churn squashed away (principle 6).
  Work stays local — don't push until the human asks.

## What this unblocks

Once routes are thin and logic is in `services/`, the other backlog items get a
clean home: Alembic migrations, money-as-integer-cents, and a typed employee
DTO to decouple from Workday column-name dicts (see the review backlog).

## Estimated shape

~8 blueprints, ~10–14 commits across the phases. Phase 0 alone (export dedup) is
a worthwhile standalone improvement if the full split isn't undertaken.
