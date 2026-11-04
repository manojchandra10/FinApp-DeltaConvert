import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cortex.app.api.v1 import endpoints
from cortex.app.core import security
from cortex.app.core.database import engine, Base

logger = logging.getLogger("cortex.main")
logging.basicConfig(level=logging.INFO)

# Product name lives in one place; a future rename only needs APP_BRAND
# set in .env.
BRAND = os.getenv("APP_BRAND", "DeltaConvert")

# API docs and the OpenAPI schema are served only when the environment is
# explicitly a development one. An unset or misspelt ENVIRONMENT counts as
# production, so the schema can never appear on the server by accident.
ENVIRONMENT = os.getenv("ENVIRONMENT", "production").strip().lower()
DEV_MODE = ENVIRONMENT in {"development", "dev", "local"}


# --- Rate Limiter (in-memory, per client) ---
# The rule is unchanged: 30 API calls per client per minute. The client is
# the TCP peer, or the X-Real-IP that nginx sets when the peer is a trusted
# proxy (see core/security.py).
rate_limiter = security.RateLimiter(max_requests=30, window_seconds=60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified.")
    except Exception as e:
        # Multiple workers may race to create tables -- safe to ignore
        logger.warning(f"Table creation skipped (likely already exists): {e}")

    problem = security.admin_secret_problem(os.getenv("ADMIN_SECRET", ""))
    if problem:
        logger.warning(f"{problem}; the audit-resolve endpoint refuses every request until a strong secret is set.")

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
            logger.warning(f"Warmup skip {curr}: {getattr(e, 'detail', e)}")

    logger.info("Cortex ready.")
    yield
    endpoints.MODEL_CACHE.clear()


app = FastAPI(
    title=f"{BRAND} Cortex",
    version="1.2.0",
    description="Live reference rates and exchange rate forecasting engine.",
    lifespan=lifespan,
    docs_url="/docs" if DEV_MODE else None,
    redoc_url="/redoc" if DEV_MODE else None,
    openapi_url="/openapi.json" if DEV_MODE else None,
)

# CORS. The site calls the API on its own origin, so production needs no
# cross-origin access at all; CORS_ORIGINS lists exact origins for the
# cases that do (the local http.server workflow in site/README.md). No
# credentials, and only the two headers the frontend sends.
_DEV_ORIGINS = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
ALLOWED_ORIGINS = security.parse_cors_origins(
    os.getenv("CORS_ORIGINS", _DEV_ORIGINS if DEV_MODE else "")
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # scope["path"] is the path the router matches. request.url.path is
    # rebuilt from the Host header and can be emptied by a crafted Host,
    # which used to let requests skip the limiter.
    if request.scope.get("path", "").startswith("/api/"):
        key = security.rate_limit_key(security.client_address(request))
        if not rate_limiter.is_allowed(key):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again shortly."},
            )
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # FastAPI's default 422 body repeats the submitted value back. Keep the
    # field location and the message only.
    errors = [
        {"loc": list(error.get("loc", ())), "msg": error.get("msg", "Invalid value."), "type": error.get("type", "value_error")}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


app.include_router(endpoints.router, prefix="/api/v1", tags=["Rates & Forecast"])


@app.get("/health")
def health_check():
    return {
        "status": "online",
        "cache_size": len(endpoints.MODEL_CACHE),
    }
