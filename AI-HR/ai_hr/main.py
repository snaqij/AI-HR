"""FastAPI application entrypoint for the AI-HR backend."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a script before importing third-party modules that depend on stdlib names
# such as `copy`, which would otherwise be shadowed by `ai_hr/copy`.
if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[1]
    script_dir = str(Path(__file__).resolve().parent)
    sys.path[:] = [item for item in sys.path if Path(item or ".").resolve() != Path(script_dir).resolve()]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

if __package__ in {None, ""}:
    # Allow running as a script: python ai_hr/main.py
    from ai_hr.api.router import api_router
    from ai_hr.core.config import Settings, get_settings
    from ai_hr.core.exceptions import AIHRException, ResourceNotFoundError
    from ai_hr.core.idempotency import IdempotencyMiddleware
    from ai_hr.core.request_observability import RequestObservabilityMiddleware
    from ai_hr.core.responses import Envelope
    from ai_hr.db.base import Base
    from ai_hr.db.session import engine
    from ai_hr.services.providers.circuit_breaker import ProviderCircuitBreaker
    from ai_hr.services.providers.health import ProviderHealthService
else:
    from .api.router import api_router
    from .core.config import Settings, get_settings
    from .core.exceptions import AIHRException, ResourceNotFoundError
    from .core.idempotency import IdempotencyMiddleware
    from .core.request_observability import RequestObservabilityMiddleware
    from .core.responses import Envelope
    from .db.base import Base
    from .db.session import engine
    from .services.providers.circuit_breaker import ProviderCircuitBreaker
    from .services.providers.health import ProviderHealthService


def _resolve_cors_origins(settings: Settings) -> list[str]:
    raw_value = (settings.cors_allow_origins or "").strip()
    origins = [item.strip() for item in raw_value.split(",") if item.strip()]
    if not origins:
        origins = ["*"]
    is_production = (settings.environment or "").strip().lower() in {"prod", "production"}
    if is_production and "*" in origins:
        raise AIHRException("Wildcard CORS origin is forbidden in production; set explicit AI_HR_CORS_ALLOW_ORIGINS.")
    return origins


def create_app() -> FastAPI:
    settings = get_settings()
    provider_breaker = ProviderCircuitBreaker(
        fail_threshold=settings.provider_circuit_breaker_fail_threshold,
        cooldown_seconds=settings.provider_circuit_breaker_cooldown_seconds,
    )
    provider_health = ProviderHealthService(settings=settings, circuit_breaker=provider_breaker)
    cors_allow_origins = _resolve_cors_origins(settings)
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestObservabilityMiddleware)
    app.add_middleware(IdempotencyMiddleware)
    register_exception_handlers(app)

    @app.on_event("startup")
    def on_startup() -> None:
        init_database(settings)

    @app.get("/health", tags=["system"], response_model=Envelope[dict[str, str]])
    async def healthcheck() -> Envelope[dict[str, str]]:
        return Envelope.success(
            {
                "status": "ok",
                "environment": settings.environment,
            },
        )

    @app.get("/health/providers", tags=["system"], response_model=Envelope[dict[str, dict]])
    async def provider_healthcheck() -> Envelope[dict[str, dict]]:
        """外部 Provider 健康状态与熔断快照。"""
        return Envelope.success(provider_health.get_health())

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


def init_database(settings: Settings) -> None:
    if not settings.auto_create_tables:
        return
    Base.metadata.create_all(bind=engine)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        payload = Envelope.failure("validation_error", str(exc)).model_dump()
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=payload)

    @app.exception_handler(ResourceNotFoundError)
    async def handle_not_found(_: Request, exc: ResourceNotFoundError) -> JSONResponse:
        payload = Envelope.failure("not_found", str(exc)).model_dump()
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=payload)

    @app.exception_handler(AIHRException)
    async def handle_domain_error(_: Request, exc: AIHRException) -> JSONResponse:
        payload = Envelope.failure("domain_error", str(exc)).model_dump()
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=payload)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, __: Exception) -> JSONResponse:
        payload = Envelope.failure("internal_error", "Internal server error").model_dump()
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "ai_hr.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    run()
