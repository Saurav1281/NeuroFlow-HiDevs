import logging
from arq.connections import RedisSettings
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

from config import settings
from db.pool import init_pool, close_pool
from providers.client import NeuroFlowClient
from pipelines.ingestion.pipeline import process_document

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def startup(ctx):
    """Initialize resources for the worker process."""
    logger.info("Starting up worker resources...")
    
    # 1. OpenTelemetry
    resource = Resource(attributes={SERVICE_NAME: "neuroflow-worker"})
    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"http://{settings.JAEGER_HOST}:{settings.JAEGER_PORT}", insecure=True)
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    
    # 2. Database Pool
    await init_pool()
    
    # 3. LLM Client
    # Redis configuration for the LLM router metrics
    import redis.asyncio as redis
    redis_client = redis.Redis(
        host=settings.REDIS_HOST, 
        port=settings.REDIS_PORT, 
        password=settings.REDIS_PASSWORD,
        decode_responses=True
    )
    llm_client = NeuroFlowClient(redis=redis_client)
    await llm_client.initialize()
    ctx["redis"] = redis_client
    
async def shutdown(ctx):
    """Clean up resources for the worker process."""
    logger.info("Shutting down worker resources...")
    await close_pool()
    if ctx.get("redis"):
        await ctx["redis"].aclose()

class WorkerSettings:
    """Settings for the Arq worker."""
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD
    )
    functions = [process_document]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = "arq:queue"
    max_jobs = 4
