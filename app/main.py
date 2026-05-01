import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.exceptions import AIProviderError, AnalysisError, ParseError, ReportGenerationError, ValidationError

logger = logging.getLogger(__name__)

_docs_url = "/docs" if settings.app_env != "production" else None
_redoc_url = "/redoc" if settings.app_env != "production" else None
_openapi_url = "/openapi.json" if settings.app_env != "production" else None

app = FastAPI(
    title="DeepLook API",
    description="WhatsApp Conversation Analytics Platform",
    version="1.0.0",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
    openapi_tags=[
        {"name": "System", "description": "Health and system status"},
        {"name": "Clients", "description": "Client management"},
        {"name": "Ingestion", "description": "File upload and webhook ingestion"},
        {"name": "Analytics", "description": "Analysis jobs and results"},
        {"name": "Delivery", "description": "Report generation and download"},
        {"name": "Dashboard", "description": "Dashboard API (Phase 2)"},
        {"name": "WhatsApp", "description": "WAHA integration — WhatsApp connection and sync"},
        {"name": "Billing", "description": "Plan quota and usage"},
        {"name": "Webhooks", "description": "Public webhook receivers (Wompi payments)"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(ParseError)
async def parse_error_handler(request: Request, exc: ParseError) -> JSONResponse:
    logger.error("ParseError: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=422,
        content={"error": "parse_error", "filename": exc.filename, "reason": exc.reason, "line_number": exc.line_number},
    )


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    logger.error("ValidationError: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=400,
        content={"error": "validation_error", "field": exc.field, "reason": exc.reason},
    )


@app.exception_handler(AIProviderError)
async def ai_provider_error_handler(request: Request, exc: AIProviderError) -> JSONResponse:
    logger.error("AIProviderError: %s", exc, exc_info=True)
    response = JSONResponse(
        status_code=502,
        content={"error": "ai_provider_error", "provider": exc.provider, "message": exc.message},
    )
    response.headers["Retry-After"] = "30"
    return response


@app.exception_handler(AnalysisError)
async def analysis_error_handler(request: Request, exc: AnalysisError) -> JSONResponse:
    logger.error("AnalysisError: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "analysis_error", "conversation_id": exc.conversation_id, "reason": exc.reason},
    )


@app.exception_handler(ReportGenerationError)
async def report_error_handler(request: Request, exc: ReportGenerationError) -> JSONResponse:
    logger.error("ReportGenerationError: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "report_generation_error", "job_id": exc.job_id, "reason": exc.reason},
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "message": "An unexpected error occurred."},
    )


# Startup / shutdown
@app.on_event("startup")
async def startup_event() -> None:
    if settings.database_url:
        try:
            from app.database import engine
            async with engine.begin() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            logger.info("Database connection verified.")
        except Exception as e:
            logger.error("Database connection failed: %s", e)
    else:
        logger.warning("DATABASE_URL not set — database connectivity not verified.")

    try:
        from app.analytics.ai.factory import create_provider
        provider = create_provider()
        logger.info("AI provider ready: %s / %s", provider.provider_name, provider.model_name)
    except Exception as e:
        logger.warning("AI provider not available: %s", e)

    if settings.clerk_jwks_url:
        try:
            from app.auth.clerk import warm_jwks_cache
            await warm_jwks_cache()
        except Exception as e:
            logger.warning("Clerk JWKS warm-up failed: %s", e)
    else:
        logger.warning(
            "CLERK_JWKS_URL not set — all protected endpoints will return 401."
        )

    # Start WhatsApp scheduler
    try:
        from app.services.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.error("Failed to start WhatsApp scheduler: %s", e)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    from app.services.scheduler import stop_scheduler
    stop_scheduler()

    try:
        from app.integrations.waha.client import get_waha_client
        await get_waha_client().aclose()
    except Exception:
        pass


# Routers
from app.auth.dependencies import get_current_user  # noqa: E402
from app.billing.router import router as billing_router  # noqa: E402
from app.ingestion.router import router as ingestion_router  # noqa: E402
from app.analytics.router import router as analytics_router  # noqa: E402
from app.delivery.router import router as delivery_router  # noqa: E402
from app.clients.router import router as clients_router  # noqa: E402
from app.whatsapp.router import router as whatsapp_router  # noqa: E402
from app.webhooks.router import router as webhooks_router  # noqa: E402
from app.notifications.router import router as notifications_router  # noqa: E402
from fastapi import Depends  # noqa: E402

app.include_router(billing_router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(delivery_router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(clients_router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(whatsapp_router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
app.include_router(notifications_router, prefix="/api/v1", dependencies=[Depends(get_current_user)])
# Wompi webhook — public, signature-verified internally
app.include_router(webhooks_router, prefix="/api/v1")


@app.get("/health", tags=["System"])
async def health() -> dict:
    return {
        "status": "ok",
        "version": "1.0.0",
        "ai_provider": settings.ai_provider,
        "ai_model": settings.ai_model,
    }
