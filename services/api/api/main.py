import logging

import httpx
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.auth import get_current_user
from api.config import settings
from api.database import engine, Base
from api.models import User
import api.models  # noqa: F401 — registers all models with Base
from api.routers import applications, analysis, auth, coach, resume

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

API_VERSION = "1.0.0"

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="HireIQ API",
    version=API_VERSION,
    description="Career intelligence API: manage job applications and trigger multi-agent analysis.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)


@app.on_event("startup")
def create_tables():
    """Safety net: ensures all model tables exist even if a migration is missed."""
    try:
        Base.metadata.create_all(bind=engine)
        logging.getLogger(__name__).info("DB tables created/verified via create_all")
    except Exception as exc:
        logging.getLogger(__name__).warning("DB create_all failed at startup: %s", exc)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Version"],
)


@app.middleware("http")
async def add_api_version_header(request: Request, call_next):
    """Attach X-API-Version to every response for client version negotiation."""
    response = await call_next(request)
    response.headers["X-API-Version"] = API_VERSION
    return response


app.include_router(auth.router, prefix="/api/v1")
app.include_router(applications.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(coach.router, prefix="/api/v1")
app.include_router(resume.router, prefix="/api/v1")


@app.post("/api/v1/company-preview", tags=["analysis"])
async def company_preview_proxy(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Proxy to agent-service /company-preview for quick company research during analysis."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": "Invalid JSON in request body."}, status_code=400)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{settings.agent_service_url}/company-preview", json=body)
            try:
                content = resp.json()
            except Exception:
                content = {"error": "Invalid response from agent service."}
            return JSONResponse(content=content, status_code=resp.status_code)
    except httpx.TimeoutException:
        return JSONResponse(content={"error": "Company research timed out."}, status_code=504)
    except httpx.RequestError:
        return JSONResponse(content={"error": "Could not reach agent service."}, status_code=502)


@app.get("/health", tags=["health"])
async def health():
    """Liveness check — always returns 200 if the process is up."""
    return {"status": "ok", "service": "api", "version": API_VERSION}


@app.get("/health/ready", tags=["health"])
async def readiness():
    """
    Readiness check — verifies DB and agent-service connectivity.

    Returns **503** if any dependency is unavailable.
    """
    errors: dict[str, str] = {}

    # Check PostgreSQL (offloaded to thread pool to avoid blocking the event loop)
    import asyncio
    from sqlalchemy import text

    async def _check_db():
        loop = asyncio.get_running_loop()
        def _ping():
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        await loop.run_in_executor(None, _ping)

    try:
        await asyncio.wait_for(_check_db(), timeout=3.0)
    except Exception as exc:
        errors["database"] = str(exc)

    # Check agent-service
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.agent_service_url}/health")
            if resp.status_code != 200:
                errors["agent_service"] = f"HTTP {resp.status_code}"
    except Exception as exc:
        errors["agent_service"] = str(exc)

    if errors:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "errors": errors},
        )

    return {"status": "ready", "service": "api", "version": API_VERSION}