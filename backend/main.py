import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request

from backend.api import auth, compare, documents, evaluations, finetune, pipelines, query, runs
from backend.config import settings
from backend.db.health import check_mlflow, check_postgres, check_redis
from backend.db.pool import close_pool, init_pool
from backend.resilience.backpressure import BackpressureManager
from backend.resilience.circuit_breaker import CircuitBreaker, State
from backend.resilience.rate_limiter import RateLimiter
from backend.security.auth import get_current_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup opentelemetry tracing (graceful degradation if Jaeger unavailable)
try:
    resource = Resource(attributes={SERVICE_NAME: "neuroflow-api"})
    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(
        endpoint=f"http://{settings.JAEGER_HOST}:{settings.JAEGER_PORT}", insecure=True
    )
    processor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    logger.info("OpenTelemetry tracing initialized.")
except Exception as e:
    logger.warning(f"OpenTelemetry tracing unavailable: {e}")



@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    logger.info("Initializing resources...")
    try:
        await init_pool()
        # Initialize Redis client
        app.state.redis = Redis.from_url(settings.get_redis_url(), decode_responses=True)
        # Initialize resilience components with real Redis
        app.state.cb = CircuitBreaker(app.state.redis, "llm_api")
        app.state.limiter = RateLimiter(app.state.redis)
        logger.info("Resources initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize resources: {e}")
        # Fallback to no-op versions to allow startup but degraded mode
        app.state.cb = CircuitBreaker(None, "llm_api")
        app.state.limiter = RateLimiter(None)

    app.state.backpressure = BackpressureManager(max_buffer_size=100)
    yield
    # Shutdown
    logger.info("Shutting down resources...")
    await close_pool()
    if hasattr(app.state, "redis") and app.state.redis:
        await app.state.redis.close()


app = FastAPI(lifespan=lifespan, title="NeuroFlow API")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        logger.info(f"SECURITY_DEBUG: Middleware reached for {request.url.path}")
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# Moved middleware to top

# Setup opentelemetry instrumentation
# FastAPIInstrumentor.instrument_app(app) # Disabled for security debugging

# Register routes
app.include_router(auth.router)
app.include_router(query.router, dependencies=[Depends(get_current_user)])
app.include_router(runs.router, dependencies=[Depends(get_current_user)])
app.include_router(pipelines.router, dependencies=[Depends(get_current_user)])
app.include_router(compare.router, dependencies=[Depends(get_current_user)])
app.include_router(evaluations.router, dependencies=[Depends(get_current_user)])
app.include_router(documents.router, dependencies=[Depends(get_current_user)])
app.include_router(finetune.router, dependencies=[Depends(get_current_user)])


@app.get("/health")
async def health_check() -> dict[str, Any]:
    pg_ok = await check_postgres()
    redis_ok = await check_redis()
    mlflow_ok = await check_mlflow()

    # Resilience status
    cb_state = await app.state.cb._get_state()

    status = "ok" if (pg_ok and redis_ok and mlflow_ok and cb_state != State.OPEN) else "degraded"

    return {
        "status": status,
        "checks": {
            "postgres": pg_ok,
            "redis": redis_ok,
            "mlflow": mlflow_ok,
            "circuit_breaker": cb_state.value,
        },
    }


@app.get("/metrics")
async def metrics() -> Response:
    # Return prometheus metrics text format
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
