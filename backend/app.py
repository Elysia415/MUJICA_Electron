import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
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

try:
    from backend.job_manager import (
        manager,
        run_plan_job,
        run_research_job,
        run_ingest_job,
        JobBase
    )
except ImportError:
    # Fallback for running directly from backend dir
    from job_manager import (
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

# ---------------------------
# Extended Imports for Feature Parity
# ---------------------------
import os
import shutil
from src.utils.llm import get_llm_client
from src.data_engine.storage import KnowledgeBase
from src.utils.chat_history import list_conversations, load_conversation, delete_conversation, rename_conversation
try:
    from backend.job_manager import manager
except ImportError:
    from job_manager import manager

# ---------------------------
# Helpers
# ---------------------------
def _update_env_file(updates: Dict[str, str]):
    """Update .env file preserving comments and structure."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        # Create new if not exists
        with open(env_path, "w", encoding="utf-8") as f:
            for k, v in updates.items():
                f.write(f"{k}={v}\n")
        return

    # Read existing lines
    lines = []
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Process updates
    new_lines = []
    updated_keys = set()
    
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        
        # Parse key
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
            
    # Append new keys
    for k, v in updates.items():
        if k not in updated_keys:
            new_lines.append(f"\n{k}={v}\n")
            
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

# ---------------------------
# Global Services
# ---------------------------
# Shared KB instance for read operations (listing papers etc)
# We lazily init it to avoid startup blocking
_kb_instance: Optional[KnowledgeBase] = None

def get_kb(force_refresh: bool = False) -> KnowledgeBase:
    """Get KB instance, optionally forcing a fresh connection for updated data."""
    global _kb_instance
    if _kb_instance is None or force_refresh:
        _kb_instance = KnowledgeBase()
        _kb_instance.initialize_db()
    return _kb_instance

def refresh_kb():
    """Force refresh of KB instance to see latest data."""
    global _kb_instance
    _kb_instance = None
    return get_kb()

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
    
    # Enrich stats with DB reality (Rating range, etc)
    kb = get_kb(force_refresh=True) # Ensure fresh connection
    enrich_stats = {}
    if kb and kb._meta_conn:
        try:
            # Create fresh cursor/connection if necessary, but kb._meta_conn is persistent in app context usually
            # But earlier we said it's thread-unsafe. get_kb() returns the global instance.
            # Ideally we generate a transient connection or use the one if safe.
            # Let's use a fresh connection to be safe as this runs in main thread (FastAPI worker)
            import sqlite3
            with sqlite3.connect(kb.metadata_path) as conn:
                # 1. Basic Stats
                row = conn.execute("SELECT COUNT(*), MIN(rating), MAX(rating), AVG(rating) FROM papers").fetchone()
                
                # 2. Distinct Years
                years = [r[0] for r in conn.execute("SELECT DISTINCT year FROM papers WHERE year IS NOT NULL ORDER BY year").fetchall()]
                
                # 3. Distinct Decisions
                decisions = [r[0] for r in conn.execute("SELECT DISTINCT decision FROM papers WHERE decision IS NOT NULL LIMIT 20").fetchall()]
                
                # 4. Distinct Venues (Top 5)
                venues = [r[0] for r in conn.execute("SELECT DISTINCT venue_id FROM papers WHERE venue_id IS NOT NULL LIMIT 10").fetchall()]
                
                enrich_stats = {
                    "paper_count": row[0],
                    "min_rating": row[1],
                    "max_rating": row[2],
                    "avg_rating": row[3],
                    "years": years,
                    "decisions": decisions,
                    "venues": venues,
                }
        except Exception as e:
            print(f"Error getting detailed stats: {e}")

    final_stats = req.stats or {}
    final_stats.update(enrich_stats)

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
            "stats": final_stats
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

@app.get("/api/kb/stats")
def get_kb_stats():
    """Get knowledge base statistics"""
    import sqlite3
    import lancedb
    
    result = {"papers": 0, "reviews": 0, "chunks": 0}
    kb = get_kb()
    
    # 1. SQLite Stats (Papers & Reviews)
    # Use path from the active KB instance to ensure we look at the right DB
    meta_path = getattr(kb, "metadata_path", None)
    
    if meta_path and os.path.exists(meta_path):
        try:
            conn = sqlite3.connect(meta_path)
            # Use read-only mode if possible, but standard connect is fine for WAL mode
            result["papers"] = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
            result["reviews"] = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
            conn.close()
        except Exception as e:
            print(f"[KB Stats] Error querying SQLite ({meta_path}): {e}")
    else:
        print(f"[KB Stats] Warning: Metadata DB path not found: {meta_path}")

    # 2. LanceDB Stats (Chunks)
    db_path = getattr(kb, "db_path", None)
    if db_path and os.path.exists(db_path):
        try:
            # Connect transiently to avoid threading/state issues with the shared 'kb' object
            ldb = lancedb.connect(db_path)
            if "chunks" in ldb.table_names():
                result["chunks"] = ldb.open_table("chunks").count_rows()
        except Exception as e:
            print(f"[KB Stats] Error querying LanceDB ({db_path}): {e}")

    return result

@app.post("/api/job/{job_id}/cancel")
def cancel_job(job_id: str):
    """Cancel a running job"""
    if job_id in jobs:
        job = jobs[job_id]
        if hasattr(job, "cancel_event"):
            job.cancel_event.set()
            return {"ok": True, "message": "Cancel signal sent"}
    return {"ok": False, "message": "Job not found or not cancellable"}

# ---------------------------
# Feature Parity API (KB/Config/History)
# ---------------------------

@app.post("/api/kb/refresh")
def refresh_kb_endpoint():
    """Force refresh KB connection to see latest data."""
    kb = refresh_kb()
    paper_count = 0
    if kb._meta_conn:
        try:
            paper_count = kb._meta_conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        except: pass
    return {"ok": True, "papers": paper_count}

@app.get("/api/kb/papers")
def list_papers(limit: int = 100, search: Optional[str] = None):
    """List papers from SQLite - always use fresh connection"""
    kb = get_kb(force_refresh=True)
    if not kb._meta_conn:
        return {"papers": []}
    
    cur = kb._meta_conn.cursor()
    query = "SELECT id, title, year, venue_id, decision, rating, pdf_path FROM papers"
    params = []
    
    if search:
        query += " WHERE title LIKE ? OR abstract LIKE ?"
        params.extend([f"%{search}%", f"%{search}%"])
    
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    
    rows = cur.execute(query, params).fetchall()
    return {"papers": [dict(r) for r in rows]}

@app.get("/api/kb/paper/{paper_id}")
def get_paper_detail(paper_id: str):
    """Get full paper details including reviews"""
    kb = get_kb()
    if not kb._meta_conn:
        raise HTTPException(404, "KB not initialized")
    
    cur = kb._meta_conn.cursor()
    
    # Fetch paper
    paper_row = cur.execute(
        """SELECT id, title, abstract, tldr, authors_json, keywords_json,
                  year, venue_id, decision, decision_text, rebuttal_text,
                  presentation, rating, pdf_url, pdf_path
           FROM papers WHERE id = ?""", 
        (paper_id,)
    ).fetchone()
    
    if not paper_row:
        raise HTTPException(404, "Paper not found")
    
    paper = dict(paper_row)
    
    # Parse JSON fields
    import json
    try:
        paper["authors"] = json.loads(paper.get("authors_json") or "[]")
    except:
        paper["authors"] = []
    try:
        paper["keywords"] = json.loads(paper.get("keywords_json") or "[]")
    except:
        paper["keywords"] = []
    
    # Fetch reviews
    review_rows = cur.execute(
        """SELECT idx, rating, rating_raw, confidence, confidence_raw,
                  summary, strengths, weaknesses, text
           FROM reviews WHERE paper_id = ? ORDER BY idx""",
        (paper_id,)
    ).fetchall()
    
    paper["reviews"] = [dict(r) for r in review_rows]
    
    return paper

@app.post("/api/kb/delete")
def delete_paper(paper_id: str = Query(..., description="Paper ID to delete")):
    """Delete paper from SQLite and LanceDB"""
    kb = get_kb()
    if not kb._meta_conn or not kb.db:
        raise HTTPException(500, "DB not initialized")
    
    # 1. SQLite
    try:
        cur = kb._meta_conn.cursor()
        cur.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
        cur.execute("DELETE FROM reviews WHERE paper_id = ?", (paper_id,))
        kb._meta_conn.commit()
    except Exception as e:
        raise HTTPException(500, f"SQLite delete failed: {e}")
        
    # 2. LanceDB
    try:
        if kb.papers_table in kb.db.table_names():
            kb.db.open_table(kb.papers_table).delete(f"id = '{paper_id}'")
        if kb.chunks_table in kb.db.table_names():
            kb.db.open_table(kb.chunks_table).delete(f"paper_id = '{paper_id}'")
    except Exception as e:
        print(f"LanceDB delete failed (non-fatal): {e}")
        
    return {"status": "ok"}

@app.get("/api/config")
def get_config():
    """Get current config (return values, mask secrets with indicators)"""
    return {
        # Non-sensitive values - return actual content
        "OPENAI_BASE_URL": os.getenv("OPENAI_BASE_URL", ""),
        "MUJICA_DEFAULT_MODEL": os.getenv("MUJICA_DEFAULT_MODEL", ""),
        "MUJICA_EMBEDDING_MODEL": os.getenv("MUJICA_EMBEDDING_MODEL", ""),
        "MUJICA_EMBEDDING_BASE_URL": os.getenv("MUJICA_EMBEDDING_BASE_URL", ""),
        "OPENREVIEW_USERNAME": os.getenv("OPENREVIEW_USERNAME", ""),
        
        # Sensitive values - return actual content (frontend will mask display)
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "MUJICA_EMBEDDING_API_KEY": os.getenv("MUJICA_EMBEDDING_API_KEY", ""),
        "OPENREVIEW_PASSWORD": os.getenv("OPENREVIEW_PASSWORD", ""),
        
        # Advanced settings
        "MUJICA_FAKE_EMBEDDINGS": os.getenv("MUJICA_FAKE_EMBEDDINGS", "0"),
        "MUJICA_DISABLE_JSON_MODE": os.getenv("MUJICA_DISABLE_JSON_MODE", "0"),
        
        # Status flags for UI hints
        "OPENAI_API_KEY_SET": bool(os.getenv("OPENAI_API_KEY")),
        "MUJICA_EMBEDDING_API_KEY_SET": bool(os.getenv("MUJICA_EMBEDDING_API_KEY")),
        "OPENREVIEW_CREDENTIALS_SET": bool(os.getenv("OPENREVIEW_USERNAME") and os.getenv("OPENREVIEW_PASSWORD"))
    }

@app.post("/api/config")
def update_config(conf: Dict[str, Any]):
    """Update environment variables"""
    # 1. Update os.environ
    for k, v in conf.items():
        if v is not None and v != '':
            os.environ[k] = str(v)
            
    # 2. Persist to .env (filter out None/empty values)
    to_save = {k: str(v) for k, v in conf.items() if v is not None and v != ''}
    if to_save:
        _update_env_file(to_save)
    return {"status": "updated"}

@app.get("/api/history")
def get_history_list():
    """List chat history"""
    return {"conversations": list_conversations()}

@app.get("/api/history/{cid}")
def get_history_detail(cid: str):
    """Load chat history"""
    data = load_conversation(cid)
    if not data:
        raise HTTPException(404, "Conversation not found")
    return data

@app.delete("/api/history/{cid}")
def del_history(cid: str):
    delete_conversation(cid)
    return {"status": "deleted"}

@app.post("/api/history/{cid}/rename")
def rename_history_endpoint(cid: str, data: Dict[str, str]):
    new_title = data.get("title")
    if not new_title:
        raise HTTPException(400, "New title required")
    res = rename_conversation(cid, new_title)
    if isinstance(res, dict) and not res.get("ok"):
         raise HTTPException(500, f"Rename failed: {res.get('error')}")
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
