from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from src.data_engine.fetcher import ConferenceDataFetcher
from src.data_engine.parser import PDFParser
from src.data_engine.storage import KnowledgeBase


class OpenReviewIngestor:
    """
    OpenReview -> 本地知识库 的一条龙入库管线：
    1) 拉取论文元数据（含评审/决策）
    2) 下载 PDF（可选）
    3) 解析 PDF 得到全文文本（可选）
    4) 写入 SQLite 元数据 + LanceDB 向量索引
    """

    def __init__(
        self,
        kb: KnowledgeBase,
        *,
        fetcher: Optional[ConferenceDataFetcher] = None,
        parser: Optional[PDFParser] = None,
    ) -> None:
        self.kb = kb
        self.fetcher = fetcher or ConferenceDataFetcher()
        self.parser = parser or PDFParser()

    def ingest_venue(
        self,
        *,
        venue_id: str,
        limit: Optional[int] = None,
        accepted_only: bool = False,
        presentation_in: Optional[List[str]] = None,
        skip_existing: bool = False,
        skip_paper_ids: Optional[set[str]] = None,
        download_pdfs: bool = True,
        parse_pdfs: bool = True,
        max_pdf_pages: Optional[int] = 12,
        max_downloads: Optional[int] = None,
        on_progress: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        # “追加抓取”模式：跳过已存在的论文 ID，直到凑够 limit 个新论文（或扫完）
        skip_ids = None
        if skip_existing:
            if isinstance(skip_paper_ids, set) and skip_paper_ids:
                skip_ids = skip_paper_ids
            else:
                try:
                    df = self.kb.search_structured()
                    if hasattr(df, "__len__") and (not df.empty) and ("id" in df.columns):  # type: ignore[attr-defined]
                        skip_ids = set([str(x) for x in df["id"].tolist() if str(x).strip()])
                except Exception:
                    skip_ids = None

        papers = self.fetcher.fetch_papers(
            venue_id,
            limit=limit,
            accepted_only=accepted_only,
            skip_paper_ids=skip_ids,
            on_progress=on_progress,
        )

        # 双重兜底：某些会议 decision 字段可能缺失/格式不同，这里再做一次过滤保证语义
        if accepted_only:
            kept = []
            for p in papers:
                d = str((p or {}).get("decision") or "").lower()
                if "accept" in d:
                    kept.append(p)
            papers = kept

        # 进一步过滤展示类型（oral/spotlight/poster/unknown）
        if accepted_only and isinstance(presentation_in, list) and presentation_in:
            allowed = set([str(x).strip().lower() for x in presentation_in if str(x).strip()])
            if allowed:
                kept = []
                for p in papers:
                    pres = str((p or {}).get("presentation") or "").strip().lower()
                    if pres in allowed:
                        kept.append(p)
                papers = kept

        # -------------------------------------------------------
        # Batch Processing: 下载 -> 解析 -> 入库 分批进行
        # 这样可以确保每处理完一批（如 20 篇）就写入数据库 (Checkpoint)，
        # 避免解析/Embedding 过程中断导致全部进度丢失（需要重跑）。
        # -------------------------------------------------------
        BATCH_SIZE = 20
        total_papers = len(papers)
        
        # 进度追踪状态
        progress_state = {
            "download_done": 0,
            "parse_done": 0,
            "embed_done": 0,
        }

        def _wrap_progress(stage_prefix, batch_current, batch_total, **kwargs):
            # 将 batch 内部的进度映射到全局进度
            # 注意：这里做简化的估算，主要为了 UI 不乱跳
            if not callable(on_progress):
                return
            
            # download_pdfs 会报 "downloading_pdfs"
            # parse 会报 "parse_pdf"
            # ingest 会报 "embed_papers", "embed_chunks" 等
            
            # 这里我们只透传 parse 和 embed 的关键事件，并修正 current/total
            stage = kwargs.get("stage", "")
            
            # 下载阶段通常很快，且内部自带全局进度（如果传了 task），这里暂不复杂化
            # 我们主要关注 User 提到的 "parse 重跑" 问题
            
            if stage == "parse_pdf":
                progress_state["parse_done"] += 1
                kwargs["current"] = progress_state["parse_done"]
                kwargs["total"] = total_papers
                on_progress(kwargs)
            
            elif stage.startswith("embed_") or stage.startswith("write_"):
                # Ingest 内部比较复杂，有多阶段。
                # 简单起见，我们让 ingest_data 里的 progress 直接透传，
                # 但需要用户测 app.py 能够处理（app.py 主要是显示 Log，进度条是 st.progress）
                # 由于 ingest_data 内部 current 是 batch 的 current，我们需要加上 offset
                # 但 ingest_data 内部很难注入 offset。
                # 考虑到 UI 主要看 Text Log，进度条跳变可以接受，或者我们在 batch loop 外面报大进度。
                on_progress(kwargs)
            else:
                 on_progress(kwargs)

        # 预先获取已入库 ID（用于断点续传）
        try:
            existing_ids_in_db = self.kb.get_paper_ids_with_content()
        except Exception:
            existing_ids_in_db = set()
            
        import math
        num_batches = math.ceil(total_papers / BATCH_SIZE)
        
        print(f"[Ingestor] Processing {total_papers} papers in {num_batches} batches (size={BATCH_SIZE})...")

        for i in range(0, total_papers, BATCH_SIZE):
            batch = papers[i : i + BATCH_SIZE]
            batch_idx = (i // BATCH_SIZE) + 1
            print(f"\n=== Processing Batch {batch_idx}/{num_batches} (Papers {i+1}~{min(i+BATCH_SIZE, total_papers)}) ===")

            # 1. 下载 (Batch)
            if download_pdfs:
                self.fetcher.download_pdfs(
                    batch, 
                    max_downloads=len(batch), 
                    on_progress=on_progress 
                )

            # 2. 解析 (Batch)
            if parse_pdfs:
                # 过滤出需要解析的
                parse_targets = []
                skipped_in_batch = 0
                for p in batch:
                    pid = str(p.get("id") or "")
                    if pid in existing_ids_in_db:
                        skipped_in_batch += 1
                        continue
                    if p.get("pdf_path") and os.path.exists(p.get("pdf_path")):
                        parse_targets.append(p)
                
                if skipped_in_batch > 0:
                    print(f"[Batch {batch_idx}] Skipping parsing for {skipped_in_batch} already indexed papers.")

                # 执行解析
                for p in parse_targets:
                    # 包装一下 progress
                    if callable(on_progress):
                        try:
                            # 模拟 trigger parse event
                            _wrap_progress(
                                "parse_pdf", 
                                0, 0, 
                                stage="parse_pdf", 
                                paper_id=p.get("id"),
                                title=p.get("title"),
                                pdf_path=p.get("pdf_path")
                            )
                        except Exception:
                            pass

                    pdf_path = p.get("pdf_path")
                    if pdf_path and os.path.exists(pdf_path):
                        p["content"] = self.parser.parse_pdf(pdf_path, max_pages=max_pdf_pages)
                
                # 修正全局计数（把跳过的也算进 done，保证进度条走完）
                progress_state["parse_done"] += skipped_in_batch

            # 3. 入库 (Batch) - 写入 DB
            # 只对真正需要处理的论文调用 ingest_data（完全跳过已索引的论文）
            papers_to_ingest = []
            for p in batch:
                pid = str(p.get("id") or "")
                if pid in existing_ids_in_db:
                    # 完全跳过已索引的论文（避免重复 chunking/embedding meta/review 等）
                    continue
                papers_to_ingest.append(p)
            
            if papers_to_ingest:
                print(f"[Batch {batch_idx}] Ingesting {len(papers_to_ingest)} new papers...")
                self.kb.ingest_data(papers_to_ingest, on_progress=on_progress)
            else:
                print(f"[Batch {batch_idx}] All {len(batch)} papers already indexed. Skipping ingest.")

        return papers


