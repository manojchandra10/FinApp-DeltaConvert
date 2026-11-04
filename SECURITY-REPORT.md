# DeltaConvert security review

**Date:** 4 November 2026
**Repository:** manojchandra10/FinApp-DeltaConvert, branch
`claude/eager-feynman-qamfxq`, starting from commit `cadda28`
**Scope:** everything in the repository: the FastAPI backend
(`stochastix/cortex`), the static site (`site/`), both nginx
configurations, both Dockerfiles, the Compose files, `dev.ps1`, the
environment template, the ignore files and the guides.

## Summary

The code on GitHub still contained every issue listed in the earlier
report of 22 September 2026. None of that report's fixes had reached the
repository: there was no `engine/artifacts.py`, no `core/security.py`, no
tests and no `.dockerignore`, and the images were still nginx 1.27,
untagged certbot and Node 20. Each issue was therefore reproduced again on
this code, fixed here, and tested again.

27 issues in total: the 25 from the earlier report (2 high, 8 medium,
12 low, 3 informational), all of which reproduced, and 2 new low ones
(L-13 and L-14). 26 are fixed in this branch. I-03, the backend limit of 30
API calls per minute, is a tuning decision and is left as it was.

The two high findings:

- **H-01.** Scaler files were loaded with `joblib.load`, which is pickle. A
  tampered scaler file in the models folder ran a shell command inside the
  backend, which ran as root.
- **H-02.** One client could keep the forecast model busy and stall the API.
  With 60 visitors asking for forecasts, the original backend answered 13;
  `/health` stopped answering and Docker marked the container unhealthy.
  After the fix all 60 were answered within 18 seconds.

No SQL injection was found: every query goes through the SQLAlchemy ORM
with bound parameters. No secrets were found in the code or in the Git
history. The old server's address is still in the history (commit
`cadda28`); that server has been deleted, so it no longer points at
anything of yours.

**Required at the next deployment** (step by step in README-DEPLOYMENT.md,
"SECURITY RELEASE"):

1. Write `.env` with a random `POSTGRES_PASSWORD` and a random
   `ADMIN_SECRET` of 32 or more characters (`openssl rand -hex 32`).
2. Build both images with `--no-cache`.
3. Install the new cron command.
4. Carry out "SERVER HARDENING" on the new server before deploying.

## Method

- Every issue was first reproduced against the unmodified code, then
  fixed, then the same check was run again.
- Real images were built from both versions and run with Docker: nginx
  with the production configuration and a test certificate, the backend,
  Postgres, and a deterministic stand-in for the ECB API, which is not
  reachable from the test machine. The stand-in answers under the ECB's
  host name inside the Docker network, so the fetcher code ran unchanged.
- Chromium drove all five pages of both versions, recorded CSP violations
  and console errors, and took screenshots with a fixed random seed for a
  pixel comparison.
- Equivalence: 15 API responses (7 forecasts, 5 histories, currencies,
  scoreboard, latest rates) were compared byte for byte between the
  original and the patched code.
- pip-audit (PyPI advisory data) on both dependency sets, the npm advisory
  service for esbuild, bandit on the Python code, `nginx -t` on nginx 1.30,
  `docker compose config` for the production and local setups, and a run of
  `dev.ps1` in PowerShell 7.
- A regression suite of 57 tests, added at `stochastix/cortex/tests`. It
  passes on the upgraded dependencies and on the original ones.

**Limits of the testing:**

- The ECB API was replaced by generated data with the same CSV layout.
- Docker Hub rate-limited this machine, so the official images came from
  Google's Docker Hub mirror (`mirror.gcr.io`). Debian and Alpine package
  mirrors were blocked, so the test builds used a base image with
  `libgomp1` copied in and `apt-get` replaced by a no-op. That step of the
  backend Dockerfile is unchanged from the original.
- `dev.ps1` ran in PowerShell 7 on Linux. Windows PowerShell 5.1 was not
  available; the script uses only commands that exist in 5.1.
- TensorFlow 2.21 was compared with 2.16.1 on the two models in the
  repository (GBP and CHF). The other 27 models were not available.
- The test machine has 4 CPU cores. Timings on a server will differ.
- IPv6 could not be tested here (see the note in SERVER HARDENING).

## Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| H-01 | High | Tampered scaler file runs code when loaded (pickle) | Fixed |
| H-02 | High | One client can stall the forecast engine and the whole API | Fixed |
| M-01 | Medium | Backend rate limiter bypassable; its memory grows without bound | Fixed |
| M-02 | Medium | Dependencies with published vulnerabilities | Fixed |
| M-03 | Medium | Admin endpoint public, weak secrets accepted, token on the command line | Fixed |
| M-04 | Medium | Security headers incomplete; none at all on JS and CSS | Fixed |
| M-05 | Medium | Production database password defaults to a published value | Fixed |
| M-06 | Medium | Backend container runs as root; no `.dockerignore` | Fixed |
| M-07 | Medium | Server address and root SSH login published in the guides | Fixed |
| M-08 | Medium | Renewed TLS certificates never loaded by nginx | Fixed |
| L-01 | Low | DOM XSS through the currency list from the API | Fixed |
| L-02 | Low | Stored DOM XSS through alert ids in localStorage | Fixed |
| L-03 | Low | CSV formula injection in the portfolio export | Fixed |
| L-04 | Low | Permissive CORS | Fixed |
| L-05 | Low | API schema served in production; docs on by default | Fixed |
| L-06 | Low | nginx accepts any host name and has no request limits | Fixed |
| L-07 | Low | TLS admits CBC ciphers and session tickets | Fixed |
| L-08 | Low | ECB fetcher: unchecked URL parts, redirects anywhere, no size or time cap | Fixed |
| L-09 | Low | Outdated or floating images and build tools | Fixed |
| L-10 | Low | No log rotation | Fixed |
| L-11 | Low | Local stack reachable from the local network | Fixed |
| L-12 | Low | Working-looking secrets in the template; gaps in ignore rules | Fixed |
| L-13 | Low | Every container received every secret in `.env` (new) | Fixed |
| L-14 | Low | Guides said a restart applies backend changes; it does not (new) | Fixed |
| I-01 | Info | Validation errors echo the submitted value | Fixed |
| I-02 | Info | Stored category names used as plain object keys | Fixed |
| I-03 | Info | Backend limit of 30 API calls per minute is low for real use | Unchanged |

## Details

### H-01 — Tampered scaler file runs code when loaded

`_load_model` called `joblib.load` on `EUR_XXX_scaler.joblib`. joblib's
format is pickle, and loading a pickle can call any Python function. Model
files move by hand (scp, tar archives, copies between folders), and the
container ran as root.

**Fix.** `engine/artifacts.py` reads the scaler format with its own
unpickler. It resolves four names (the MinMaxScaler class, joblib's array
wrapper, `numpy.ndarray` and `numpy.dtype`) and refuses everything else.
It also refuses object arrays, which joblib reads with the unrestricted
pickle module, compressed and legacy files, files over 1 MB, and any
attempt to set state on a class (only instances may receive state). The
fitted values are checked before use. The `.keras` file is no longer deserialised at
all: the API builds the architecture from `model.py` and loads only the
weights, so `config.json`, the part of a Keras archive that names classes
and functions, is never read. Archives with unexpected members are
refused. The file formats and the trainer are unchanged.

**Evidence.** A scaler carrying `os.system` and a second one hiding the
call inside an object array both ran their command on the original code
(the marker file was written, and the load reported success). On the
patched code: "Refusing to load posix.system from a scaler file" and
"Refusing dtype 'O8' in a scaler file"; nothing ran. The two shipped
scalers load to exactly what `joblib.load` returns (attributes, dtypes and
transform results). A `.keras` file whose `config.json` was replaced by
garbage still loads its weights; the original loader failed on it with a
JSON error. Weights and 10-step outputs are identical to the original
loading path for both models.

### H-02 — One client can stall the forecast engine and the whole API

Every uncached forecast ran the model once per day of the horizon for each
currency, inside a process-wide lock. The response cache was keyed on
(from, to, days), so there were over 78,000 distinct uncached requests.
Requests waiting on the lock filled FastAPI's pool of 40 threads, and then
`/rates/latest`, `/currencies` and `/health` stopped answering as well.

**Fix.** Each currency's forecast is computed once per ECB data snapshot
and extended to the longest horizon asked for so far, so the model runs at
most 90 steps per currency per snapshot, whatever mix of pairs and
horizons arrives. The values are the same as before, because each step
depends only on the previous one. At most 8 requests do model work at a
time; any further request gets 503 with `Retry-After` at once, so forecast
traffic can never take the whole thread pool. The response cache now has a
lock (its eviction could raise KeyError, a 500, under concurrent requests).

**Evidence.**

- Eight GBP-to-CHF requests with horizons 30, 45, 60, 75, 90, 89, 88 and
  87: 1,128 model calls in 114 seconds before; 180 calls in 18.5 seconds
  after.
- 60 forecasts from 60 different visitors, sent in 9 seconds to a cold
  backend. Before: 13 answered, 47 still waiting at the 180-second client
  limit; `/health` and `/rates/latest` timed out at 60 seconds; Docker's
  health check failed 5 times in a row. After: all 60 answered within
  18.1 seconds (48 forecasts and 12 immediate "busy, try again" answers
  while the first computation ran); the cheap endpoints answered every
  time, slowest 2.9 seconds; the health check never failed.
- 7 forecast responses are byte-identical to the original code on the same
  dependencies.

### M-01 — Backend rate limiter bypassable, memory unbounded

The limiter believed `X-Real-IP` from any caller, and it checked
`request.url.path`, which Starlette rebuilds from the Host header
(CVE-2026-48710). A request with `Host: deltaconvert.com?x` has an empty
path there and was never counted, and this worked through the production
nginx. Every identity stayed in memory for the life of the process.

**Fix.** The limiter reads the routed path (`scope["path"]`). `X-Real-IP`
is believed only from a proxy address (`TRUSTED_PROXY_CIDRS`, by default
loopback and private networks, which covers nginx on the Docker network)
and only when it is a literal IP address. IPv6 clients are counted per
/64. Idle clients are swept once per window and the table holds at most
20,000 entries. nginx now refuses such Host headers as well (L-06).

**Evidence.** 40 requests through the production nginx with the crafted
Host: 0 limited before; after, nginx refuses them (400), and the backend
on its own limits 10 of 40. 40 requests with rotating `X-Real-IP` from an
untrusted address: 0 limited before, 10 after. 50,000 distinct callers:
50,000 entries kept before, 20,000 after.

### M-02 — Dependencies with published vulnerabilities

pip-audit found 23 entries in 4 packages: Starlette 0.41.3 (7 advisories,
including CVE-2026-48710 and CVE-2026-54282, which concern the request
URL this API used), requests 2.32.3 (CVE-2024-47081 and CVE-2026-25645),
protobuf 4.25.9 (CVE-2026-0994), and setuptools 79.0.1. The backend image
also shipped pip 24.0 and setuptools 79.0.1 from the base image.
scikit-learn was an open range that installed 1.9.1, while the scalers
were written by 1.9.0.

**Fix.** FastAPI 0.141.1 (the last release without a new OpenTelemetry
dependency) with Starlette 1.6.0 pinned directly, uvicorn 0.54.0, h11
0.16.0, TensorFlow 2.21.0 with protobuf 6.33.6, requests 2.34.2, urllib3
2.8.0, psycopg2-binary 2.9.13 and scikit-learn exactly 1.9.0. The image
upgrades pip to 26.2.2 and setuptools to 84.2.1.

**Evidence.** pip-audit on the full installed set: no known
vulnerabilities. TensorFlow 2.21 against 2.16.1 over 90 autoregressive
steps: largest difference 6e-8 (GBP) and 1.2e-7 (CHF), which is float32
rounding. Through the whole API, 13 of 15 responses are byte-identical;
in the 90-day GBP-to-CHF forecast, 2 of 300 displayed values moved by
0.0001 (the last displayed digit) where a value sits on a rounding
boundary. The code changes alone gave 15 of 15 identical responses.

### M-03 — Admin endpoint weaknesses

`POST /api/v1/audit/resolve` was reachable from the internet through
nginx. Any `ADMIN_SECRET` was accepted, including the template value that
START-LOCAL.md told readers to copy. The documented command put the token
on the host's command line. A non-ASCII token made `hmac.compare_digest`
raise TypeError (a 500), and the route was listed in the OpenAPI schema.

**Fix.** Three independent checks: the caller must be on loopback (the
cron job runs inside the container; `ADMIN_CALLER_CIDRS` overrides this),
the secret must have 32 or more characters and no template wording, and
the token comparison runs in constant time on SHA-256 digests without an
exception for any input. nginx answers 404 for the path. A new command,
`python -m cortex.app.resolve_audits`, reads the token from the
container's own environment. A weak secret is reported at start-up, and
the route is hidden from the schema.

**Evidence.** Template token from a non-loopback caller: 200 before, 403
after. Through nginx: reached the backend (200) before; 404 after, for
four spellings of the path. Non-ASCII token: 500 before, 403 after. The
new cron command against the running stack: 200.

### M-04 — Security headers incomplete

`location ~* \.(css|js)$` had its own `add_header`, which in nginx drops
every header inherited from the server block, so `app.js` and
`styles.css` had none. No response had a Content-Security-Policy or a
Permissions-Policy, and the Server header gave the nginx version.

**Fix.** All headers sit at server level and no location uses
`add_header`; Cache-Control comes from a `map`. A Content-Security-Policy
matched to the site: scripts, styles and API calls from the site's own
origin only, no plugins or frames, and inline style attributes permitted
because the pages use them. Also Permissions-Policy,
Cross-Origin-Opener-Policy, Cross-Origin-Resource-Policy and
`server_tokens off`. The local configuration has the same headers apart
from HSTS.

**Evidence.** `app.js` and `styles.css`: 0 of 6 checked headers before,
6 of 6 after; HTML and API answers: 4 of 6 before, 6 of 6 after, 404
pages included. Chromium recorded 0 CSP violations and 0 console errors
across all five pages. The Server header now reads "nginx".

### M-05 — Database password defaulted to a published value

`${POSTGRES_PASSWORD:-localdev}` meant a server whose `.env` lacked the
variable started Postgres with a password printed in the repository.

**Fix.** `${POSTGRES_PASSWORD:?...}`: Compose stops with a clear message.
`dev.ps1` writes a local `.env` with random secrets on its first run. For
a local database volume that already exists from the old defaults it
keeps "localdev", so local data still opens.

**Evidence.** `docker compose config` with no `.env`: rendered "localdev"
before; after, "required variable POSTGRES_PASSWORD is missing a value".
`dev.ps1` in PowerShell 7: a 48-character hex password and a 64-character
hex admin secret on first run; "localdev" when the old volume exists; an
existing `.env` left untouched.

### M-06 — Backend container ran as root

The Dockerfile had no `USER`, so the API, and any code injected through
H-01, ran as root and could rewrite the application. With no
`.dockerignore`, `COPY . /app/cortex/` copied anything in the backend
folder into the image (the Dockerfile itself was in it), and the nginx
build sent the whole project to the Docker daemon.

**Fix.** A dedicated user (uid 10001). Application code is owned by root
and read-only to that user; only `models/` is writable, so the training
command still works. Compose drops every Linux capability for the backend
and sets `no-new-privileges` on all services. Two `.dockerignore` files:
the nginx build sees only `site/` and `nginx/`, and the backend build
leaves out `.env` files, keys, tests, caches and archives.

**Evidence.** The original image runs as uid 0. The patched one runs as
uid 10001 with no capabilities (`CapEff` 0) and `NoNewPrivs` set;
writing to the application code fails and writing to `models/` works.
With a decoy `.env`, a `.env` variant and an archive planted in the build
folders, none of them reached either image.

### M-07 — Server address and root SSH login published in the guides

The previous server's public IP appeared 16 times, mostly as `ssh root@`
and `scp root@`, next to hosting details.

**Fix.** Host details replaced by `$SERVER` and `$REMOTE_DIR`, with a
deploy user. A new "SERVER HARDENING" section covers the deploy user,
key-only SSH without root, a firewall, automatic security updates and
fail2ban.

**Evidence.** 16 occurrences before, none after. The address remains in
the old commit; see "Not changed" below.

### M-08 — Renewed TLS certificates never loaded

certbot renewed certificates every 12 hours, but nginx reads certificate
files only when it starts or reloads, and nothing reloaded it.

**Fix.** A hook in the nginx image (`nginx/reload-certs.sh`) reloads nginx
every 6 hours. certbot is pinned to v5.8.0.

**Evidence.** The certificate files were replaced while the stack ran.
The original kept serving the old certificate. The patched image, with a
20-second interval for the test, served the new one after 14 seconds.

### L-01 — DOM XSS through the currency list

Codes from `/api/v1/currencies` went into `innerHTML` unescaped. **Fix:**
codes must be three capital letters, and they are escaped. **Evidence:**
an injected payload ran in Chromium before and not after.

### L-02 — Stored DOM XSS through alert ids

Alert ids were the one unescaped field in the rule list. **Fix:** escaped
like the other fields, and stored data of the wrong shape falls back to
the defaults. **Evidence:** the payload ran before and not after. Before,
the affected rule also could not be deleted; after, it can.

### L-03 — CSV formula injection

Holding names and categories starting with `=`, `+`, `-` or `@` were
exported as they were, so a spreadsheet would evaluate them. **Fix:** text
cells starting with those characters, a tab or a carriage return get a
leading apostrophe; numbers are written unchanged. **Evidence:** the
exported cell changed from `=HYPERLINK(...)` to `'=HYPERLINK(...)`.

### L-04 — Permissive CORS

Credentialed requests were permitted, any request header was accepted,
and `http://localhost` was a production origin. **Fix:** no credentials,
only `Accept` and `Content-Type`, exact origins only (wildcards, paths and
user names are refused with a warning), and production origins limited to
the two HTTPS addresses. **Evidence:** a preflight asking for
`x-admin-token` got 200 with credentials before and 400 after.

### L-05 — API schema and docs exposure

Docs were hidden only when `ENVIRONMENT` was exactly "production", and
`/openapi.json` was served even then. **Fix:** docs, ReDoc and the schema
appear only when `ENVIRONMENT` is development, dev or local. **Evidence:**
`/openapi.json` in production returned 200, listing the admin route,
before; 404 after.

### L-06 — nginx host and request handling

Any Host header was accepted, and the HTTP redirect echoed it
(`Host: evil.example` gave `Location: https://evil.example/...`). Unknown
TLS names were served the site. There was no connection limit, bodies up
to 1 MB were accepted, regex locations could capture `/api/` paths, and
dotfiles were not blocked. **Fix:** default servers close unknown HTTP
hosts (444), refuse TLS handshakes for unknown names, and close a request
whose Host header differs from its TLS name; 16 KB body limit, 15-second
header and body timeouts, 100 connections per address, 429 on limits,
`^~ /api/`, dotfiles 404. **Evidence:** each case was redirected or served
before and is closed or refused after; a 20 KB body now gets 413;
`/api/v1/x.js` now reaches the API. ACME challenges and the normal
redirect still work.

### L-07 — TLS configuration

The default cipher list admitted CBC-mode suites, and session tickets were
on with a key that is never rotated. **Fix:** ECDHE with AES-GCM or
ChaCha20 only (Mozilla's intermediate list without the DHE suites);
session tickets off. **Evidence:** ECDHE-ECDSA-AES128-SHA was accepted and
a session ticket issued before; the suite is refused and no ticket is
issued after.

### L-08 — ECB fetcher

Currency codes and dates went into the upstream URL unchecked, redirects
were followed to any host, and responses had no size cap. The 30-second
timeout applied to each socket read, so a slow response could hold a
thread indefinitely. Each distinct `days` value in `/rates/history` caused
a separate upstream download. **Fix:** codes must be three capital letters
and dates ISO dates, or no request is made; redirects only on the ECB host
over the same scheme, at most three; a 32 MB cap; an overall deadline
checked between socket reads; history requests share four fetch windows;
the latest-rates parser drops malformed codes and dates. **Evidence:**

- A code of `G/../x` changed the upstream path before (the request went to
  `/EXR/x.EUR.SP00.A`); after, no request is made.
- A redirect to another host was followed before and is refused after.
- A 60 MB body was accepted before and is dropped after.
- A server sending one byte per second held the original call for 45
  seconds despite `timeout=10`; after, the call stops at its deadline.
- 20 history requests with distinct `days` cost 40 upstream fetches
  before and 2 after. The trimmed history is identical for every window
  boundary tested.

### L-09 — Outdated or floating images and build tools

nginx 1.27.5 (a branch with no further releases), untagged certbot, Node
20 (end of life in April 2026) and esbuild 0.23.0 (GHSA-67mh-4wv8-2f99,
development server only). **Fix:** `nginx:1.30-alpine` (current stable,
1.30.6), `certbot/certbot:v5.8.0`, `node:24-alpine`, esbuild 0.28.2 and
`python:3.11-slim-trixie`.

### L-10 — No log rotation

Docker's json-file driver never rotates, so logs would grow until the disk
filled and would keep visitor addresses indefinitely. **Fix:** 10 MB × 5
files per container, checked in `docker inspect`.

### L-11 — Local stack reachable from the local network

The local overlay published ports 80, 443 and 8000 on every interface,
with API docs on. **Fix:** 80 and 8000 on 127.0.0.1 only; the production
port list is replaced with `!override`.

### L-12 — Secret template and ignore rules

`.env.example` held working-looking secrets that START-LOCAL.md told
readers to copy, `.gitignore` missed `.env` variants, key and certificate
formats and the models archive, and `.gitignore` and `gitignore.txt` had
drifted apart. **Fix:** empty secrets with instructions for generating
them, broader rules (checked with `git check-ignore`), identical files.

### L-13 — Every container received every secret (new)

`env_file: .env` passed the whole file to both the backend and the
database, so Postgres held `ADMIN_SECRET`. **Fix:** each container gets
only the variables it needs, listed in `docker-compose.yml`. **Evidence:**
the database container has no `ADMIN_SECRET` and the backend has no
separate `POSTGRES_PASSWORD`.

### L-14 — A restart does not apply backend changes (new)

Both guides said to run `docker compose restart cortex` after changing
backend code or models. Code and models are copied into the image at
build time, so a restart keeps running the old image, and a security fix
applied that way would silently not take effect. **Fix:** the guides now
use `docker compose up -d --build cortex`.

### I-01 — Validation errors echoed input

422 answers repeated the submitted value. **Fix:** errors carry the field
location, message and type only, and the currency validator's message no
longer names the value.

### I-02 — Category names as object keys

Stored category names were used as plain object keys. A holding with the
category `constructor` broke the whole allocation chart (every slice
showed "—%") and one with `__proto__` disappeared. **Fix:** own-property
lookups and a `Map`. **Evidence:** all four test categories show correct
shares after.

### I-03 — Backend limit of 30 API calls per minute

An Exchange page load makes about nine API calls, and during the browser
tests normal browsing reached the limit within a minute (a 429 in the
console), on the original and the patched build alike. Visitors behind
one shared address, such as a university network, share that budget.
Left unchanged; raise `max_requests` in `main.py` if visitors report it.

## Not changed, with recommendations

- **I-03** above.
- **Git history.** Commit `cadda28` still contains the old server's
  address and the root login pattern. The server is deleted, so this has
  no security effect now. Removing it would need a history rewrite
  (`git filter-repo`), which changes every commit ID and needs a force
  push.
- **Busy answers during a cold start.** At most 8 forecast requests do
  model work at once. In the 60-visitor test, 12 requests were told to try
  again while the cache filled; the site then shows its preview with the
  message. With normal traffic this should be rare, because each currency
  is computed only once per data snapshot. Raise
  `FORECAST_COMPUTE_SLOTS` in `endpoints.py` if it happens often.
- **Hash-locked dependencies.** Generate a lock file with hashes for the
  server's platform (`pip-compile --generate-hashes`) and install with
  `--require-hashes`. Not done here, because the lock must be produced for
  the server's architecture and checked in a real build there.
- **Least-privilege database role.** The API connects as the Postgres
  superuser. The SQL for a limited role is in README-DEPLOYMENT.md.
- **Secrets in environment variables.** Anyone with Docker access can read
  them with `docker inspect`. The `docker` group already amounts to root
  on the host, so the server hardening steps matter more.
- **Image digests.** The tags now name maintained branches. Pinning by
  digest with a monthly rebuild, or a bot such as Renovate or Dependabot,
  would make updates deliberate.
- **The other 27 scaler files.** The restricted loader was tested on the
  two shipped scalers. The others come from the same trainer in the same
  format. If one is refused, the log names it, and retraining that
  currency replaces it.

## Look and behaviour of the site

The site's HTML and CSS sources are unchanged. Screenshots of all five
pages, taken with a fixed random seed from fresh stacks of both versions,
are pixel-identical on four pages. On the Exchange page 4 pixels differ,
at the anti-aliased corners of two summary tiles, each by one colour
level out of 255. Two captures of the original build are identical to
each other, so this comes from the newer esbuild, whose minified CSS
differs from the old one in whitespace only. The JavaScript changes only
alter what happens with malformed or hostile data.

## Evidence summary

| Check | Before | After |
|---|---|---|
| Scaler with `os.system` payload | Command ran | Refused, nothing ran |
| Scaler with payload in an object array | Command ran | Refused, nothing ran |
| `.keras` with a garbage `config.json` | Load failed parsing it | Weights load; config never read |
| 8 forecasts, distinct horizons | 1,128 model calls, 114 s | 180 calls, 18.5 s |
| 60 forecasts from 60 visitors | 13 answered; health checks failed | 60 answered in 18 s; health fine |
| Crafted Host through nginx, 40 requests | 0 limited | Refused by nginx; backend limits 10 |
| Rotating `X-Real-IP`, untrusted caller | 0 limited | 10 limited |
| 50,000 limiter identities | 50,000 kept | 20,000 cap |
| pip-audit | 23 entries, 4 packages | None |
| Admin, template token, remote caller | 200 | 403 |
| Admin path through nginx | Reached backend | 404 |
| Non-ASCII admin token | 500 | 403 |
| Headers on `app.js` (of 6) | 0 | 6 |
| CSP violations in Chromium | No CSP sent | 0 with CSP |
| Compose with no `.env` | Started on "localdev" | Refuses to start |
| Backend user | uid 0 | uid 10001, no capabilities |
| Server address in the guides | 16 | 0 |
| Renewed certificate | Never loaded | Loaded at the next reload |
| Payload in `/currencies` | Ran | Did not run |
| Payload in a stored alert id | Ran | Did not run |
| CSV cell `=HYPERLINK(...)` | Written as is | `'=HYPERLINK(...)` |
| CORS preflight for `x-admin-token` | 200 with credentials | 400 |
| `/openapi.json` in production | 200 | 404 |
| Unknown host over HTTP / TLS | Redirected / served | Closed / refused |
| TLS 1.2 CBC suite, session ticket | Accepted, issued | Refused, none |
| Upstream fetches, 20 history requests | 40 | 2 |
| Slow upstream response, `timeout=10` | Held 45 s | Stops at the deadline |
| API responses vs original code | | 15 of 15 identical (same libraries) |
| Regression tests | | 57 passed |
