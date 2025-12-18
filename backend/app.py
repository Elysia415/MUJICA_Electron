import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import zipfile
import shutil
import tempfile
import datetime
import io
import os
import json
import sqlite3
# Try importing lancedb, but don't crash if missing (though it should be there)
try:
    import lancedb
    import pyarrow as pa
except ImportError:
    lancedb = None
    pass

# ---------------------------
# Path Setup
# ---------------------------
# Detect if running in PyInstaller bundle
IS_PACKAGED = getattr(sys, 'frozen', False)

def _get_source_root():
    """Get the source root path, handling PyInstaller bundling."""
    if IS_PACKAGED and hasattr(sys, '_MEIPASS'):
        # Running in PyInstaller bundle - src is directly under _MEIPASS
        return Path(sys._MEIPASS)
    else:
        # Running in normal Python environment - source is under project root
        return Path(__file__).resolve().parent.parent / "source"

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # Always points to MUJICA_Electron in dev
SOURCE_ROOT = _get_source_root()

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

# Also add the parent of src for module resolution (for `from src.utils import ...`)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# User config directory (for .env persistence in packaged app)
# Use %APPDATA%/MUJICA on Windows, ~/.mujica on Unix
if os.name == 'nt':
    USER_CONFIG_DIR = Path(os.environ.get('APPDATA', os.path.expanduser('~'))) / 'MUJICA'
else:
    USER_CONFIG_DIR = Path.home() / '.mujica'
USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
USER_ENV_PATH = USER_CONFIG_DIR / '.env'

# Data directory - use user directory in packaged mode, project directory in dev mode
if IS_PACKAGED:
    DATA_DIR = USER_CONFIG_DIR / 'data'
else:
    DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------
# Imports from Source
# ---------------------------
try:
    from src.utils.env import load_env
    load_env()  # Load environment variables
except ImportError as e:
    print(f"Warning: Could not import from source: {e}")
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"SOURCE_ROOT: {SOURCE_ROOT}")
    print(f"sys.path: {sys.path[:5]}...")
    # Try to load dotenv directly as fallback
    try:
        from dotenv import load_dotenv
        if USER_ENV_PATH.exists():
            load_dotenv(USER_ENV_PATH)
    except:
        pass

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
    expose_headers=["Content-Length", "Content-Disposition"],
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
    """Update .env file in user config directory (not installation dir)."""
    env_path = USER_ENV_PATH  # Use user directory instead of PROJECT_ROOT
    
    if not env_path.exists():
        # Create new if not exists
        with open(env_path, "w", encoding="utf-8") as f:
            for k, v in updates.items():
                f.write(f"{k}={v}\n")
        # Also update current process env
        for k, v in updates.items():
            os.environ[k] = str(v)
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
    
    # Also update current process env
    for k, v in updates.items():
        os.environ[k] = str(v)

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
        # Use absolute path for data directory
        kb_path = str(DATA_DIR / "lancedb")
        _kb_instance = KnowledgeBase(db_path=kb_path)
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
    if manager.cancel_job(job_id):
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
    try:
        kb = get_kb(force_refresh=True)
        if not kb or not kb._meta_conn:
            print("[ListPapers] KB or connection not initialized")
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
    except Exception as e:
        import traceback
        print(f"[ListPapers] Error: {e}")
        traceback.print_exc()
        raise HTTPException(500, f"Failed to list papers: {str(e)}")

@app.get("/api/kb/semantic-search")
def semantic_search_papers(query: str = Query(..., min_length=1), limit: int = 20):
    """
    Semantic search using vector embeddings.
    Returns papers ranked by similarity to the query.
    """
    from src.data_engine.storage import KnowledgeBase
    
    kb = get_kb(force_refresh=True)
    
    try:
        # Use search_chunks for chunk-level semantic search
        results = kb.search_chunks(query, limit=limit)
        
        # Deduplicate by paper_id and aggregate scores
        papers_map = {}
        for r in results:
            paper_id = r.get("paper_id")
            if not paper_id:
                continue
            
            distance = r.get("_distance", 1.0)
            # Convert distance to similarity (LanceDB uses L2 distance)
            similarity = max(0, 1 - distance) if distance else 0.5
            
            if paper_id not in papers_map:
                papers_map[paper_id] = {
                    "id": paper_id,
                    "title": r.get("title", ""),
                    "year": r.get("year"),
                    "venue_id": r.get("venue_id"),
                    "decision": r.get("decision"),
                    "rating": r.get("rating"),
                    "similarity": similarity,
                    "matched_chunk": r.get("text", "")[:200] + "..." if r.get("text") else "",
                    "source": r.get("source", ""),
                }
            else:
                # Keep the higher similarity score
                if similarity > papers_map[paper_id]["similarity"]:
                    papers_map[paper_id]["similarity"] = similarity
                    papers_map[paper_id]["matched_chunk"] = r.get("text", "")[:200] + "..." if r.get("text") else ""
        
        # Sort by similarity descending
        papers = sorted(papers_map.values(), key=lambda x: x["similarity"], reverse=True)
        
        return {"papers": papers, "mode": "semantic"}
    except Exception as e:
        print(f"[Semantic Search] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Semantic search failed: {e}")

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

# ---------------------------
# PDF Viewer API
# ---------------------------
@app.post("/api/open-pdf")
def open_pdf(data: Dict[str, str]):
    """Open PDF file in system default viewer"""
    import subprocess
    import os
    
    pdf_path = data.get("pdf_path", "")
    if not pdf_path:
        raise HTTPException(400, "pdf_path is required")
    
    # Resolve relative path from backend directory
    if not os.path.isabs(pdf_path):
        pdf_path = os.path.join(os.path.dirname(__file__), pdf_path)
    
    if not os.path.exists(pdf_path):
        raise HTTPException(404, f"PDF not found: {pdf_path}")
    
    try:
        # Windows
        if sys.platform == "win32":
            os.startfile(pdf_path)
        # macOS
        elif sys.platform == "darwin":
            subprocess.run(["open", pdf_path], check=True)
        # Linux
        else:
            subprocess.run(["xdg-open", pdf_path], check=True)
        return {"status": "ok", "path": pdf_path}
    except Exception as e:
        raise HTTPException(500, f"Failed to open PDF: {e}")

@app.post("/api/system/open_folder")
def open_folder(path_data: dict):
    """Open a folder in the system file explorer"""
    path = path_data.get("path")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Path not found")
    
    try:
        if os.name == 'nt': # Windows
            os.startfile(path)
        elif sys.platform == 'darwin': # macOS
            subprocess.run(["open", path], check=True)
        else: # Linux
            subprocess.run(["xdg-open", path], check=True)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, f"Failed to open folder: {e}")

# ---------------------------
# KB Import / Export API
# ---------------------------

def calculate_dir_size(path):
    total_size = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            total_size += os.path.getsize(fp)
    return total_size

@app.get("/api/kb/export_local")
async def export_kb_local():
    """Export KB locally with SSE progress"""
    
    # Target directory: Desktop/MUJICA_Backups
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    backup_dir = os.path.join(desktop, "MUJICA_Backups")
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"mujica_kb_backup_{timestamp}.zip"
    target_path = os.path.join(backup_dir, filename)
    
    kb_path = DATA_DIR / "lancedb"
    if not kb_path.exists():
        raise HTTPException(404, "KB not found")
        
    async def generate():
        total_size = calculate_dir_size(kb_path)
        processed_size = 0
        
        # Initial yield
        yield json.dumps({"progress": 0, "status": "Starting..."}) + "\n"
        
        try:
            with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_STORED) as zf:
                # 1. Metadata
                sqlite_path = kb_path / "metadata.sqlite"
                if sqlite_path.exists():
                    zf.write(sqlite_path, arcname="metadata.sqlite")
                    processed_size += sqlite_path.stat().st_size
                    yield json.dumps({"progress": int(processed_size / total_size * 100), "status": "Archiving metadata..."}) + "\n"
                
                # 2. LanceDB
                for db_name in ["papers.lance", "chunks.lance"]:
                    db_path = kb_path / db_name
                    if db_path.exists():
                        for root, dirs, files in os.walk(db_path):
                            for file in files:
                                file_path = Path(root) / file
                                rel_path = file_path.relative_to(kb_path)
                                zf.write(file_path, arcname=str(rel_path))
                                
                                processed_size += file_path.stat().st_size
                                # Yield every 1% or 10MB to avoid spamming
                                # But for smooth bar, every file is okay if small
                                yield json.dumps({
                                    "progress": min(99, int(processed_size / total_size * 100)),
                                    "status": f"Archiving {rel_path}"
                                }) + "\n"
            
            # Done
            yield json.dumps({"progress": 100, "status": "Done", "path": target_path, "dir": backup_dir}) + "\n"
            
        except Exception as e:
            yield json.dumps({"error": str(e)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
@app.get("/api/kb/export")
def export_kb(background_tasks: BackgroundTasks):
    """Export Knowledge Base (SQLite + LanceDB) as ZIP"""
    print(f"[KB Export] Request received, starting export process...")
    print(f"[KB Export] Strategy: Disk-based buffer (NamedTemporaryFile) with ZIP_STORED")
    
    kb_path = DATA_DIR / "lancedb"
    if not kb_path.exists():
        raise HTTPException(404, "Knowledge base data not found")
    
    # Create a temp file on disk, NOT in memory
    # delete=False because we need to re-open it for streaming
    # We use a try-finally block for safety only if writing fails, but for streaming we need it to persist
    
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_file.close() # Close immediately, we just wanted a name
    temp_path = Path(tmp_file.name)
        
    try:
        # Write to disk
        print(f"[KB Export] Writing zip to temp file: {temp_path}")
        with zipfile.ZipFile(temp_path, mode="w", compression=zipfile.ZIP_STORED) as zf:
            # 1. Archive metadata.sqlite
            sqlite_path = kb_path / "metadata.sqlite"
            if sqlite_path.exists():
                zf.write(sqlite_path, arcname="metadata.sqlite")
            
            # 2. Archive LanceDB tables
            for db_name in ["papers.lance", "chunks.lance"]:
                db_path = kb_path / db_name
                if db_path.exists():
                    for root, dirs, files in os.walk(db_path):
                        for file in files:
                            file_path = Path(root) / file
                            rel_path = file_path.relative_to(kb_path)
                            zf.write(file_path, arcname=str(rel_path))
        
        file_size = temp_path.stat().st_size
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"mujica_kb_backup_{timestamp}.zip"
        
        print(f"[KB Export] ZIP created on disk successfully")
        print(f"[KB Export] File size: {file_size} bytes ({file_size / 1024 / 1024:.2f} MB)")
        print(f"[KB Export] Sending stream...")

        # Schedule cleanup
        background_tasks.add_task(os.remove, temp_path)
        
        return StreamingResponse(
            open(temp_path, "rb"),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Length": str(file_size)
            }
        )

    except Exception as e:
        print(f"[KB Export] Error during export: {e}")
        if temp_path.exists():
            os.remove(temp_path)
        raise HTTPException(500, f"Export failed: {e}")

@app.post("/api/kb/import")
async def import_kb(file: UploadFile = File(...)):
    """Import and Merge Knowledge Base from ZIP"""
    import traceback
    
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "Only .zip files are supported")
    
    try:
        kb_path = DATA_DIR / "lancedb"
        kb_path.mkdir(parents=True, exist_ok=True)
        print(f"[Import] kb_path: {kb_path}")
        
        # Use tempfile for extraction - ALL operations must be inside this block
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            zip_path = tmp_path / "upload.zip"
            
            # Save uploaded file
            print(f"[Import] Saving upload to: {zip_path}")
            with open(zip_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            
            # Create extraction directory
            extract_dir = tmp_path / "extracted"
            extract_dir.mkdir()
            
            # Extract ZIP
            try:
                print(f"[Import] Extracting to: {extract_dir}")
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(extract_dir)
                print(f"[Import] Extracted files: {list(extract_dir.iterdir())}")
            except zipfile.BadZipFile:
                raise HTTPException(400, "Invalid zip file")
            
            # 2. Merge SQLite (metadata) - INSERT OR IGNORE to add without overwriting
            src_sqlite = extract_dir / "metadata.sqlite"
            dst_sqlite = kb_path / "metadata.sqlite"
            
            if src_sqlite.exists() and src_sqlite.is_file():
                print(f"[Import] Processing SQLite: {src_sqlite} ({src_sqlite.stat().st_size / 1024 / 1024:.2f} MB)")
                if not dst_sqlite.exists():
                    print(f"[Import] Copying new SQLite database")
                    shutil.copy2(src_sqlite, dst_sqlite)
                else:
                    print(f"[Import] Merging into existing SQLite database")
                    _merge_sqlite(str(src_sqlite), str(dst_sqlite))
            
            # 3. Merge LanceDB (vectors) - Add/Append, not overwrite
            if lancedb:
                for table_name in ["papers", "chunks"]:
                    src_tbl_dir = extract_dir / f"{table_name}.lance"
                    dst_tbl_dir = kb_path / f"{table_name}.lance"
                    
                    if src_tbl_dir.exists() and src_tbl_dir.is_dir():
                        print(f"[Import] Processing LanceDB table: {table_name}")
                        try:
                            if not dst_tbl_dir.exists():
                                # Direct copy if destination doesn't exist
                                print(f"[Import] Copying new table: {table_name}")
                                shutil.copytree(src_tbl_dir, dst_tbl_dir)
                            else:
                                # Append/merge data into existing table
                                print(f"[Import] Merging into existing table: {table_name}")
                                src_db = lancedb.connect(str(extract_dir))
                                dst_db = lancedb.connect(str(kb_path))
                                
                                if table_name in src_db.table_names() and table_name in dst_db.table_names():
                                    src_tbl = src_db.open_table(table_name)
                                    dst_tbl = dst_db.open_table(table_name)
                                    
                                    # Get total count for progress
                                    total_rows = src_tbl.count_rows()
                                    print(f"[Import] Source has {total_rows} rows in {table_name}")
                                    
                                    # Batch process to avoid memory issues
                                    batch_size = 10000
                                    offset = 0
                                    total_added = 0
                                    
                                    while offset < total_rows:
                                        # Use LanceDB's search with limit/offset for batching
                                        batch_df = src_tbl.to_pandas()[offset:offset + batch_size]
                                        if batch_df.empty:
                                            break
                                        
                                        batch_data = batch_df.to_dict('records')
                                        if batch_data:
                                            dst_tbl.add(batch_data)
                                            total_added += len(batch_data)
                                            print(f"[Import] Added {total_added}/{total_rows} records to {table_name}")
                                        
                                        offset += batch_size
                                    
                                    print(f"[Import] Completed merging {total_added} records into {table_name}")
                        except Exception as e:
                            print(f"[Import] LanceDB error for {table_name} (non-fatal): {e}")
                            traceback.print_exc()
            
            # Return success - this is inside the with block
            return {"status": "ok", "message": "Import and merge completed"}
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[Import] Fatal error: {e}")
        traceback.print_exc()
        raise HTTPException(500, f"Import failed: {str(e)}")

def _merge_sqlite(src_path: str, dst_path: str):
    """Helper to merge SQLite databases using INSERT OR IGNORE"""
    print(f"[SQLite Merge] Starting: {src_path} -> {dst_path}")
    
    conn_src = sqlite3.connect(src_path)
    conn_dst = sqlite3.connect(dst_path)
    conn_dst.row_factory = sqlite3.Row
    
    try:
        # Get all tables from source
        cursor_src = conn_src.cursor()
        cursor_src.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables_info = cursor_src.fetchall()
        
        print(f"[SQLite Merge] Found {len(tables_info)} tables in source")
        
        for table_name, create_sql in tables_info:
            print(f"[SQLite Merge] Processing table: {table_name}")
            
            # Check if table exists in destination
            cursor_dst = conn_dst.cursor()
            cursor_dst.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            
            if not cursor_dst.fetchone():
                # Table doesn't exist - create it using the same schema
                print(f"[SQLite Merge] Creating table {table_name} in destination")
                conn_dst.execute(create_sql)
                conn_dst.commit()
            
            # Read data from source
            cursor_src.execute(f"SELECT * FROM {table_name}")
            columns = [desc[0] for desc in cursor_src.description]
            
            # Batch insert for large tables
            batch_size = 1000
            total_inserted = 0
            
            while True:
                rows = cursor_src.fetchmany(batch_size)
                if not rows:
                    break
                
                placeholders = ",".join(["?"] * len(columns))
                col_names = ",".join(columns)
                sql = f"INSERT OR IGNORE INTO {table_name} ({col_names}) VALUES ({placeholders})"
                
                conn_dst.executemany(sql, rows)
                conn_dst.commit()
                total_inserted += len(rows)
            
            print(f"[SQLite Merge] Inserted {total_inserted} rows into {table_name}")
        
        print(f"[SQLite Merge] Completed successfully")
        
    except Exception as e:
        print(f"[SQLite Merge] Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        conn_src.close()
        conn_dst.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
