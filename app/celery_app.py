import os
from celery import Celery

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

celery = Celery(
    "matcher_jobs",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["tasks"],
)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_time_limit=int(os.getenv("MATCHER_TASK_TIME_LIMIT", "180")),
    task_soft_time_limit=int(os.getenv("MATCHER_TASK_SOFT_TIME_LIMIT", "150")),
)
