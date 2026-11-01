# DeltaConvert — Developer Guide

DeltaConvert is a currency app: live ECB reference rates, a multi-day
model forecast, and demo pages (Markets, Portfolio, Alerts) that carry
sample data until those features are built for real. The frontend is now
the static multi-page site in `site/` (plain HTML, CSS and JS). The old
React app in `stochastix/interface/` is retired and should be deleted.

## Server Details
- **Server:** Hetzner CX43 (8 vCPU, 16GB RAM, 160GB SSD)
- **IP:** 204.168.221.119
- **Location:** Helsinki, Finland
- **OS:** Ubuntu 24.04
- **Domain:** deltaconvert.com (DNS on Namecheap)
- **SSL:** Let's Encrypt — the previously noted expiry (2026-06-30) has
  passed, so verify renewal before anything else (see "SSL certificate")
- **Cost:** €12.49/month

Note on access: deployment below uses the root account because that is how
the server is currently set up. A safer arrangement is a non-root user with
docker group membership and SSH key-only login. Worth doing before promoting
the site anywhere.

---

## Folder Structure

```
D:\DeltaConvert_Deployment\
├── docker-compose.yml
├── docker-compose.override.yml ← LOCAL ONLY (never upload this)
├── Dockerfile.nginx            ← builds the site image (minifies JS/CSS)
├── .env                        ← LOCAL ONLY (never upload this)
├── .env.example                ← template for a new .env
├── START-LOCAL.md              ← running the stack on Windows
│
├── site\                       ← static frontend (the live site)
│   ├── index.html  exchange.html
│   ├── markets.html  portfolio.html  alerts.html
│   ├── styles.css  app.js
│   ├── robots.txt  sitemap.xml
│   ├── palette.txt             ← design reference, not shipped
│   └── README.md               ← frontend notes and local run options
│
├── stochastix\
│   └── cortex\                 ← FastAPI backend
│       ├── Dockerfile          ← python:3.11-slim, uvicorn on 8000
│       ├── requirements.txt
│       ├── models\             ← 29 .keras + 29 .joblib files
│       └── app\
│           ├── main.py
│           ├── api\v1\endpoints.py
│           ├── core\           ← database.py, models.py
│           ├── engine\         ← trainer.py, fetcher.py, model.py, auditor.py
│           └── schemas\forecast.py
│
└── nginx\
    ├── nginx.conf              ← production, HTTPS on 443
    └── nginx.local.conf        ← local, plain HTTP on 80
```

`stochastix\interface\` (React) no longer exists in this tree. `.env`
keeps its existing secrets; `FLASK_SECRET_KEY` is no longer read by
anything and can be deleted. Optionally add `DOMAIN=deltaconvert.com`
(the compose file defaults to that value anyway).

---

## SOURCE VISIBILITY, IN PLAIN TERMS

Every website ships its frontend to the browser; there is no way to hide
HTML, CSS or JS from someone who wants to read it, on any stack. What the
build does:

- The Docker image minifies `app.js` and `styles.css` with esbuild, which
  makes them compact and tedious to read. That deters casual copying only.
- Everything of real value stays server-side and is never sent to the
  browser: the 29 trained models, the training code, the audit database,
  the admin token, and the prediction logic. The frontend only ever sees
  JSON answers.
- The ECB source needs no API key. If a paid rate provider is added later,
  its key lives in `.env` on the server and requests go through the
  backend, never from the browser.

---

## CONVERTER AND OLD-FRONTEND REMOVAL (one-off, on the server)

No folder rename, no volume migration. The compose project name is pinned
to `deltaconvert`, which matches what the old stack used, so the Postgres
data and certificates carry over untouched.

```bash
ssh root@204.168.221.119
cd /root/deltaconvert

# 1. Stop the stack
docker compose down

# 2. Delete the converter code — this is the actual removal
rm -rf deltaconvert/            # Flask app, transformer.py, templates, static assets

# 3. Delete the retired React frontend
rm -rf stochastix/interface/

# 4. Check for a stale forecast.py in the engine folder. The current code
#    imports nothing from it; if the file exists on the server, delete it.
ls stochastix/cortex/app/engine/
# rm stochastix/cortex/app/engine/forecast.py   (only if present)

# 5. Upload the new files (see DEPLOY section): docker-compose.yml,
#    Dockerfile.nginx, nginx.conf, the site/ folder and the API files.

# 6. Start the new stack
docker compose up --build -d
docker compose ps        # expect: dc_nginx, dc_cortex, dc_postgres, dc_certbot

# 7. Once healthy, remove the last traces
docker volume rm deltaconvert_dc_temp
docker image prune -af   # drops the old converter image among others
docker ps -a | grep dc_converter   # expect no output
```

The cron entry already references `dc_cortex` and needs no change.

---

## DATABASE MIGRATION (one-off)

The audit table gains a unique constraint on (currency_pair, target_date)
so concurrent requests cannot insert duplicate rows. `create_all` does not
alter existing tables, so apply it once by hand. Duplicates may already
exist from the race; remove them first:

```bash
docker exec -it dc_postgres psql -U $POSTGRES_USER -d $POSTGRES_DB
```

```sql
-- keep the earliest row of each duplicate group
DELETE FROM prediction_audits a
USING prediction_audits b
WHERE a.id > b.id
  AND a.currency_pair = b.currency_pair
  AND a.target_date = b.target_date;

ALTER TABLE prediction_audits
  ADD CONSTRAINT uq_audit_pair_target UNIQUE (currency_pair, target_date);
```

Fresh databases get the constraint automatically from the model definition.

---

## SSL CERTIFICATE

Verify state first:

```bash
docker exec dc_certbot certbot certificates
docker exec dc_certbot certbot renew --dry-run
```

If the certificate has lapsed:

```bash
docker compose stop nginx
docker run --rm -p 80:80 \
  -v deltaconvert_certbot_certs:/etc/letsencrypt \
  certbot/certbot renew
docker compose start nginx
```

The certbot container renews on a 12-hour loop after that.

---

## LOCAL TESTING (VS Code Terminal)

```powershell
cd D:\DeltaConvert_Deployment
docker compose up --build -d
docker compose ps
docker compose logs -f          # all containers
docker compose logs cortex      # just the API
docker compose down
```

Rebuild a single container after changes:

```powershell
# site/ or nginx.conf changed → rebuild nginx
docker compose build --no-cache nginx
docker compose up -d nginx

# API changes → rebuild cortex
docker compose build --no-cache cortex
docker compose up -d cortex
```

Quick restart when only .py files changed (Dockerfile and requirements
untouched):

```powershell
docker compose restart cortex
```

Test URLs locally:

```
http://localhost/                  ← landing page
http://localhost/exchange.html     ← live converter, rate chart, forecast
http://localhost/api/v1/rates/latest
http://localhost/api/v1/rates/history?base=GBP&quote=EUR&days=30
http://localhost/health
```

Two files apply on a laptop only and must never reach the server:
`docker-compose.override.yml` (HTTP-only nginx, relaxed health gate,
published port 8000) and `nginx/nginx.local.conf`. Full Windows
instructions are in `START-LOCAL.md`.

To run the frontend without Docker against a bare uvicorn backend, see
"Run locally" in `site/README.md` (one meta-tag change plus
`python3 -m http.server 5173`).

---

## RETRAIN CURRENCY MODELS

```powershell
Remove-Item D:\DeltaConvert_Deployment\stochastix\cortex\models\*.keras
Remove-Item D:\DeltaConvert_Deployment\stochastix\cortex\models\*.joblib

# Train all 29 currency pairs (takes 45-90 minutes)
docker exec dc_cortex python -m cortex.app.engine.trainer --force

# Copy trained models from container to local folder
docker cp dc_cortex:/app/cortex/models/. D:\DeltaConvert_Deployment\stochastix\cortex\models\

# Verify 29 models exist — both commands should return 29
(Get-ChildItem D:\DeltaConvert_Deployment\stochastix\cortex\models\*.keras).Count
(Get-ChildItem D:\DeltaConvert_Deployment\stochastix\cortex\models\*.joblib).Count
```

Note: requirements.txt pins `keras==3.15.0`. Models trained under a
different Keras major version should be retrained rather than reused.

---

## DEPLOY TO SERVER (Windows PowerShell)

```powershell
# Frontend — the whole static site in one go
scp -r D:\DeltaConvert_Deployment\site root@204.168.221.119:/root/deltaconvert/

# API files
scp D:\DeltaConvert_Deployment\stochastix\cortex\app\main.py root@204.168.221.119:/root/deltaconvert/stochastix/cortex/app/main.py
scp D:\DeltaConvert_Deployment\stochastix\cortex\app\api\v1\endpoints.py root@204.168.221.119:/root/deltaconvert/stochastix/cortex/app/api/v1/endpoints.py
scp D:\DeltaConvert_Deployment\stochastix\cortex\app\core\models.py root@204.168.221.119:/root/deltaconvert/stochastix/cortex/app/core/models.py
scp D:\DeltaConvert_Deployment\stochastix\cortex\app\engine\fetcher.py root@204.168.221.119:/root/deltaconvert/stochastix/cortex/app/engine/fetcher.py
scp D:\DeltaConvert_Deployment\stochastix\cortex\app\engine\model.py root@204.168.221.119:/root/deltaconvert/stochastix/cortex/app/engine/model.py
scp D:\DeltaConvert_Deployment\stochastix\cortex\app\engine\auditor.py root@204.168.221.119:/root/deltaconvert/stochastix/cortex/app/engine/auditor.py
scp D:\DeltaConvert_Deployment\stochastix\cortex\requirements.txt root@204.168.221.119:/root/deltaconvert/stochastix/cortex/requirements.txt

# Infrastructure — note that docker-compose.override.yml is deliberately absent
scp D:\DeltaConvert_Deployment\docker-compose.yml root@204.168.221.119:/root/deltaconvert/docker-compose.yml
scp D:\DeltaConvert_Deployment\Dockerfile.nginx root@204.168.221.119:/root/deltaconvert/Dockerfile.nginx
scp D:\DeltaConvert_Deployment\nginx\nginx.conf root@204.168.221.119:/root/deltaconvert/nginx/nginx.conf
scp D:\DeltaConvert_Deployment\stochastix\cortex\Dockerfile root@204.168.221.119:/root/deltaconvert/stochastix/cortex/Dockerfile
```

If the server already has a working `stochastix/cortex/Dockerfile`, keep
it and skip that last line. The version in this tree was reconstructed to
match the layout the code expects (`/app/cortex/models`, `PYTHONPATH=/app`,
uvicorn on `cortex.app.main:app`).

Model upload after retraining:

```powershell
cd D:\DeltaConvert_Deployment\stochastix\cortex
tar -czf models.tar.gz models
scp models.tar.gz root@204.168.221.119:/root/deltaconvert/stochastix/cortex/models.tar.gz
# then on the server: tar -xzf models.tar.gz && rm models.tar.gz
```

Rebuild on server after SSH:

```bash
cd /root/deltaconvert

# site/ or nginx.conf changed:
docker compose build --no-cache nginx && docker compose up -d nginx

# API code changed (no dependency changes):
docker compose restart cortex

# Dockerfile or requirements.txt changed:
docker compose build --no-cache cortex && docker compose up -d cortex

# Models updated:
docker compose restart cortex
```

Checks:

```bash
docker compose ps
docker compose logs cortex --tail 20
curl -s https://deltaconvert.com/health
curl -s https://deltaconvert.com/api/v1/rates/latest | head -c 300
curl -s "https://deltaconvert.com/api/v1/rates/history?base=GBP&quote=EUR&days=7" | head -c 300
```

---

## CONTAINER → SERVICE MAP

| Container | Service | Role |
|---|---|---|
| dc_nginx | nginx | Reverse proxy + static site (80/443) |
| dc_cortex | cortex | FastAPI rates + forecast API (8000) |
| dc_postgres | db | PostgreSQL prediction audit database |
| dc_certbot | certbot | SSL certificate renewal loop |

---

## DAILY AUDIT CRON JOB

Runs daily at 18:00 UTC to resolve stored predictions against actual ECB
reference rates. ECB publishes around 16:00 CET, so 18:00 UTC has headroom
in winter; in summer publication lands at 14:00 UTC, which leaves even
more. If audits ever show "rate unavailable", the publication slipped that
day — re-run manually or shift the cron later.

```bash
crontab -l    # entry references dc_cortex and is unchanged

# Manual resolve
ADMIN_KEY=$(grep ADMIN_SECRET /root/deltaconvert/.env | cut -d= -f2)
docker exec dc_cortex python -c "
import urllib.request
req = urllib.request.Request('http://localhost:8000/api/v1/audit/resolve', method='POST')
req.add_header('x-admin-token', '$ADMIN_KEY')
resp = urllib.request.urlopen(req)
print(resp.read().decode())
"
```

---

## USEFUL SERVER COMMANDS

```bash
free -h                      # memory
df -h                        # disk
docker stats --no-stream     # per-container usage
docker system prune -af      # clean old images
apt update && apt upgrade -y # Ubuntu security updates
```

---

## SECURITY REMINDERS

- **NEVER** upload `.env` to version control or share it; secrets live on
  the server only. `FLASK_SECRET_KEY` can be deleted — nothing reads it.
- PostgreSQL sits on an internal Docker network and is unreachable from
  outside.
- nginx reaches the backend through a variable with Docker's embedded
  resolver, so the web server starts even when the backend container is
  down and returns 502 per request instead. With a literal hostname
  nginx resolves at startup and refuses to start at all.
- nginx rate limits: 10r/s on /api, 30r/s general. The backend has its own
  per-IP limiter that reads the `X-Real-IP` header set by nginx. The
  backend limiter is in-memory and per-worker, so treat nginx as the real
  limit.
- The API's /predict endpoint is public and CPU-bound. The response cache
  blunts repeat queries, but a burst of distinct pairs at 90-day horizons
  is still expensive. If load becomes a problem, cap the horizon further
  or put the endpoint behind a token.
- The frontend holds no secrets: no keys, no tokens, and localStorage
  carries only demo preferences.
- Rotate the server root password and move to key-only SSH before any
  public promotion. This file previously circulated with the IP and root
  login pattern in it; treat the current credentials as semi-public.
