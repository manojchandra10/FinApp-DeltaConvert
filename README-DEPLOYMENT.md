# DeltaConvert — Developer Guide

DeltaConvert is a currency app: live ECB reference rates, a multi-day
model forecast, and demo pages (Markets, Portfolio, Alerts) that carry
sample data until those features are built for real. The frontend is now
the static multi-page site in `site/` (plain HTML, CSS and JS). The old
React app in `stochastix/interface/` is retired and should be deleted.

## Server Details

The previous server has been deleted. Server addresses, logins and hosting
details are not recorded in this repository: a public address next to a
root login pattern invites password guessing. The commands below use two
shell variables, set once per session on your own machine:

```bash
SERVER=deploy@your.server.address     # the deploy user, never root
REMOTE_DIR=/srv/deltaconvert           # where the project lives on the server
```

In PowerShell: `$SERVER = "deploy@your.server.address"` and
`$REMOTE_DIR = "/srv/deltaconvert"`.

- **OS:** Ubuntu 24.04 LTS (or newer)
- **Domain:** deltaconvert.com
- **SSL:** Let's Encrypt, renewed by the certbot container and picked up by
  nginx automatically (see "SSL certificate")

Set up a new server with the steps in "SERVER HARDENING" before anything is
deployed to it.

---

## SECURITY RELEASE (read before the next deployment)

This release fixes the issues listed in SECURITY-REPORT.md. Four steps are
needed when the stack is next deployed:

1. **Write `.env` with strong secrets.** Compose now refuses to start
   without `POSTGRES_PASSWORD`, and the audit endpoint stays locked unless
   `ADMIN_SECRET` has 32 or more random characters. Generate each value
   with `openssl rand -hex 32` (see `.env.example`). Never reuse the
   values from a laptop.
2. **Rebuild both images without cache**, because dependencies, both
   Dockerfiles and the nginx configuration changed:
   `docker compose build --no-cache && docker compose up -d`
3. **Install the new cron command** from "DAILY AUDIT CRON JOB". The old
   one passed the token on the host's command line.
4. **Harden the server first** ("SERVER HARDENING"). Earlier copies of
   this guide published the old server's address and a root login.

---

## Folder Structure

```
D:\DeltaConvert_Deployment\
├── docker-compose.yml
├── compose.local.yml           ← LOCAL ONLY overlay (used by dev.ps1)
├── dev.ps1                     ← runs the local stack; writes a local .env
├── Dockerfile.nginx            ← builds the site image (minifies JS/CSS)
├── .dockerignore               ← keeps .env and everything but site/ and nginx/ out of the nginx build
├── .env                        ← secrets for one machine; never upload or commit
├── .env.example                ← template for a new .env (no secrets in it)
├── START-LOCAL.md              ← running the stack on Windows
├── SECURITY-REPORT.md          ← security review: findings, fixes, evidence
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
│       ├── Dockerfile          ← python:3.11-slim, non-root user, uvicorn on 8000
│       ├── .dockerignore       ← keeps secrets, tests and archives out of the image
│       ├── requirements.txt
│       ├── models\             ← 29 .keras + 29 .joblib files
│       ├── tests\              ← security regression tests (not in the image)
│       └── app\
│           ├── main.py
│           ├── resolve_audits.py ← daily audit command for cron
│           ├── api\v1\endpoints.py
│           ├── core\           ← database.py, models.py, security.py
│           ├── engine\         ← trainer.py, fetcher.py, model.py, auditor.py, artifacts.py
│           └── schemas\forecast.py
│
└── nginx\
    ├── nginx.conf              ← production, HTTPS on 443
    ├── nginx.local.conf        ← local, plain HTTP on 80
    └── reload-certs.sh         ← reloads nginx every 6 h so renewed certificates load
```

`stochastix\interface\` (React) no longer exists in this tree. On a new
server, write `.env` from `.env.example` with freshly generated secrets
(see "SECURITY RELEASE"). `FLASK_SECRET_KEY` is no longer read by anything
and does not belong in it. `DOMAIN=deltaconvert.com` is optional (the
compose file defaults to that value anyway).

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
ssh $SERVER
cd $REMOTE_DIR

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

Then install the cron entry from "DAILY AUDIT CRON JOB"; the command
changed in this release.

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
  certbot/certbot:v5.8.0 renew
docker compose start nginx
```

The certbot container renews on a 12-hour loop after that. nginx reads
certificates only when it starts or reloads, so the nginx image reloads
itself every 6 hours (`nginx/reload-certs.sh`); a renewed certificate is
in use within 6 hours without any manual step. To load one at once:

```bash
docker exec dc_nginx nginx -s reload
```

---

## LOCAL TESTING (VS Code Terminal)

`dev.ps1` runs Compose with the local overlay (`compose.local.yml`). On
its first run it writes a `.env` with random local secrets.

```powershell
cd D:\DeltaConvert_Deployment
.\dev.ps1 up --build -d
.\dev.ps1 ps
.\dev.ps1 logs -f               # all containers
.\dev.ps1 logs cortex           # just the API
.\dev.ps1 down
```

Rebuild a single container after changes:

```powershell
# site/ or nginx.local.conf changed → rebuild nginx
.\dev.ps1 build --no-cache nginx
.\dev.ps1 up -d nginx

# API changes → rebuild cortex
.\dev.ps1 build --no-cache cortex
.\dev.ps1 up -d cortex
```

Quick restart when only .py files changed (Dockerfile and requirements
untouched):

```powershell
.\dev.ps1 restart cortex
```

Test URLs locally:

```
http://localhost/                  ← landing page
http://localhost/exchange.html     ← live converter, rate chart, forecast
http://localhost/api/v1/rates/latest
http://localhost/api/v1/rates/history?base=GBP&quote=EUR&days=30
http://localhost/health
```

The local overlay applies on a laptop only: `compose.local.yml`
(HTTP-only nginx, relaxed health gate, API docs on, port 8000) used with
`nginx/nginx.local.conf`. It publishes every port on 127.0.0.1, so the
stack is not reachable from other machines on the same network. It is
inert unless named explicitly, and the server runs plain
`docker compose`. Full Windows instructions are in `START-LOCAL.md`.

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

Set `$SERVER` and `$REMOTE_DIR` first (see "Server Details"). Files go to
the deploy user's project folder; nothing is copied as root.

```powershell
# Frontend — the whole static site in one go
scp -r D:\DeltaConvert_Deployment\site "${SERVER}:${REMOTE_DIR}/"

# Backend — the app package, requirements, Dockerfile and .dockerignore
scp -r D:\DeltaConvert_Deployment\stochastix\cortex\app "${SERVER}:${REMOTE_DIR}/stochastix/cortex/"
scp D:\DeltaConvert_Deployment\stochastix\cortex\requirements.txt D:\DeltaConvert_Deployment\stochastix\cortex\Dockerfile D:\DeltaConvert_Deployment\stochastix\cortex\.dockerignore "${SERVER}:${REMOTE_DIR}/stochastix/cortex/"

# Infrastructure. compose.local.yml, dev.ps1 and .env are deliberately
# absent: the server gets its own .env, written there by hand.
scp D:\DeltaConvert_Deployment\docker-compose.yml D:\DeltaConvert_Deployment\Dockerfile.nginx D:\DeltaConvert_Deployment\.dockerignore "${SERVER}:${REMOTE_DIR}/"
scp D:\DeltaConvert_Deployment\nginx\nginx.conf D:\DeltaConvert_Deployment\nginx\reload-certs.sh "${SERVER}:${REMOTE_DIR}/nginx/"
```

On the server, protect the secrets file once: `chmod 600 $REMOTE_DIR/.env`.

Model upload after retraining:

```powershell
cd D:\DeltaConvert_Deployment\stochastix\cortex
tar -czf models.tar.gz models
scp models.tar.gz "${SERVER}:${REMOTE_DIR}/stochastix/cortex/models.tar.gz"
Remove-Item models.tar.gz
# then on the server, in $REMOTE_DIR/stochastix/cortex:
#   tar -xzf models.tar.gz --no-same-owner && rm models.tar.gz
```

The backend loads model and scaler files without executing anything in
them (`engine/artifacts.py`). If a file is refused, `docker compose logs
cortex` names it, and retraining that currency replaces it.

Rebuild on server after SSH. Code and models are copied into the backend
image at build time, so a plain restart keeps running the old image: every
backend change needs a build.

```bash
cd $REMOTE_DIR

# site/ or nginx files changed:
docker compose build --no-cache nginx && docker compose up -d nginx

# API code or models changed (no dependency changes); the dependency
# layer comes from cache, so this is quick:
docker compose up -d --build cortex

# Dockerfile or requirements.txt changed:
docker compose build --no-cache cortex && docker compose up -d cortex
```

Checks:

```bash
docker compose ps
docker compose logs cortex --tail 20
curl -s https://deltaconvert.com/health
curl -s https://deltaconvert.com/api/v1/rates/latest | head -c 300
curl -s "https://deltaconvert.com/api/v1/rates/history?base=GBP&quote=EUR&days=7" | head -c 300
curl -sI https://deltaconvert.com/app.js | grep -i -E "content-security-policy|strict-transport-security"
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

The command runs inside the backend container and reads the token from
that container's own environment, so the token never appears on the
host's command line, in `ps` output or in shell history. The endpoint
accepts calls from inside the container only, and nginx answers 404 for
it.

```bash
crontab -e    # as the deploy user, then add this line:
0 18 * * * docker exec dc_cortex python -m cortex.app.resolve_audits >> $HOME/deltaconvert-audit.log 2>&1

# Manual resolve
docker exec dc_cortex python -m cortex.app.resolve_audits
```

A 403 means `ADMIN_SECRET` in `.env` is missing, shorter than 32
characters or a template value. The API logs which at start-up.

---

## SERVER HARDENING (new server, before the first deployment)

Run as root on the first login only. Install Docker Engine from Docker's
own apt repository first.

```bash
# 1. A deploy user with your SSH key, which runs Docker without root.
adduser --disabled-password --gecos "" deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
install -m 600 -o deploy -g deploy /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
usermod -aG docker deploy
install -d -o deploy -g deploy /srv/deltaconvert

# 2. Key-only SSH and no root login. Open a second session as deploy and
#    check it works before closing this one.
cat > /etc/ssh/sshd_config.d/10-hardening.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
sshd -t && systemctl restart ssh

# 3. Firewall: SSH, HTTP and HTTPS only.
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# 4. Automatic security updates and SSH brute-force protection.
apt update && apt install -y unattended-upgrades fail2ban
dpkg-reconfigure -f noninteractive unattended-upgrades
systemctl enable --now fail2ban
```

Notes:

- Docker inserts its own firewall rules for published ports, ahead of
  ufw's. Only nginx publishes ports (80 and 443). Keep it that way and
  never publish 5432 or 8000 on the server.
- Membership of the `docker` group is equivalent to root on the host.
  Give it to the deploy user only and keep that user's SSH key safe.
- If the hosting provider offers a network firewall, open only 22, 80
  and 443 there as well.
- If the server has an IPv6 address, check the nginx access log once
  (`docker compose logs nginx`): IPv6 visitors should appear with their
  own addresses. If they all appear as one Docker gateway address (such
  as 172.18.0.1), Docker is forwarding IPv6 through its userland proxy,
  and all IPv6 visitors share one rate limit.

---

## OPTIONAL: LEAST-PRIVILEGE DATABASE ROLE

The API connects as the Postgres superuser that the image creates from
`POSTGRES_USER`. No SQL injection was found (every query goes through the
SQLAlchemy ORM with bound parameters), but a role limited to the audit
table narrows what any future bug could reach. With the stack running
once (so the table exists):

```bash
docker exec -it dc_postgres psql -U $POSTGRES_USER -d $POSTGRES_DB
```

```sql
CREATE ROLE cortex_app LOGIN PASSWORD 'paste a new value from openssl rand -hex 32';
GRANT CONNECT ON DATABASE deltaconvert TO cortex_app;
GRANT USAGE ON SCHEMA public TO cortex_app;
GRANT SELECT, INSERT, UPDATE ON prediction_audits TO cortex_app;
GRANT USAGE, SELECT ON SEQUENCE prediction_audits_id_seq TO cortex_app;
```

Then add `APP_DB_PASSWORD` to `.env` and change the cortex `DATABASE_URL`
in `docker-compose.yml` to `postgresql://cortex_app:${APP_DB_PASSWORD}@db:5432/...`.

---

## USEFUL SERVER COMMANDS

```bash
free -h                      # memory
df -h                        # disk
docker stats --no-stream     # per-container usage
docker system prune -af      # clean old images
sudo apt update && sudo apt upgrade -y   # Ubuntu security updates
pip-audit -r stochastix/cortex/requirements.txt   # on any machine with pip-audit, before changing pins
```

---

## SECURITY REMINDERS

- **NEVER** upload `.env` to version control or share it; secrets live on
  the server only, in a file only the deploy user can read.
- PostgreSQL sits on an internal Docker network and is unreachable from
  outside.
- nginx reaches the backend through a variable with Docker's embedded
  resolver, so the web server starts even when the backend container is
  down and returns 502 per request instead. With a literal hostname
  nginx resolves at startup and refuses to start at all.
- nginx limits: 10 r/s on /api (burst 20), 30 r/s elsewhere, 100
  connections per address, 16 KB request bodies; excess requests get 429.
  The backend also accepts at most 30 API calls per client per minute. It believes
  the `X-Real-IP` header only from a proxy address (`TRUSTED_PROXY_CIDRS`,
  by default loopback and private networks, which covers nginx on the
  Docker network), and counts IPv6 clients per /64.
- Forecasts: each currency's forecast is computed once per ECB data
  snapshot (at most 90 model steps) and shared by every pair and horizon.
  At most 8 requests do model work at once; the rest get 503 with
  Retry-After, so forecast traffic cannot stall the other endpoints.
- Model and scaler files are never unpickled or deserialised as code
  (`engine/artifacts.py`).
- The audit-resolve endpoint needs a caller on loopback, a 32-character
  secret and a matching token, and nginx hides it.
- Every response carries a Content-Security-Policy and the other security
  headers, scripts and styles included. If the site gains a new external
  resource (fonts, analytics, a CDN), the policy in both nginx
  configurations must list it or browsers will block it.
- API docs and the OpenAPI schema are served only when `ENVIRONMENT` is
  development, dev or local.
- The frontend holds no secrets: no keys, no tokens, and localStorage
  carries only demo preferences.
