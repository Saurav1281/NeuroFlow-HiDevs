import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
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
from backend.db.retention import run_data_retention_job
from backend.resilience.backpressure import BackpressureManager
from backend.resilience.circuit_breaker import CircuitBreaker, State
from backend.resilience.rate_limiter import RateLimiter
from backend.security.auth import get_current_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup opentelemetry tracing
resource = Resource(attributes={SERVICE_NAME: "neuroflow-api"})
provider = TracerProvider(resource=resource)
# Using gRPC exporter to Jaeger
otlp_exporter = OTLPSpanExporter(
    endpoint=f"http://{settings.JAEGER_HOST}:{settings.JAEGER_PORT}", insecure=True
)
processor = BatchSpanProcessor(otlp_exporter)
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    logger.info("Initializing resources...")
    try:
        await init_pool()
        # Initialize Redis client
        app.state.redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
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
    
    # Initialize background jobs
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_data_retention_job, "cron", hour=3, minute=0)
    scheduler.start()
    app.state.scheduler = scheduler
    
    yield
    # Shutdown
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown()
        
    logger.info("Shutting down resources...")
    await close_pool()
    if hasattr(app.state, "redis") and app.state.redis:
        await app.state.redis.close()

description = """
NeuroFlow API helps you manage advanced RAG pipelines, fine-tuned models, and document knowledge bases.

## Getting Started

1. Set up an authentication client and retrieve a token via `/auth/token`.
2. Ingest documents using the **Ingestion** endpoints.
3. Configure your Retrieval-Augmented Generation processes via **Pipelines**.
4. Retrieve and generate text streams using the **Query** API.
5. Evaluate your query runs directly using the **Evaluation** API.

For client generation, we provide the `neuroflow` Python SDK.
"""

tags_metadata = [
    {
        "name": "auth",
        "description": "Authentication and authorization operations.",
    },
    {
        "name": "query",
        "description": "Operations for performing RAG queries and retrieving streamed chunks.",
    },
    {
        "name": "runs",
        "description": "Retrieve history and provide human ratings for executed queries.",
    },
    {
        "name": "pipelines",
        "description": "Design, manage, and analyze RAG generation pipelines and metrics.",
    },
    {
        "name": "compare",
        "description": "A/B test different RAG pipelines and their results side-by-side.",
    },
    {
        "name": "evaluations",
        "description": "Evaluate pipeline results utilizing multiple quality metrics (faithfulness, relevancy).",
    },
    {
        "name": "documents",
        "description": "Ingest and process text and URLs to build your retrieval knowledge base.",
    },
    {
        "name": "finetune",
        "description": "Start LLM fine-tuning jobs and monitor their progress.",
    }
]

app = FastAPI(
    title="NeuroFlow API",
    description=description,
    summary="Advanced RAG and Fine-Tuning developer platform.",
    version="1.0.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)


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
