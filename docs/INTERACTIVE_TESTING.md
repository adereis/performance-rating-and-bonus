# Interactive & Agentic Testing Guide

How to run the app and drive it through a real browser to verify changes that the
Python test suite **cannot** see: rendering, CSS, client-side JavaScript, the
employee modal, charts, the global filter, and demo-mode session isolation.

> The pytest suite (`python3 -m pytest tests/`) covers server logic and must stay
> green first. This guide is for everything *after* that — the things that only
> break in a browser. Several of this codebase's worst historical bugs (the modal
> wiping promotion data, the tenets UI crashing) were client-side JS that no
> Python test could catch.

Audience: humans and AI agents. No framework or build step is required — the app
serves plain templates + vanilla JS, and we drive it with headless Chrome.

---

## TL;DR checklist (run this after any UI change)

1. `python3 -m pytest tests/ -q` → must be green.
2. Start the app (see [Running the app](#running-the-app)). **Restart it after any
   `.html`/template or Python change** (Jinja caches templates in production mode;
   only `static/` CSS/JS reload without a restart).
3. Screenshot-tour all 8 pages, asserting `pageerror == 0` (see [Smoke tour](#smoke-tour-all-pages)).
4. Verify the flows your change touched ([Per-area checks](#what-to-verify-after-specific-changes)).
5. Stop the server (kill **by port**, not `pkill` — see [gotchas](#environment-gotchas-read-this-first)).

---

## Environment gotchas (read this first)

These are non-obvious and will waste your time if you don't know them:

| Gotcha | Why | Do this instead |
|---|---|---|
| **Foreground `sleep` may be blocked** in sandboxed shells (hangs until timeout). | The shell sandbox blocks it. | Wait for readiness with curl's own retry: `curl --retry 25 --retry-connrefused --retry-delay 1 --max-time 3 <url>`. Never a `sleep` poll loop. |
| **`pkill -f "python app.py"` kills its own launcher.** | `pkill -f` matches the launching shell's command line too (it contains "python app.py"). | Kill **by listening port** (the launcher doesn't listen): see [Stopping the server](#stopping-the-server). |
| **Template/HTML edits don't take effect until restart.** | Jinja caches compiled templates when `FLASK_ENV != development`. | Restart the server after any `templates/*.html` or `*.py` change. `static/css` and `static/js` reload **without** a restart. |
| **`/health` can give a transient false "down" at startup.** | Race between bind and the readiness probe. | Confirm with an actual request (e.g. `curl -s -o /dev/null -w '%{http_code}' <url>/`) before concluding it's down. |
| **Capture console + page errors** — they catch bugs before you click anything. | The tenets crash showed up as a `pageerror` on load. | Always attach `page.on('console')` and `page.on('pageerror')`. |
| **`tenets.json` controls the tenet UI.** Absent → "No tenets configured" (handled gracefully now; used to crash). | Tenet config is an optional file. | For full tenet testing: `cp samples/tenets-sample.json tenets.json` (gitignored). |
| **Demo isolation needs separate browser *contexts*.** | One context = one cookie = one session DB. | Use `browser.newContext()` per simulated visitor. |
| **Never point the app at the real `ratings.db`.** | It holds real data. | Always set `DATABASE_URL` to a throwaway path (normal mode) or use demo mode. |

---

## One-time setup

```bash
# 1. venv (uses system site-packages so most deps come from signed RPMs)
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt

# 2. Generate fully-populated sample databases (employees + ratings + talent + tenets)
.venv/bin/python scripts/generate-demo-templates.py
#   -> writes demo-templates/small-team.db (12 employees)
#               demo-templates/large-team.db (55 employees incl. 5 managers, multi-org)
#   NOTE: the --output-dir flag is currently a no-op; it always writes to demo-templates/.

# 3. Browser driver: playwright-core uses the SYSTEM Chrome (no bundled-browser download)
mkdir -p ~/tmp/uitest && cd ~/tmp/uitest && npm install playwright-core
#   Run all driver scripts from this dir so `require('playwright-core')` resolves.
#   Find your Chrome: command -v google-chrome-stable || command -v chromium
```

The **large team** is best for testing manager/multi-org features (it has 5 managers
and several orgs, so the bonus page shows multi-team tabs and the exclude-managers
filter has a visible effect).

---

## Running the app

Pick a throwaway DB and a non-default port. The screenshots/scripts below assume
port **5050**.

### Normal mode (sample data; import enabled)

```bash
cp demo-templates/large-team.db ~/tmp/uitest/app.db          # throwaway copy
DATABASE_URL="sqlite:///$HOME/tmp/uitest/app.db" SECRET_KEY=uitest-secret-key \
FLASK_HOST=127.0.0.1 FLASK_PORT=5050 FLASK_ENV=production PYTHONUNBUFFERED=1 \
  .venv/bin/python app.py > ~/tmp/uitest/flask.log 2>&1 &
# SECRET_KEY is REQUIRED with FLASK_ENV=production (config.py fails fast without it).
# wait for readiness (no sleep!):
curl -s --retry 25 --retry-connrefused --retry-delay 1 --max-time 3 http://127.0.0.1:5050/health
```

### Demo mode (session-isolated; import disabled)

```bash
mkdir -p ~/tmp/demo_sessions
DEMO_MODE=true SESSION_DB_DIR="$HOME/tmp/demo_sessions" SECRET_KEY=uitest-secret-key \
FLASK_HOST=127.0.0.1 FLASK_PORT=5050 FLASK_ENV=production PYTHONUNBUFFERED=1 \
  .venv/bin/python app.py > ~/tmp/uitest/flask_demo.log 2>&1 &
curl -s --retry 25 --retry-connrefused --retry-delay 1 --max-time 3 http://127.0.0.1:5050/health
# Then load data by visiting /demo/large (or /demo/small) in the browser.
```

### Stopping the server

```bash
# Kill by listening port — NOT `pkill -f "python app.py"` (which kills the launcher).
PID=$(ss -ltnp 2>/dev/null | grep ':5050' | grep -oP 'pid=\K[0-9]+' | head -1)
[ -n "$PID" ] && kill "$PID"
```

To restart after a template/Python change: stop (by port) then start again.

---

## The browser harness

Run these from `~/tmp/uitest` (where `playwright-core` is installed). The pattern:
launch the system Chrome headless, capture console/page errors, screenshot to a
file, then view the file. Agents: the `Read` tool renders PNGs, so screenshot →
Read is how you "see" the result.

```js
// harness skeleton — save as ~/tmp/uitest/<name>.js, run with `node <name>.js`
const { chromium } = require('playwright-core');
const CHROME = '/usr/bin/google-chrome-stable'; // adjust per `command -v`
const BASE = 'http://127.0.0.1:5050';

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox', '--disable-gpu'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console.error: ' + m.text()); });

  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.screenshot({ path: 'shot.png' });
  console.log('pageerrors:', errors.length, errors.slice(0, 3));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
```

---

## Smoke tour (all pages)

The cheapest high-value check: every page must load with **zero page errors** and
render its icons. A `pageerror > 0` on load is how the tenets crash was caught.

```js
const { chromium } = require('playwright-core');
const BASE = 'http://127.0.0.1:5050', CHROME = '/usr/bin/google-chrome-stable';
const PAGES = [['index','/'],['rate','/rate'],['calibrate','/calibrate'],['analytics','/analytics'],
               ['bonus','/bonus-calculation'],['export','/export'],['history','/history'],['import','/import']];
(async () => {
  const b = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox','--disable-gpu'] });
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  for (const [name, path] of PAGES) {
    const p = await ctx.newPage(); const errs = [];
    p.on('pageerror', e => errs.push(e.message));
    p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    const r = await p.goto(BASE + path, { waitUntil: 'networkidle' });
    await p.waitForTimeout(900);
    const icons = await p.$$eval('.icon', els => els.length).catch(() => 0);
    await p.screenshot({ path: `tour-${name}.png` });
    console.log(`${name}: HTTP ${r.status()}  icons=${icons}  jsErr=${errs.length}` + (errs.length ? '  '+errs[0].slice(0,80) : ''));
    await p.close();
  }
  await b.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
```

**Pass criteria:** every page `HTTP 200`, `jsErr=0`, icons present where expected.
Then open the `tour-*.png` files and eyeball layout/legibility.

---

## Key interactive flows

These are the flows the Python suite can't reach. Verify the ones your change touches.

### Employee modal (the dual-entry hazard)
Click any employee name → `#employeeModal.active` appears → fields populated → edit
a field → close. **Regression guard:** after a close-with-changes, fields the modal
*doesn't* render (e.g. `talent_promo_*`, which live only on the Calibrate page) must
be **unchanged** in the DB. To check, set a value via `/api/calibrate`, drive the
modal, then read it back via `/api/employee/<id>` — it must survive. (This is the
exact bug that prompted this guide.)

### Bonus chart
`/bonus-calculation` must contain a `<canvas>` and produce no JS errors. The
performance curve legend should show clean swatches (line / dot / dashed line),
not a garbled box. Large team → multi-team Overview/Comparison/Detailed tabs.

### Global privacy filter (exclude managers)
Open Filters (`#filterToggle`), check `#excludeManagers`, click `.btn-apply`. Expect
a "Filters Active: N employee(s) hidden" banner, the `Filters (N)` badge, and the
employee/stat counts to drop by the manager count (5 on the large team). The filter
is a **global** toggle (it persists across pages via sessionStorage — it's the
"hide names while screen-sharing" feature, so it appears on every page except
History).

### Number formatting
Performance ratings render as `140%`, not `140.0%` (the `pct` Jinja filter).

### Demo mode specifics
- `/demo/large` loads sample data and redirects to `/rate`; the red "DEMO MODE"
  banner is present.
- Imports are blocked server-side: `fetch('/api/import/analyze', {method:'POST'})`
  must return **403** (not just hidden in the UI).
- **Session isolation:** two separate `browser.newContext()` sessions, each loading
  `/demo/large` and editing the *same* employee differently, must read back only
  their own edit. Corroborate at the filesystem level: each session is a distinct
  `session_<uuid>.db` under `SESSION_DB_DIR`, and every filename is a valid UUID
  (proof the cookie is validated and can't carry a path-traversal payload).

---

## What to verify after specific changes

| You changed… | Then verify |
|---|---|
| A `templates/*.html` file | **Restart**, re-run the smoke tour (HTTP 200 + jsErr 0), eyeball the page. |
| `static/css/base.css` or `static/js/*` | No restart needed; re-screenshot the affected pages. |
| Inline JS in a template | Restart; console-error check on those pages; exercise the interaction. |
| Bonus calculation (`services/bonus.py`) | `pytest tests/test_api.py -k bonus`; then the bonus page renders + the curve looks right + numbers sane. |
| Import / parsing (`xlsx_utils.py`, `import_handler.py`) | `pytest tests/test_import_api.py tests/test_workday_format.py`; then a real `POST /api/import/analyze` in **normal** mode. |
| The employee modal or `services/db_helpers` | The modal flow + the dual-entry regression guard above. |
| Demo / session code (`demo_mode.py`) | The session-isolation check (two contexts) + import-403 in demo mode. |
| Manager detection / filters | The exclude-managers flow (count must drop by the exact manager count). |
| Anything | `pytest tests/` green **first** — the browser pass is only for what tests can't see. |

---

## Cleanup

Everything lives outside the repo or is gitignored:

```bash
# stop the server (by port — see above), then:
rm -rf ~/tmp/uitest ~/tmp/demo_sessions   # driver scripts, screenshots, session DBs
rm -f tenets.json                          # if you created it from the sample (gitignored)
# .venv, demo-templates/, and any throwaway *.db are gitignored; remove if desired.
```

Never commit `ratings.db`, real Workday exports, `tenets.json`, or session DBs.
