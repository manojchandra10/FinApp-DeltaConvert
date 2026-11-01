# Running DeltaConvert locally on Windows

Two ways to run this. Start with the first one if you only want to look
at the interface.

---

## A. Frontend only, no Docker, no build (about ten seconds)

Open `D:\MJ\MJFin\site\index.html` by double-clicking it. Every page
works: navigation, the command menu (Ctrl+K), the converter, the forecast
chart, the stock wall, the portfolio table and the alert rules.

With no backend behind it, the pages fall back to sample figures and say
so on screen:

- **Exchange** shows "Live rates unavailable — sample figures shown"
  under the quote. The converter still works across all 30 currencies and
  the chart draws a sample line. Pressing Run forecast lower down the
  same page says "Preview only — the forecast service is not connected"
  and draws a sample history, forecast line, band and table, so the
  layout can be judged. The track record panel says it needs the
  backend.
- **Markets, Portfolio and Alerts** are demo features already, so they
  behave exactly as they will in production.

That is enough to decide whether the design and layout are right. Come
back to part B when you want live rates and real forecasts.

---

## B. Full stack in Docker

Everything below runs inside Docker. Node, npm and Python are not needed
on the machine — the nginx image installs esbuild in its own build stage,
which is why `docker compose build --no-cache nginx` already succeeded.

## What the error meant

`env file D:\MJ\MJFin\.env not found` — the compose file passes secrets to
the backend and the database through a `.env` file, and that file is not
in the zip on purpose. Secrets never travel with code. The blank-string
warnings above the error come from the same missing file.

## One-time setup

Two things are worth setting up before the full stack, and neither
blocks a frontend-only run:

1. **`.env`** — optional. The stack starts without it on weak local
   defaults (user, password and database all `deltaconvert` / `localdev`),
   which is fine for development. Create one only when you want your own
   secrets, or to use the audit-resolve endpoint, which refuses every
   request while `ADMIN_SECRET` is unset:

   ```powershell
   Rename-Item .env.example .env
   ```

   If `.env.example` is not in the folder, write it directly:

   ```powershell
   @"
   POSTGRES_USER=deltaconvert
   POSTGRES_PASSWORD=local_dev_password_change_me
   POSTGRES_DB=deltaconvert
   ADMIN_SECRET=local_dev_admin_token_change_me
   DOMAIN=deltaconvert.com
   APP_BRAND=DeltaConvert
   "@ | Set-Content -Path .env -Encoding utf8
   ```

   The server keeps its own `.env` with real secrets. Note that the
   Postgres volume remembers whichever credentials it was first created
   with, so changing them later means recreating the volume with
   `docker compose down -v`.

2. **`.gitignore`** — the zip carries it as `_gitignore` so it stays
   visible in File Explorer. Rename it before any git work:

   ```powershell
   Rename-Item _gitignore .gitignore
   ```

3. **The trained models** — one `EUR_XXX.keras` and one
   `EUR_XXX_scaler.joblib` per currency.
   They are large binaries and were never in the zip. Copy them from the
   old deployment folder into:

   ```
   D:\MJ\MJFin\stochastix\cortex\models\
   ```

   ```powershell
   New-Item -ItemType Directory -Force D:\MJ\MJFin\stochastix\cortex\models
   Copy-Item D:\DeltaConvert_Deployment\stochastix\cortex\models\* D:\MJ\MJFin\stochastix\cortex\models\
   ```

   Adjust the source path to wherever the old folder actually sits. If
   the models are only on the server, pull them down with scp:

   ```powershell
   scp -r root@204.168.221.119:/root/deltaconvert/stochastix/cortex/models D:\MJ\MJFin\stochastix\cortex\
   ```

   Skipping this step is fine for a first look: live rates work without
   models, and the forecast section says which pairs have a trained model
   instead of drawing a chart.

### Training a small subset

Training all 29 currencies takes 45 to 90 minutes. To test the flow
quickly, trim two lists to the same short set:

- `stochastix/cortex/app/schemas/forecast.py` → `SUPPORTED_CURRENCIES`
- `stochastix/cortex/app/engine/trainer.py` → `CURRENCIES`

Keep `EUR` in `SUPPORTED_CURRENCIES` even though it never appears in
`CURRENCIES`. Every model is quoted against the euro, so EUR pairs need
no model of their own, and leaving it out blocks EUR conversions for no
saving. A useful pair for testing:

```python
SUPPORTED_CURRENCIES = {"GBP", "INR", "EUR"}   # schemas/forecast.py
CURRENCIES = ["GBP", "INR"]                     # engine/trainer.py
```

The interface follows whatever the backend reports through
`GET /api/v1/currencies`. Dropdowns list only supported currencies, and
the Run forecast button turns itself off with an explanation when a pair
has no trained model. No frontend edit is needed.

## Start it

```powershell
cd D:\FinApp\DeltaConvert_Deployment
docker compose up -d db cortex nginx
```

Naming the three services keeps the certbot container out of it, since
certificate renewal makes no sense on a laptop.

The first run builds the backend image and installs TensorFlow, which is
roughly 600 MB, so expect 5 to 15 minutes. Later runs reuse that layer
unless `requirements.txt` changes.

Watch it come up:

```powershell
docker compose ps
docker compose logs -f cortex
```

Wait for `Cortex ready.`, then press Ctrl+C to stop tailing. The
container keeps running.

## Train the models

```powershell
docker exec dc_cortex python -m cortex.app.engine.trainer --force
```

By default all 29 currencies are trained, which takes 45 to 90 minutes
and produces 58 files: `EUR_XXX.keras` and `EUR_XXX_scaler.joblib` for
each. EUR needs no model of its own.

For a quicker run, uncomment this line in `docker-compose.override.yml`
and restart cortex first:

```yaml
      - CURRENCIES=GBP,USD,INR
```

One variable drives the API and the trainer together, so there is no
second list to keep in step. The interface reads
`GET /api/v1/currencies` and offers only what is actually trained.

Either way, copy the models out afterwards so a future image rebuild
does not lose them:

```powershell
docker cp dc_cortex:/app/cortex/models/. D:\FinApp\DeltaConvert_Deployment\stochastix\cortex\models\
```

Models live inside the container until this copy runs, so an empty local
`models\` folder during training is expected.

## Check it

```
http://localhost/                          landing page
http://localhost/exchange.html             live rates and converter
http://localhost/exchange.html#forecast    the forecast section
http://localhost:8000/docs                 API reference (Swagger)
```

Six checks, in order. Each should behave as described.

1. **Backend alive.** `curl http://localhost/health` returns ok.
2. **Currency set.** `curl http://localhost/api/v1/currencies` lists
   `EUR, GBP, INR, USD` under both `supported` and `forecastable`. If
   `forecastable` is short, training has not finished.
3. **Live rates.** `curl http://localhost/api/v1/rates/latest` returns
   four rates and today's or the last business day's `rate_date`.
4. **Converter.** Open the Exchange page. The dropdowns hold four
   currencies, the converted amount fills in, and the note under the
   quote names the ECB publication date. The chart shows labelled rate
   values down the left and several dates along the bottom, and hovering
   gives a crosshair with a tooltip.
5. **Forecast.** Press Run forecast. A dashed line and shaded band appear
   past the divider, three summary tiles fill in, and a table lists one
   row per day. Switch the horizon to 90 and the table grows to 90 rows.
6. **Untrained pair.** Switch to a currency outside the set, if you have
   widened it. The Run forecast button turns itself off and says which
   pairs are trained.

The track record panel stays empty until the daily audit resolves its
first prediction, which needs a forecast stored today and the audit run
tomorrow. That is expected on a fresh database.

## Everyday commands

```powershell
# after editing anything in site\
docker compose build nginx
docker compose up -d nginx

# after editing backend .py files
docker compose restart cortex

# after editing requirements.txt or the backend Dockerfile
docker compose build --no-cache cortex
docker compose up -d cortex

# stop everything
docker compose down

# stop and wipe the local database too
docker compose down -v
```

## Why the local setup differs from the server

`docker-compose.override.yml` is read automatically by Compose and applies
only on this machine. It does three things:

- builds nginx with `nginx/nginx.local.conf`, which serves plain HTTP on
  port 80. The production config listens on 443 and reads a Let's Encrypt
  certificate for deltaconvert.com; that certificate does not exist on a
  laptop, so nginx would refuse to start.
- lets nginx start without waiting for the backend health check, so the
  site is visible while TensorFlow finishes importing.
- publishes port 8000 and switches the API docs on.

**Do not upload `docker-compose.override.yml` to the server.** Production
reads `docker-compose.yml` alone and keeps HTTPS, the health gate and the
closed docs.

## If something misbehaves

**Port 80 already in use** — another web server or IIS holds it. Find it
with `netstat -ano | findstr :80`, or change the nginx port mapping in
`docker-compose.override.yml` to `"8080:80"` and use http://localhost:8080.

**Live rates unavailable, sample figures shown** — expected when nginx
runs alone with `--no-deps`. With the full stack up, it means nginx could
not reach the backend or the backend could not reach the ECB. Check
`docker compose logs cortex --tail 40`. A corporate network or VPN
blocking outbound HTTPS is the usual cause.

**Forecast reports "Model unavailable"** — the models folder is empty or
in the wrong place. Confirm with:

```powershell
docker exec dc_cortex ls /app/cortex/models | Measure-Object -Line
```

58 lines is the full set. Rebuild cortex after adding files, because
models are copied into the image at build time.

**Page looks stale after editing site files** — rebuild the nginx image;
the site is baked into it. `docker compose restart nginx` alone will not
pick up edits.

## Training models in the container

Models are copied into the backend image at build time, so anything
trained inside a running container is lost the next time that image is
rebuilt. Train, then copy the files out to the local folder:

```powershell
# a couple of minutes for two currencies, 45-90 for all 29
docker exec dc_cortex python -m cortex.app.engine.trainer --force

# keep them: copy out of the container into the local models folder
docker cp dc_cortex:/app/cortex/models/. D:\FinApp\DeltaConvert_Deployment\stochastix\cortex\models\
```

Reload the Exchange page afterwards. `GET /api/v1/currencies` picks the
new models up on the next request, so the forecast button switches on
for the trained pairs with no restart. A restart is only needed to warm
them into the model cache.
