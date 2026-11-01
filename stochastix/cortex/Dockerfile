# Cortex — FastAPI rates and forecast backend.
#
# Container layout matches the code's expectations:
#   /app/cortex/app/      application package
#   /app/cortex/models/   29 .keras + 29 .joblib files
# MODEL_DIR in endpoints.py is hard-coded to /app/cortex/models, and
# PYTHONPATH=/app makes "cortex.app.*" imports resolve.

FROM python:3.11-slim

# scikit-learn and TensorFlow link against the OpenMP runtime, which the
# slim base image does not carry.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so editing application code does not re-run the
# long TensorFlow install on every rebuild.
COPY requirements.txt /app/cortex/requirements.txt
RUN pip install --no-cache-dir -r /app/cortex/requirements.txt

COPY . /app/cortex/

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    TF_CPP_MIN_LOG_LEVEL=2

EXPOSE 8000

# One worker keeps the in-memory model cache and rate limiter coherent.
CMD ["uvicorn", "cortex.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
