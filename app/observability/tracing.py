from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from app.config import settings
from app.observability.logging_config import logger

def setup_tracing(service_name: str = "codenavigator"):
    if not settings.OTEL_ENDPOINT:
        logger.info("tracing_disabled", reason="OTEL_ENDPOINT not set")
        return

    try:
        provider = TracerProvider()
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_ENDPOINT, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info("tracing_enabled", endpoint=settings.OTEL_ENDPOINT)
    except Exception as e:
        logger.error("tracing_setup_failed", error=str(e))
