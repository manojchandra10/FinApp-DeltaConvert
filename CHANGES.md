# Security release

Date: 4 November 2026

Fixes for the 26 issues described in SECURITY-REPORT.md, with the evidence
for each. The look of the site is unchanged. Before the next deployment,
follow "SECURITY RELEASE" in README-DEPLOYMENT.md: a new `.env` with
strong secrets, a rebuild of both images without cache, the new cron
command, and the server hardening steps.

- Backend: model and scaler files load without running code; forecasts
  are computed once per currency per data snapshot; rate limiter, admin
  endpoint, CORS, docs and the ECB fetcher hardened; dependencies
  upgraded (pip-audit clean); security regression tests added.
- Site: escaping for currency codes and alert ids, CSV formula cells
  neutralised, stored data checked before use.
- Infrastructure: security headers and a Content-Security-Policy on every
  response, stricter TLS and host handling, non-root backend container,
  `.dockerignore` files, required database password, automatic
  certificate reloads, log rotation, local ports on 127.0.0.1.
- Guides: server details removed, server hardening added, local setup
  through `dev.ps1`.

---

# Changes — new interface, live rates wired, Forecast page added

Date: 19 July 2026

## Summary

The site now runs on the new static multi-page template (plain HTML, CSS
and JS) under the DeltaConvert name; TIKIT was a placeholder and is gone.
Two features are wired to the backend and treated as production: live ECB
reference rates on the Exchange page and the multi-day model forecast on
a new Forecast page. Markets, Portfolio and Alerts remain labelled demos
with sample data, exactly as agreed, until they are built for real. The
React app in `stochastix/interface/` is retired.

## Frontend

- Rebrand across all pages: brand lockup, titles, meta tags, footer,
  aria labels, localStorage keys (`deltaconvert-*`) and the CSV export
  filename. The landing hero reads "DeltaConvert tells you when."
- The forecast sits on the Exchange page as a second section rather than
  on a page of its own. Live rates and the converter come first, then
  "Forecast — 1 GBP in EUR" for whichever pair is selected above, with
  horizon presets (7/30/60/90 days), the chart, a day-by-day table of
  rate, low and high, and the public next-day track record. Changing
  currency at the top updates the forecast heading and, once a forecast
  has been run, re-runs it for the new pair.
- New chart engine (`RateChart` in app.js) used by every chart on the
  site. It draws a value axis with labels, a date axis with as many
  ticks as the width allows, an optional forecast band, and a crosshair
  with a tooltip carrying the date, the value, the unit and the band
  range. Canvases size themselves to their container through a
  ResizeObserver, so a chart always fills its card at any zoom level and
  never overflows it. The earlier version had no axes, three fixed date
  labels, no interaction, and a canvas that could grow wider than its
  panel.
- Forecast table restored. The React app had one and the first rewrite
  dropped it.
- The allocation doughnut on Portfolio responds to hover: the segment
  lifts and the centre shows that category's share.
- Exchange page wired to live data: the converter and quote use real ECB
  cross rates, the chart shows real daily history over 1W/1M/6M/1Y
  (the 1D tab is gone because the ECB publishes one rate per business
  day), corridor rows show live rates with real day moves, and a source
  note states the rate date and that bank and card rates differ. Fees,
  settlement paces and the quote lock are labelled demo values. If the
  API is unreachable the page says so and falls back to labelled sample
  figures.
- Landing page: the hero GBP/EUR quote, the GBP→EUR route card and the
  GBP/USD signal card show live figures when the API responds; the page
  keeps its illustrative values offline. The capability strip gains a
  fifth entry for the Forecast page and the "Open app" button now opens
  Exchange.
- Navigation carries five entries; the forecast is reached from the
  Exchange page or from the landing page's capability strip.
- All pages carry `<meta name="api-base" content="/api/v1">`; the shared
  data layer in app.js reads it, so pointing the frontend at a bare local
  backend is a one-line change per page.
- Currency pickers on Exchange and Forecast now list all 30 supported
  currencies; symbols come from Intl so every code renders sensibly.
- Footer disclaimer updated: rates and forecasts are indicative only,
  demo areas use sample figures, nothing is financial advice.
- `robots.txt` and `sitemap.xml` cover the six pages.

## Backend

- New `GET /api/v1/rates/history?base=&quote=&days=` — daily ECB
  reference-rate history for one pair via EUR triangulation, 5 to 1830
  days. Backs the Exchange chart, corridor moves and landing figures.
- (Carried from earlier in this release: `GET /rates/latest`, the
  forecast response cache, honest audit labels, the scoreboard ordering
  fix, the `X-Real-IP` rate-limiter fix, the audit unique constraint with
  its one-off SQL migration, the Keras pin, and the removal of the baked
  `training=True` dropout flag.)

## Infrastructure

- `Dockerfile.nginx` rebuilt: a Node stage minifies `app.js` and
  `styles.css` with esbuild, then nginx ships the result. Minification
  deters casual copying; it cannot hide frontend code, because no site
  can. The models, training code, database and admin token stay
  server-side and never reach the browser.
- nginx serves the multi-page site with a 404 fallback in place of the
  old SPA rewrite, redirects `/stochastix/*` to the forecast section of
  the Exchange page, and
  keeps a one-hour cache on the CSS/JS bundle so deploys propagate
  quickly.
- Both nginx configs name the backend through a variable and Docker's
  embedded resolver (127.0.0.11). The web server now starts on its own,
  which makes `docker compose up -d --no-deps nginx` a working
  frontend-only workflow. Verified against nginx directly: the literal
  form fails with "host not found in upstream" when the backend is
  absent, the variable form passes.
- docker-compose unchanged apart from a comment; container names, project
  name, volumes and the cron entry all stay as they are.

## Chart appearance and tooltip

- The line chart lost its original look in the rewrite. The deep teal
  stroke at width 3, the gradient fill fading to transparent beneath it,
  and the orange dot on the final point are all back, now sitting over
  the labelled axes. The forecast chart keeps the same treatment for its
  history section, with the dashed orange forecast line and aqua band
  past the divider; the legend swatch matches the line colour again.
- The tooltip stayed on screen after the pointer left. Setting
  `hidden = true` had no effect because the browser hides such elements
  through `[hidden] { display: none }` in its own stylesheet, and
  `.chart-tooltip { display: grid }` outranks it. Added the matching
  `[hidden]` rules for the tooltip, the forecast summary tiles and the
  forecast table.
- Currency default returned to all 29. The three-currency line in
  `docker-compose.override.yml` is commented out and ready to uncomment
  when training time matters.

## Dependency and fetcher fixes

- `requests-cache` removed. It pulled in attrs and cattrs, and some
  resolved version combinations failed at runtime with "name
  'RequestsCookieJar' is not defined" while serialising a response, which
  made every ECB fetch return zero rows and blocked training. The fetcher
  keeps its own time-based cache instead: one hour for series, thirty
  minutes for latest rates, bounded at 64 entries. `requests` is now
  pinned. Three dependencies fewer.
- Ticker parsing corrected. `"EUREUR".replace("EUR", "")` stripped both
  occurrences and left an empty string, so EUR-based history requests
  built the all-currencies URL and pulled every series at once instead of
  returning a constant 1.0. Only the leading EUR is removed now.

## Currency configuration

- One environment variable now drives both lists. `CURRENCIES=GBP,USD,INR`
  sets what the API accepts and what the trainer builds; leaving it unset
  gives all 29. Previously the two lists sat in separate files and could
  drift apart silently. EUR is added automatically because every model is
  quoted against it and it needs none of its own.
- `docker-compose.override.yml` sets the three-currency set for local
  runs, so training finishes in minutes. Production never sets it.
- The forecast note quoted the wrong date. Rows typed `indicative` carry
  the last published rate forward across weekends, and the note treated
  the final one as an ECB rate. It now names the last genuinely published
  date.

## Capability discovery

- New `GET /api/v1/currencies` returns `supported` (what the converter and
  history charts accept) and `forecastable` (those with a trained model
  on disk; EUR counts because every model is quoted against it).
- The frontend built its dropdowns from a hardcoded list of 30 codes,
  which broke as soon as the backend supported fewer. It now takes the
  list from `/currencies` and rebuilds the themed dropdowns, falling back
  to the 30-code list when the backend is unreachable.
- The Run forecast button turns itself off when either leg has no trained
  model, and the note states which pairs are trained. Previously the run
  failed with a 503 after the fact.
- Model warmup at startup now reads the models directory rather than a
  fixed list of four currencies, so a partial training run no longer logs
  failures for models that were never meant to exist.

## Local development files

- `stochastix/cortex/Dockerfile` — the backend image definition was never
  among the project files supplied, so the stack could not build from a
  clean checkout. Reconstructed to match what the code expects:
  `/app/cortex/models`, `PYTHONPATH=/app`, uvicorn on
  `cortex.app.main:app`, plus `libgomp1` for scikit-learn and TensorFlow.
  If the server already has a working copy, keep the server's.
- `.env.example` — template for an optional `.env`. Compose no longer
  requires the file: every interpolation carries a local default, and
  `env_file` is marked `required: false`, so a fresh copy of the folder
  starts without any setup step. `ADMIN_SECRET` deliberately has no
  default, and the audit-resolve endpoint already refuses every request
  when it is blank.
- `nginx/nginx.local.conf` — plain HTTP on port 80. The production config
  reads a Let's Encrypt certificate that does not exist on a laptop, so
  nginx would refuse to start.
- `docker-compose.override.yml` — read automatically by Compose on the
  development machine: selects the local nginx config, drops the health
  gate so the site appears while TensorFlow imports, publishes port 8000
  and switches the API docs on. This file must never reach the server.
- `Dockerfile.nginx` takes an `NGINX_CONF` build argument that picks
  between the two configs; the production default is unchanged.
- `START-LOCAL.md` — Windows setup and troubleshooting.

## Removal checklist additions

Alongside the converter steps already listed in README-DEPLOYMENT.md:
delete `stochastix/interface/` on the server and in the local deployment
folder. The old `/stochastix/` URLs redirect to the Forecast page.

## Open items

- Benchmark the forecaster against a naive "tomorrow equals today"
  baseline on held-out data. Until that comparison exists, the honest
  position is that the network's advantage is unproven; the Forecast
  page's reading guide says as much to users.
- Real-time rates. ECB publishes one reference rate per business day
  around 16:00 CET. Genuinely live pricing needs a market data provider
  with an API key and a licence that permits display; the key would sit
  in `.env` and requests would go through the backend. Rate retrieval is
  isolated in `fetcher.py`, so the swap touches one module plus the
  source note in the UI.
- Currency coverage. The ECB set omits PKR, BDT, NGN, LKR and VND, which
  are core currencies for the international-student audience. A second
  data source is the only fix.
- A favicon: the pages currently reference none, so browsers request
  /favicon.ico and receive a 404. Harmless, easy to add later.
- The "How to read this" explainer panel has been removed at your
  request. The honesty note under the chart still states that the band
  covers roughly 80 per cent of outcomes, that it widens with the
  horizon, and that the estimate is often wrong.
- Naming: parked. The brand sits behind the lockup markup, titles and
  the `APP_BRAND` env variable.
