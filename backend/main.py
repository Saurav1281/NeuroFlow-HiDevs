import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from redis.asyncio import Redis

from backend.config import settings
from backend.db.pool import init_pool, close_pool, get_pool
from backend.db.health import check_postgres, check_redis, check_mlflow
from backend.db.migrations import check_migrations
from backend.api import query, runs, pipelines, compare, evaluations, documents, auth
from backend.security.auth import get_current_user
from fastapi import Security, Depends
import uuid

from backend.resilience.circuit_breaker import CircuitBreaker, State
from backend.resilience.rate_limiter import RateLimiter
from backend.resilience.backpressure import BackpressureManager
from starlette.middleware.base import BaseHTTPMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup opentelemetry tracing
resource = Resource(attributes={
    SERVICE_NAME: "neuroflow-api"
})
provider = TracerProvider(resource=resource)
# Using gRPC exporter to Jaeger
otlp_exporter = OTLPSpanExporter(
    endpoint=f"http://{settings.JAEGER_HOST}:{settings.JAEGER_PORT}",
    insecure=True
)
processor = BatchSpanProcessor(otlp_exporter)
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up resources (BYPASSED for security testing)...")
    # Define state to avoid AttributeError in health/metrics
    app.state.cb = CircuitBreaker(None, "llm_api")
    app.state.limiter = RateLimiter(None)
    app.state.backpressure = BackpressureManager(max_buffer_size=100)
    yield
    # Shutdown
    logger.info("Shutting down resources...")

app = FastAPI(lifespan=lifespan, title="NeuroFlow API")

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
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
app.include_router(auth.router, prefix="/auth")
app.include_router(query.router, prefix="/query", dependencies=[Depends(get_current_user)])
app.include_router(runs.router, prefix="/runs", dependencies=[Depends(get_current_user)])
app.include_router(pipelines.router, prefix="/pipelines", dependencies=[Depends(get_current_user)])
app.include_router(compare.router, prefix="/compare", dependencies=[Depends(get_current_user)])
app.include_router(evaluations.router, prefix="/evaluations", dependencies=[Depends(get_current_user)])
app.include_router(documents.router, dependencies=[Depends(get_current_user)])

@app.get("/health")
async def health_check():
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
            "circuit_breaker": cb_state.value
        }
    }

@app.get("/metrics")
async def metrics():
    # Return prometheus metrics text format
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
