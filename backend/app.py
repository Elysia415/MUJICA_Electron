import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------
# Path Setup
# ---------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = PROJECT_ROOT / "source"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

# ---------------------------
# Imports from Source
# ---------------------------
try:
    from src.utils.env import load_env
    load_env()  # Load environment variables
except ImportError as e:
    print(f"Error importing from source: {e}")

from backend.job_manager import (
    manager,
    run_plan_job,
    run_research_job,
    run_ingest_job,
    JobBase
)

# ---------------------------
# App & CORS
# ---------------------------
app = FastAPI(title="MUJICA Backend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Pydantic Models
# ---------------------------

class PlanRequest(BaseModel):
    query: str
    model_name: str = "gpt-4o"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    stats: Dict[str, Any] = {}

class ResearchRequest(BaseModel):
    plan: Dict[str, Any]
    model_name: str = "gpt-4o"
    chat_api_key: Optional[str] = None
    chat_base_url: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: Optional[str] = None
    embedding_base_url: Optional[str] = None

class IngestRequest(BaseModel):
    venue_id: str
    limit: Optional[int] = 50
    accepted_only: bool = False
    presentation_in: Optional[List[str]] = None
    skip_existing: bool = False
    download_pdfs: bool = True
    parse_pdfs: bool = True
    max_pdf_pages: Optional[int] = 12
    max_downloads: Optional[int] = None
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: Optional[str] = None
    embedding_base_url: Optional[str] = None

class JobResponse(BaseModel):
    job_id: str
    status: str
    type: str

# ---------------------------
# Endpoints
# ---------------------------

@app.get("/")
def health_check():
    return {"status": "ok", "service": "MUJICA Backend"}

@app.get("/api/jobs")
def list_jobs():
    """List all jobs (summary)"""
    with manager._lock:
        return {
            "jobs": [
                {
                    "job_id": j.job_id,
                    "type": j.type,
                    "status": j.status,
                    "message": j.message,
                    "started_ts": j.started_ts
                }
                for j in manager.jobs.values()
            ]
        }

@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    """Get detailed job status"""
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()

@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str):
    """Cancel a running job"""
    if manager.cancel_job(job_id):
        return {"status": "cancelled_requested"}
    raise HTTPException(status_code=404, detail="Job not found")

@app.post("/api/plan", response_model=JobResponse)
def start_plan(req: PlanRequest, background_tasks: BackgroundTasks):
    job = manager.create_job("plan")
    
    # Run in background thread (managed by logic inside job_manager to allow cancellation)
    # But since run_plan_job is synchronous, we wrap it in a thread here
    t = threading.Thread(
        target=run_plan_job,
        kwargs={
            "job": job,
            "user_query": req.query,
            "model_name": req.model_name,
            "api_key": req.api_key,
            "base_url": req.base_url,
            "stats": req.stats
        },
        daemon=True
    )
    job.thread = t
    t.start()
    
    return {"job_id": job.job_id, "status": "init", "type": "plan"}

@app.post("/api/research", response_model=JobResponse)
def start_research(req: ResearchRequest, background_tasks: BackgroundTasks):
    job = manager.create_job("research")
    
    t = threading.Thread(
        target=run_research_job,
        kwargs={
            "job": job,
            "plan": req.plan,
            "model_name": req.model_name,
            "chat_api_key": req.chat_api_key,
            "chat_base_url": req.chat_base_url,
            "embedding_model": req.embedding_model,
            "embedding_api_key": req.embedding_api_key,
            "embedding_base_url": req.embedding_base_url,
        },
        daemon=True
    )
    job.thread = t
    t.start()
    
    return {"job_id": job.job_id, "status": "init", "type": "research"}

@app.post("/api/ingest", response_model=JobResponse)
def start_ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    job = manager.create_job("ingest")
    
    t = threading.Thread(
        target=run_ingest_job,
        kwargs={
            "job": job,
            "venue_id": req.venue_id,
            "limit": req.limit,
            "accepted_only": req.accepted_only,
            "presentation_in": req.presentation_in,
            "skip_existing": req.skip_existing,
            "download_pdfs": req.download_pdfs,
            "parse_pdfs": req.parse_pdfs,
            "max_pdf_pages": req.max_pdf_pages,
            "max_downloads": req.max_downloads,
            "embedding_model": req.embedding_model,
            "embedding_api_key": req.embedding_api_key,
            "embedding_base_url": req.embedding_base_url,
        },
        daemon=True
    )
    job.thread = t
    t.start()
    
    return {"job_id": job.job_id, "status": "init", "type": "ingest"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
