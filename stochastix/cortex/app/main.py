import os
import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from collections import defaultdict

from cortex.app.api.v1 import endpoints
from cortex.app.core.database import engine, Base

logger = logging.getLogger("cortex.main")
logging.basicConfig(level=logging.INFO)

# Product name lives in one place; a future rename only needs APP_BRAND
# set in .env.
BRAND = os.getenv("APP_BRAND", "DeltaConvert")


# --- Rate Limiter (in-memory, per-IP) ---
class RateLimiter:
    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        window_start = now - self.window
        self.requests[client_ip] = [
            t for t in self.requests[client_ip] if t > window_start
        ]
        if len(self.requests[client_ip]) >= self.max_requests:
            return False
        self.requests[client_ip].append(now)
        return True


rate_limiter = RateLimiter(max_requests=30, window_seconds=60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified.")
    except Exception as e:
        # Multiple workers may race to create tables -- safe to ignore
        logger.warning(f"Table creation skipped (likely already exists): {e}")

    # Load popular models into RAM and trigger TF graph compilation
    # Warm whichever models are actually present, so a partial training
    # run (or a trimmed SUPPORTED_CURRENCIES) does not log failures for
    # models that were never meant to exist.
    try:
        available = sorted(
            name[4:-6]
            for name in os.listdir(endpoints.MODEL_DIR)
            if name.startswith("EUR_") and name.endswith(".keras")
        )
    except OSError:
        available = []
    warmup = [code for code in ["INR", "USD", "GBP", "JPY"] if code in available][:4]
    if not warmup:
        warmup = available[:4]
    logger.info(f"Loading models into cache: {warmup}")
    for curr in warmup:
        try:
            model, scaler = endpoints._load_model(f"EUR_{curr}")
            # Trigger TF graph compilation with a dummy predict call
            # so the first real user request is fast
            import numpy as np
            dummy = np.zeros((1, endpoints.WINDOW_SIZE, 1), dtype=np.float32)
            model.predict(dummy, verbose=0)
            logger.info(f"Cached + compiled EUR_{curr}")
        except Exception as e:
            logger.warning(f"Warmup skip {curr}: {e}")

    logger.info("Cortex ready.")
    yield
    endpoints.MODEL_CACHE.clear()


app = FastAPI(
    title=f"{BRAND} Cortex",
    version="1.2.0",
    description="Live reference rates and exchange rate forecasting engine.",
    lifespan=lifespan,
    docs_url=None if os.getenv("ENVIRONMENT") == "production" else "/docs",
    redoc_url=None if os.getenv("ENVIRONMENT") == "production" else "/redoc",
)

# CORS -- reads allowed origins from env, falls back to localhost for dev
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        # X-Real-IP is set by nginx to the actual connecting address
        # ($remote_addr) and cannot be spoofed by the client. X-Forwarded-For
        # is client-appendable and must not be trusted for limiting.
        client_ip = request.headers.get("X-Real-IP") or (
            request.client.host if request.client else "unknown"
        )
        if not rate_limiter.is_allowed(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again shortly."},
            )
    return await call_next(request)


app.include_router(endpoints.router, prefix="/api/v1", tags=["Rates & Forecast"])


@app.get("/health")
def health_check():
    return {
        "status": "online",
        "cache_size": len(endpoints.MODEL_CACHE),
    }
