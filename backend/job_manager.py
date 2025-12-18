import threading
import time
import traceback
import uuid
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from fastapi.encoders import jsonable_encoder

# Setup sys.path before importing from src
# This ensures the module can be imported both in dev mode and packaged mode
IS_PACKAGED = getattr(sys, 'frozen', False)

def _get_source_root() -> Path:
    if IS_PACKAGED and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    else:
        return Path(__file__).resolve().parent.parent / "source"

_source_root = _get_source_root()
if str(_source_root) not in sys.path:
    sys.path.insert(0, str(_source_root))

from src.utils.llm import get_llm_client
from src.data_engine.storage import KnowledgeBase
from src.data_engine.loader import DataLoader
from src.data_engine.fetcher import ConferenceDataFetcher
from src.data_engine.ingestor import OpenReviewIngestor
from src.planner.agent import PlannerAgent
from src.researcher.agent import ResearcherAgent
from src.writer.agent import WriterAgent
from src.verifier.agent import VerifierAgent
from src.utils.cancel import MujicaCancelled
from src.utils.chat_history import save_conversation

# Compute DATA_DIR the same way as app.py
def _get_data_dir() -> Path:
    if getattr(sys, 'frozen', False):
        # Packaged mode - use user directory
        if os.name == 'nt':
            user_config = Path(os.environ.get('APPDATA', os.path.expanduser('~'))) / 'MUJICA'
        else:
            user_config = Path.home() / '.mujica'
        return user_config / 'data'
    else:
        # Dev mode - use project directory
        return Path(__file__).resolve().parent.parent / 'data'

DATA_DIR = _get_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------
# Job Classes
# ---------------------------

@dataclass
class JobBase:
    job_id: str
    type: str  # plan, research, ingest
    cancel_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    status: str = "init"  # init, running, done, cancelled, error
    stage: str = "init"
    message: str = ""
    progress: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None
    error_trace: Optional[str] = None
    started_ts: float = field(default_factory=lambda: time.time())
    finished_ts: Optional[float] = None
    thread: Optional[threading.Thread] = None

    def to_dict(self):
        with self.lock:
            return {
                "job_id": self.job_id,
                "type": self.type,
                "status": self.status,
                "stage": self.stage,
                "message": self.message,
                "progress": self.progress,
                "result": self.result,
                "error": self.error,
                "started_ts": self.started_ts,
                "finished_ts": self.finished_ts,
            }

@dataclass
class PlanJob(JobBase):
    pass

@dataclass
class ResearchJob(JobBase):
    pass

@dataclass
class IngestJob(JobBase):
    pass

# ---------------------------
# Job Manager
# ---------------------------

class JobManager:
    def __init__(self):
        self.jobs: Dict[str, JobBase] = {}
        self._lock = threading.Lock()

    def create_job(self, job_type: str) -> JobBase:
        job_id = uuid.uuid4().hex
        if job_type == "plan":
            job = PlanJob(job_id=job_id, type="plan")
        elif job_type == "research":
            job = ResearchJob(job_id=job_id, type="research")
        elif job_type == "ingest":
            job = IngestJob(job_id=job_id, type="ingest")
        else:
            raise ValueError(f"Unknown job type: {job_type}")
        
        with self._lock:
            self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[JobBase]:
        with self._lock:
            return self.jobs.get(job_id)

    def cancel_job(self, job_id: str):
        job = self.get_job(job_id)
        if job:
            job.cancel_event.set()
            return True
        return False

# Global instance
manager = JobManager()

# ---------------------------
# Job Runners
# ---------------------------

def _job_update(job: JobBase, **kwargs: Any) -> None:
    with job.lock:
        for k, v in kwargs.items():
            setattr(job, k, v)
        # Update timestamp only if significant changes
        job.progress["_ts"] = time.time()

def _job_emit_progress(job: JobBase, *, kind: str, payload: Dict[str, Any]) -> None:
    with job.lock:
        job.progress[kind] = payload
        job.progress["_ts"] = time.time()

def run_plan_job(
    job: PlanJob,
    user_query: str,
    model_name: str,
    api_key: Optional[str],
    base_url: Optional[str],
    stats: Dict[str, Any] = None,
) -> None:
    try:
        print(f"[JobManager] Starting plan job {job.job_id}")
        print(f"[JobManager] Model: {model_name}, BaseURL: {base_url}")
        
        _job_update(job, status="running", stage="init", message="Initializing Planner...")
        
        # Fallback for placeholder model names (user misconfiguration)
        if "PLACEHOLDER" in model_name.upper():
            print(f"[JobManager] Warning: Detected placeholder model '{model_name}'. Falling back to 'deepseek-chat'.")
            model_name = "deepseek-chat"
            
        # Allow env fallback - frontend might send masked/empty API key
        if api_key:
            api_key = api_key.strip()
            
        llm = get_llm_client(api_key=api_key, base_url=base_url, allow_env_fallback=True)
        if llm is None:
            print("[JobManager] Failed to create LLM client")
            raise RuntimeError("Authentication Failed: missing/invalid API key.")
            
        print("[JobManager] LLM Client created. Initializing planner...")
        planner = PlannerAgent(llm, model=model_name)
        _job_update(job, stage="planning", message="Generating Plan...")
        
        print("[JobManager] Calling planner.generate_plan...")
        plan = planner.generate_plan(user_query, stats or {}, cancel_event=job.cancel_event)
        print("[JobManager] Plan generated successfully")
        
        _job_update(job, result={"plan": plan}, status="done", stage="done", message="Planning Complete ✅", finished_ts=time.time())
    except MujicaCancelled as e:
        print(f"[JobManager] Cancelled: {e}")
        _job_update(job, status="cancelled", stage="cancelled", message="Planning Cancelled", error=str(e), finished_ts=time.time())
    except Exception as e:
        print(f"[JobManager] Error: {e}")
        import traceback
        traceback.print_exc()
        _job_update(job, status="error", stage="error", message="Planning Failed ❌", error=str(e), error_trace=traceback.format_exc(), finished_ts=time.time())

def run_research_job(
    job: ResearchJob,
    plan: Dict[str, Any],
    model_name: str,
    chat_api_key: Optional[str],
    chat_base_url: Optional[str],
    embedding_model: str,
    embedding_api_key: Optional[str],
    embedding_base_url: Optional[str],
) -> None:
    try:
        _job_update(job, status="running", stage="init", message="Initializing Research Agents...")

        # Fallback for placeholder model names
        if "PLACEHOLDER" in model_name.upper():
            print(f"[JobManager] Warning: Detected placeholder model '{model_name}'. Falling back to 'deepseek-chat'.")
            model_name = "deepseek-chat"

        kb = KnowledgeBase(
            db_path=str(DATA_DIR / "lancedb"),
            embedding_model=embedding_model,
            embedding_api_key=embedding_api_key,
            embedding_base_url=embedding_base_url,
        )
        kb.initialize_db()

        llm = get_llm_client(api_key=chat_api_key, base_url=chat_base_url, allow_env_fallback=False)
        if llm is None:
            raise RuntimeError("Authentication Failed: missing/invalid API key.")

        researcher = ResearcherAgent(kb, llm, model=model_name)
        writer = WriterAgent(llm, model=model_name)
        verifier = VerifierAgent(llm, model=model_name)

        # Research
        _job_update(job, stage="research", message="Researching...")
        
        def _on_research_progress(payload: Dict[str, Any]) -> None:
            if not isinstance(payload, dict): return
            _job_emit_progress(job, kind="research", payload=payload)
            stg = payload.get("stage")
            if stg == "research_section":
                _job_update(job, message=f"Researching: {payload.get('section')}")

        notes = researcher.execute_research(plan, on_progress=_on_research_progress, cancel_event=job.cancel_event)
        _job_update(job, result={"research_notes": notes})

        # Write
        _job_update(job, stage="write", message="Writing Report...")
        
        def _on_write_progress(payload: Dict[str, Any]) -> None:
            if not isinstance(payload, dict): return
            _job_emit_progress(job, kind="write", payload=payload)
            if payload.get("stage") == "write_llm_call":
                _job_update(job, message="Generating content with LLM...")

        report, ref_ctx = writer.write_report(plan, notes, on_progress=_on_write_progress, cancel_event=job.cancel_event)
        
        # Verify
        _job_update(job, stage="verify", message="Verifying Report...")
        chunk_map = {}
        for n in notes:
            for e in (n.get("evidence") or []):
                chunk_map[e.get("chunk_id")] = e.get("text")
        
        verification = verifier.verify_report(report, {"chunks": chunk_map, "ref_map": ref_ctx.get("ref_map", {})}, cancel_event=job.cancel_event)

        _job_update(job, result={
            "research_notes": notes,
            "final_report": report,
            "report_ref_ctx": ref_ctx,
            "verification_result": verification
        }, status="done", stage="done", message="All Done ✅", finished_ts=time.time())

        # Save to History
        try:
            snapshot = {
                "title": plan.get("title", "Research Report"),
                "created_ts": time.time(),
                "messages": [
                    {"role": "user", "content": str(plan.get("title") or "Research Task")},
                    {"role": "assistant", "content": report}
                ],
                # Save full result for detailed re-rendering
                "job_result": {
                     "final_report": report,
                     "verification_result": verification,
                     "research_notes": notes,
                     "report_ref_ctx": ref_ctx
                }
            }
            save_conversation(job.job_id, jsonable_encoder(snapshot))
        except Exception as history_error:
            print(f"[JobManager] Failed to save history: {history_error}")
            try:
                from backend.debug_tools import log_exception, log_debug
                log_debug(f"Verification result type: {type(verification)}")
                log_debug(f"Verification keys: {verification.keys() if isinstance(verification, dict) else 'Not Dict'}")
                log_exception(history_error, "save_conversation")
            except:
                pass

    except MujicaCancelled as e:
        _job_update(job, status="cancelled", stage="cancelled", message="Cancelled", error=str(e), finished_ts=time.time())
    except Exception as e:
        _job_update(job, status="error", stage="error", message="Failed ❌", error=str(e), error_trace=traceback.format_exc(), finished_ts=time.time())

def run_ingest_job(
    job: IngestJob,
    venue_id: str,
    limit: Optional[int],
    accepted_only: bool,
    presentation_in: Optional[List[str]],
    skip_existing: bool,
    download_pdfs: bool,
    parse_pdfs: bool,
    max_pdf_pages: Optional[int],
    max_downloads: Optional[int],
    embedding_model: str,
    embedding_api_key: Optional[str],
    embedding_base_url: Optional[str],
) -> None:
    try:
        _job_update(job, status="running", stage="ingest", message="Ingesting Data...")
        
        kb = KnowledgeBase(
            db_path=str(DATA_DIR / "lancedb"),
            embedding_model=embedding_model,
            embedding_api_key=embedding_api_key,
            embedding_base_url=embedding_base_url,
        )
        kb.initialize_db()
        ingestor = OpenReviewIngestor(kb, fetcher=ConferenceDataFetcher(output_dir=str(DATA_DIR / "raw")))

        def _on_progress(payload: Dict[str, Any]) -> None:
            if job.cancel_event.is_set():
                raise MujicaCancelled("User Cancelled")
            
            stage = payload.get("stage", "unknown")
            cur = payload.get("current", 0)
            tot = payload.get("total", 0)
            
            # Map embed_papers/embed_chunks to unified "embedding" stage for frontend
            if stage in ("embed_papers", "embed_chunks"):
                # Emit both as "embedding" stage so frontend progress bar picks it up
                _job_emit_progress(job, kind="embedding", payload={
                    "stage": "embedding",
                    "current": cur,
                    "total": tot,
                    "sub_stage": stage,
                    **{k: v for k, v in payload.items() if k not in ("stage", "current", "total")}
                })
                _job_update(job, message=f"Embedding {cur}/{tot}")
            elif stage == "prepare_chunks":
                _job_emit_progress(job, kind="chunking", payload=payload)
                _job_update(job, message=f"Chunking {cur}/{tot}")
            else:
                _job_emit_progress(job, kind=stage, payload=payload)
                # Update message based on stage
                if stage == "fetch_papers":
                    _job_update(job, message=f"Fetching Meta {cur}/{tot}")
                elif stage == "download_pdf":
                    _job_update(job, message=f"Downloading PDF {cur}/{tot}")
                elif stage == "parse_pdf":
                    _job_update(job, message=f"Parsing PDF {cur}/{tot}")

        papers = ingestor.ingest_venue(
            venue_id=venue_id,
            limit=limit,
            accepted_only=accepted_only,
            presentation_in=presentation_in,
            skip_existing=skip_existing,
            download_pdfs=download_pdfs,
            parse_pdfs=parse_pdfs,
            max_pdf_pages=max_pdf_pages,
            max_downloads=max_downloads,
            on_progress=_on_progress,
        )

        _job_update(job, status="done", stage="done", message=f"Ingest Complete: {len(papers)} papers", result=papers, finished_ts=time.time())
    except MujicaCancelled as e:
        _job_update(job, status="cancelled", stage="cancelled", message="Ingest Cancelled", error=str(e), finished_ts=time.time())
    except Exception as e:
        _job_update(job, status="error", stage="error", message="Ingest Failed ❌", error=str(e), error_trace=traceback.format_exc(), finished_ts=time.time())
