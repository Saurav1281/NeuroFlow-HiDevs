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
from backend.db.pool import init_pool, close_pool
from backend.db.health import check_postgres, check_redis, check_mlflow
from backend.db.migrations import check_migrations
from backend.api import query, runs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenTelemetry configuration
resource = Resource(attributes={SERVICE_NAME: "neuroflow-api"})
provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=f"http://{settings.JAEGER_HOST}:{settings.JAEGER_PORT}", insecure=True))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up resources...")
    await init_pool()
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

@app.get("/health")
async def health_check():
    pg_ok = await check_postgres()
    redis_ok = await check_redis()
    mlflow_ok = await check_mlflow()
    
    status = "ok" if (pg_ok and redis_ok and mlflow_ok) else "degraded"
    
    return {
        "status": status,
        "checks": {
            "postgres": pg_ok,
            "redis": redis_ok,
            "mlflow": mlflow_ok
        }
    }

@app.get("/metrics")
async def metrics():
    # Return prometheus metrics text format
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
