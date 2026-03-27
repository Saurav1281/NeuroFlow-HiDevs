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

from backend.config import settings
from backend.db.pool import init_pool, close_pool, get_pool
from backend.db.health import check_postgres, check_redis, check_mlflow
from backend.db.migrations import check_migrations
from backend.api import query, runs, pipelines, compare

from backend.resilience.circuit_breaker import CircuitBreaker, State
from backend.resilience.rate_limiter import RateLimiter
from backend.resilience.backpressure import BackpressureManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ... (opentelemetry config)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up resources...")
    await init_pool()
    # Initialize Resilience
    app.state.redis = get_pool() # Assuming redis pool is same as pg for now or needs separate init
    app.state.cb = CircuitBreaker(app.state.redis, "llm_api")
    app.state.limiter = RateLimiter(app.state.redis)
    app.state.backpressure = BackpressureManager(max_buffer_size=100)
    
    await check_migrations()
    yield
    # Shutdown
    logger.info("Shutting down resources...")
    await close_pool()

app = FastAPI(lifespan=lifespan, title="NeuroFlow API")

# Setup opentelemetry instrumentation
FastAPIInstrumentor.instrument_app(app)

# Register routes
app.include_router(query.router)
app.include_router(runs.router)
# ...

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
