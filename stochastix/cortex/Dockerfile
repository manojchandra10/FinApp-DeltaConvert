# Cortex — FastAPI rates and forecast backend.
#
# Container layout matches the code's expectations:
#   /app/cortex/app/      application package
#   /app/cortex/models/   29 .keras + 29 .joblib files
# MODEL_DIR in endpoints.py is hard-coded to /app/cortex/models, and
# PYTHONPATH=/app makes "cortex.app.*" imports resolve.
#
# .dockerignore keeps .env files, keys, tests, caches and archives out of
# the image.

FROM python:3.11-slim-trixie

# scikit-learn and TensorFlow link against the OpenMP runtime, which the
# slim base image does not carry.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# The API runs as a dedicated unprivileged user (uid 10001), never as root.
RUN groupadd --system --gid 10001 cortex \
 && useradd --system --uid 10001 --gid 10001 --create-home --home-dir /home/cortex \
      --shell /usr/sbin/nologin cortex

WORKDIR /app

# Dependencies first, so editing application code does not re-run the
# long TensorFlow install on every rebuild. pip and setuptools from the
# base image carry published advisories, so they are upgraded first.
COPY requirements.txt /app/cortex/requirements.txt
RUN pip install --no-cache-dir --upgrade pip==26.2.2 setuptools==84.2.1 \
 && pip install --no-cache-dir -r /app/cortex/requirements.txt

# Application code stays owned by root and read-only to the API user, so
# nothing running in the API can rewrite it. Only models/ is writable,
# which the documented training command needs.
COPY . /app/cortex/
RUN mkdir -p /app/cortex/models \
 && chown -R 10001:10001 /app/cortex/models \
 && chmod -R go-w /app/cortex/app /app/cortex/requirements.txt

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TF_CPP_MIN_LOG_LEVEL=2

USER 10001:10001

EXPOSE 8000

# One worker keeps the in-memory model cache and rate limiter coherent.
# --no-proxy-headers: the app decides itself which proxy headers to trust
# (core/security.py), so uvicorn must report the real TCP peer.
CMD ["uvicorn", "cortex.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-server-header"]
