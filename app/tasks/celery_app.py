from celery import Celery
from app.config import settings

celery_app = Celery(
    "onboarding_agent",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.ingestion_task"]
)

# Optional configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_routes={"app.tasks.ingestion_task.run_ingestion": {"queue": "ingestion"}},
    broker_connection_retry_on_startup=False,
    broker_connection_timeout=3,
    broker_connection_max_retries=1,
)
