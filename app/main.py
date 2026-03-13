import json
import os
import uuid
from typing import Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from job_store import create_job, get_job, init_db
from matcher import match_records
from tasks import run_match_job

app = FastAPI()

class MatchConfig(BaseModel):
    weights: Optional[Dict] = None

class MatchRequest(BaseModel):
    dataA: List[Dict]
    dataB: List[Dict]
    config: Optional[MatchConfig] = None


class MatchJobRequest(BaseModel):
    dataA: List[Dict] = Field(..., min_length=1)
    dataB: List[Dict] = Field(..., min_length=1)
    config: Optional[MatchConfig] = None


def _require_token(authorization: Optional[str]) -> None:
    expected = os.getenv("MATCHER_JOB_TOKEN", "").strip()
    if expected == "":
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")
    received = authorization.replace("Bearer ", "", 1).strip()
    if received != expected:
        raise HTTPException(status_code=401, detail="Token invalido")


@app.on_event("startup")
def startup_event():
    init_db()


@app.post("/match")
def match_endpoint(request: MatchRequest):
    results = match_records(request)
    return {"results": results}


@app.post("/jobs/match")
def create_match_job(
    request: MatchJobRequest,
    authorization: Optional[str] = Header(default=None),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id"),
):
    _require_token(authorization)
    if not idempotency_key or idempotency_key.strip() == "":
        raise HTTPException(status_code=422, detail="Idempotency-Key es requerido")

    payload = request.model_dump()
    trace_id = (x_trace_id or x_request_id or str(uuid.uuid4())).strip()
    job = create_job(idempotency_key.strip(), payload, trace_id)

    # Idempotencia: solo encolar si esta PENDING.
    if job.get("status") == "PENDING":
        run_match_job.delay(job["job_id"])

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "trace_id": job.get("trace_id"),
    }


@app.get("/jobs/{job_id}")
def get_match_job(job_id: str, authorization: Optional[str] = Header(default=None)):
    _require_token(authorization)
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    result = None
    if job.get("result_json"):
        try:
            result = json.loads(job["result_json"])
        except Exception:  # noqa: BLE001
            result = None

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": int(job.get("progress") or 0),
        "attempts": int(job.get("attempts") or 0),
        "trace_id": job.get("trace_id"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "result": result,
        "error": job.get("error_message"),
    }