# DeltaConvert — static multi-page interface

A dark fintech interface on the black, white, aqua, teal and orange brand
palette, served as plain HTML, CSS and JavaScript. Two features are wired
to the live DeltaConvert API; the rest of the site is a labelled demo.

## Pages

- `index.html` — landing page; the hero quote, GBP→EUR card and GBP/USD
  signal card show live ECB figures when the API is reachable
- `exchange.html` — the main page. Live ECB reference rates and the
  converter come first, then the forecast for the same pair: horizon
  presets, chart with an 80 per cent band, day-by-day table and the
  public next-day track record. Settlement paces, fees and the quote
  lock are demo values
- `markets.html` — demo stock wall, search, lenses, watchlist and drawer
- `portfolio.html` — demo holdings ledger, allocation chart and CSV export
- `alerts.html` — demo rule composer and digest schedule

## Files

- `styles.css` — shared responsive layout and visual system
- `app.js` — shared interactions, canvas charts, browser storage and the
  live data layer (see the "Live data layer" section near the top)

## Live data

The API base path comes from a meta tag in each page head:

```html
<meta name="api-base" content="/api/v1">
```

In production, nginx proxies `/api/` to the backend, so the default value
works unchanged. Live currency data comes from four endpoints: `GET /currencies`,
`GET /rates/latest`, `GET /rates/history` and `POST /predict`, plus
`GET /audit/scoreboard` for the track record. The currency dropdowns are
built from `GET /currencies`, so trimming the backend's supported list or
training only some models changes the interface with no edit here. When the API is
unreachable, the Exchange page says so and falls back to labelled sample
figures; the Forecast page reports the error.

## Look at the interface without a backend

Double-click `index.html`. All five pages work offline. The Exchange
page labels its figures as samples and says the service is not
connected. Nothing else is needed for a design review.

## Run locally

Option one, the full stack: `.\dev.ps1 up --build -d` from the
repository root (see START-LOCAL.md), then open http://localhost/.

Option two, frontend against a bare backend: start the API with uvicorn
on port 8000 with `ENVIRONMENT=development` set (the API accepts these
local origins only in development), change the meta tag in each page you
are testing to `http://localhost:8000/api/v1`, then serve this folder
with:

```bash
python3 -m http.server 5173
```

and open http://localhost:5173. Port 5173 is already in the backend's
development CORS list. Revert the meta tag before deployment.

## Data notes

Watchlists, holdings, alert rules and digest settings are demo features
stored in `localStorage`. Stock prices and portfolio figures are sample
values. Live exchange rates are ECB daily reference rates and the
forecast is a statistical estimate; both are indicative only and neither
is financial advice.

## Charts

Every chart uses the same engine in `app.js` (`RateChart`): a deep teal
line at width 3 over a gradient fill that fades to transparent, an orange
dot on the final point, a value axis with labels, a date axis with as
many ticks as the width allows, an optional dashed forecast line with its
80 per cent band, and a crosshair with a tooltip that follows the
pointer. Canvases size themselves to their container and redraw on
resize, so they always fill the card.

One thing to keep in mind when adding elements that use the `hidden`
attribute: the browser hides them through `[hidden] { display: none }`,
which any class rule setting `display` will override. Pair every such
rule with its own `[hidden]` rule, as `.chart-tooltip` and
`.forecast-summary` do.
