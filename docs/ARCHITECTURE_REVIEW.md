# Architecture review — 2026-09-10

The blueprint split provides useful boundaries, especially the pure bonus and
employee utility functions. The main remaining risks are state lifecycle,
unescaped browser rendering, and exceptional bonus pools. This review started
at `a206b67` and includes the focused fixes listed below.

## Remaining findings

### P1: Imported text can become executable HTML

In [templates/import.html](../templates/import.html), the allocation notice
interpolates workbook employee names directly into `innerHTML`. In
[templates/base.html](../templates/base.html), `renderEmployeeModal()` does the
same with associate IDs, job profiles, organizations, currency, and tenure.
Jinja autoescaping does not protect JSON values interpolated by JavaScript.
Markup in an imported value is interpreted as HTML, including event handlers
with access to the application's same-origin APIs.

Use text nodes for plain values and the existing `App.escapeHtml`/`escapeAttr`
helpers for the appropriate HTML context. Audit both employee entry surfaces
and import/history rendering together. Add browser checks with fictitious
markup in text and attribute fields. This is a source-level finding; browser
execution was not exercised during this review.

### P1: Worker startup and cleanup can delete active demo sessions

[app.py](../app.py) calls `clear_all_sessions()` from `create_app()`.
[demo_mode.py](../demo_mode.py) puts workers belonging to the same server in
the same session directory. Starting or replacing a worker therefore removes
existing visitors' databases. A temporary probe using the shared pytest
fixtures confirmed that creating an app removes an existing session file.

The lifecycle needs a coordinated fix: cleanup relies on process-local access
times, so one worker cannot see activity handled by another. Reset also copies
to a fixed `.tmp` name and deletes the live database before renaming the copy.
That leaves a gap in the claimed atomic replacement and can conflict with
other workers' open WAL connections. These races were identified from source,
not reproduced with concurrent workers.

Move destructive initialization out of per-worker app creation, establish
cross-process session ownership/activity tracking, and coordinate reset,
request access, and expiry. Validate worker replacement, concurrent requests,
and reset/cleanup overlap together. The committed cookie recovery fix does not
claim to solve these lifecycle issues.

### P1: Fixed-pool normalization does not cover infeasible allocations

In [services/bonus.py](../services/bonus.py), overrides are paid in full and the
remaining pool is clamped to zero. A deterministic fictitious case with two
10,000 targets, one 200% override, and a 15,000 Workday pool returns 20,000
allocated. The existing over-pool test checks nonnegative payouts, not total
spend. Separately, a 10,000 target with a zero rating leaves a 10,000 pool
entirely unallocated because all raw shares are zero.

These cases need an explicit domain decision: exact overrides, zero awards,
and exact pool exhaustion cannot always hold simultaneously. Represent an
infeasible allocation or residual pool explicitly and make calculation and
export flows handle it consistently. Do not silently rescale fixed overrides
or increase zero-rated payouts as an incidental review fix.

### P2: Archiving clears inputs it did not snapshot

In [blueprints/history.py](../blueprints/history.py), `archive_period()` skips
employees without a numeric performance rating, then clears justification,
mentorship, and tenets for every employee. An unfinished evaluation with notes
can disappear without a historical record. The query also spans employees
outside the current bonus cycle.

Define which cycle and which drafts the archive action owns. Snapshot the
inputs being cleared, or retain drafts outside that scope, and test unrated
employees and employees excluded from the current cycle. This is a source-level
finding; the archive policy was not changed in this review.

### P2: Error handling conflicts with privacy and recovery guarantees

[blueprints/export.py](../blueprints/export.py) logs employee names on tenet
parse failures. [app.py](../app.py) logs raw exception strings; database
exceptions can contain bound values. Several APIs also return raw exceptions.
Use diagnostics that retain operation and error type without employee values,
and test failure paths with fictitious sensitive markers.

The schema-error page advises deleting the database and claims re-import will
lose no data. Unsynced manager inputs and local history are not necessarily in
Workday. Recovery guidance should preserve the database and support repair or
migration before any destructive action.

## Architecture follow-up

- **Make configuration and persistence belong to the Flask app.** `Config`
  reads the environment at construction, but `app`, `models`, and `demo_mode`
  retain independent module-level mode flags and shared engine state.
  `create_app(config)` copies only selected settings. A temporary fixture-based
  probe confirmed that a config with `DEMO_MODE=True` is not installed in
  `flask_app.config` and does not change request/database mode globals.
  App extensions and `current_app.config` would provide one ownership boundary.
  Test two differently configured apps in one process when making that change.
- **Finish moving import behavior, not just filenames.** The roughly
  1,000-line [import blueprint](../blueprints/import_.py) still implements
  preservation and change reporting inline. `apply_bonus_import*` and
  `apply_talent_import*` in [services/import_handler.py](../services/import_handler.py)
  have no callers. Keeping two implementations invites fixes in the inactive
  copy. Reconcile them against round-trip tests, then retain one implementation
  with the transaction owned by the import operation.
- **Preserve the existing useful boundaries.** Bonus computation and employee
  utilities are independently testable; import mutations share one commit and
  rollback; shared fixtures protect the production database. Consolidate
  duplicated completion/validation logic and browser save handling around
  these existing boundaries rather than adopting a different framework.

## Completed fixes

| Commit | Change | Verification |
| --- | --- | --- |
| `9281bd6` | Preserve explicit bonus-cycle exclusions across startup; backfill only legacy NULL membership. | Five migration tests; four failed before the fix. |
| `45e62e7` | Persist analyzed manager currency, including all-international teams and header fallback. | Four new regressions; 76 import/format tests passed. |
| `8c39021` | Reject non-finite numbers, booleans, invalid JSON shapes, and negative budgets without changing stored inputs. | 35 new cases; all 107 API tests passed. |
| `fa77677` | Persist replacement demo cookies so subsequent requests retain the same session. | Two new regressions; all 40 demo tests passed. |
| `0308107` | Ignore the default database's WAL and shared-memory files. | Explicit ignore checks for the database and its three sidecars. |

## Validation scope

The unchanged baseline passed 540 tests. The final full suite passed all 586
tests in 97.64 seconds, including 46 added regression cases using shared
fixtures and fictitious data. Targeted suites also passed before their
respective commits. Test databases and logs are kept under a private directory
in `~/tmp`. The production database and real exports were not used.

The two temporary architecture probes assert the observed startup/configuration
defects; they are diagnostic evidence, not tests claiming those defects are
fixed. Bonus edge cases were reproduced through the pure calculation function.
No templates or client-side JavaScript were changed.
