import json
import os
from types import SimpleNamespace

from celery.utils.log import get_task_logger

from celery_app import celery
from job_store import get_job, init_db, update_job
from matcher import match_records

logger = get_task_logger(__name__)


@celery.task(bind=True, name="matcher.run_match_job")
def run_match_job(self, job_id: str):
    init_db()
    max_retries = int(os.getenv("MATCHER_TASK_MAX_RETRIES", "3"))
    retry_base = int(os.getenv("MATCHER_TASK_RETRY_BASE_SECONDS", "5"))

    job = get_job(job_id)
    if not job:
        logger.error("Job %s no encontrado.", job_id)
        return {"status": "FAILED", "error": "Job no encontrado"}

    if job.get("status") == "DONE":
        result = job.get("result_json")
        return {"status": "DONE", "result": json.loads(result) if result else {}}

    try:
        update_job(
            job_id,
            status="PROCESSING",
            started_at=job.get("started_at") or __import__("datetime").datetime.utcnow().isoformat(),
            attempts=(int(job.get("attempts") or 0) + 1),
            progress=10,
            error_message=None,
        )

        payload = json.loads(job["payload_json"])
        if not isinstance(payload, dict):
            raise ValueError("Payload invalido")
        if not isinstance(payload.get("dataA"), list) or not isinstance(payload.get("dataB"), list):
            raise ValueError("Payload debe incluir dataA y dataB como arrays")

        namespace = SimpleNamespace(
            dataA=payload.get("dataA", []),
            dataB=payload.get("dataB", []),
            config=SimpleNamespace(**payload.get("config", {})) if isinstance(payload.get("config"), dict) else None,
        )

        update_job(job_id, progress=70)
        results = match_records(namespace)
        payload_result = {"results": results}

        update_job(
            job_id,
            status="DONE",
            progress=100,
            result_json=payload_result,
            error_message=None,
            finished_at=__import__("datetime").datetime.utcnow().isoformat(),
        )
        return {"status": "DONE", "result": payload_result}
    except Exception as exc:  # noqa: BLE001
        retries = int(self.request.retries)
        logger.exception("Error en job %s intento %s: %s", job_id, retries + 1, exc)
        update_job(job_id, error_message=str(exc), progress=0)
        if retries < max_retries:
            countdown = retry_base * (2 ** retries)
            raise self.retry(exc=exc, countdown=countdown)

        update_job(
            job_id,
            status="FAILED",
            error_message=str(exc),
            finished_at=__import__("datetime").datetime.utcnow().isoformat(),
        )
        return {"status": "FAILED", "error": str(exc)}
