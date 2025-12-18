from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from src.data_engine.storage import KnowledgeBase
from src.utils.cancel import MujicaCancelled, check_cancel
from src.utils.json_utils import extract_json_object


def _env_truthy(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


class ResearcherAgent:
    def __init__(self, kb: KnowledgeBase, llm_client, model: str = "gpt-4o"):
        self.kb = kb
        self.llm = llm_client
        self.model = model

    def _apply_filters(self, df: pd.DataFrame, filters: Dict[str, Any]) -> pd.DataFrame:
        if df is None or df.empty or not filters:
            return df

        out = df.copy()

        # ---------------------------
        # 文本/元数据过滤（标题/作者/关键词/venue）
        # ---------------------------
        title_contains = (filters.get("title_contains") or "").strip()
        if title_contains and "title" in out.columns:
            out = out[out["title"].fillna("").astype(str).str.contains(title_contains, case=False, regex=False)]

        venue_contains = (filters.get("venue_contains") or "").strip()
        if venue_contains and "venue_id" in out.columns:
            out = out[out["venue_id"].fillna("").astype(str).str.contains(venue_contains, case=False, regex=False)]

        author_contains = (filters.get("author_contains") or "").strip()
        if author_contains:
            if "authors_text" in out.columns:
                out = out[out["authors_text"].fillna("").astype(str).str.contains(author_contains, case=False, regex=False)]
            elif "authors_json" in out.columns:
                out = out[out["authors_json"].fillna("").astype(str).str.contains(author_contains, case=False, regex=False)]

        keyword_contains = (filters.get("keyword_contains") or "").strip()
        if keyword_contains:
            if "keywords_text" in out.columns:
                out = out[out["keywords_text"].fillna("").astype(str).str.contains(keyword_contains, case=False, regex=False)]
            elif "keywords_json" in out.columns:
                out = out[out["keywords_json"].fillna("").astype(str).str.contains(keyword_contains, case=False, regex=False)]

        min_rating = filters.get("min_rating", None)
        if isinstance(min_rating, (int, float)):
            out = out[out["rating"].notna() & (out["rating"] >= float(min_rating))]

        min_year = filters.get("min_year", None)
        if isinstance(min_year, int) and "year" in out.columns:
            out = out[out["year"].notna() & (out["year"] >= int(min_year))]

        max_year = filters.get("max_year", None)
        if isinstance(max_year, int) and "year" in out.columns:
            out = out[out["year"].notna() & (out["year"] <= int(max_year))]

        year_in = filters.get("year_in", None)
        if isinstance(year_in, list) and year_in:
            out = out[out["year"].isin(year_in)]

        decision_in = filters.get("decision_in", None)
        if isinstance(decision_in, list) and decision_in:
            # decision 可能为空；使用模糊匹配 (Accept 匹配 Accept (poster))
            mask = pd.Series([False] * len(out), index=out.index)
            for d_val in decision_in:
                if d_val:
                    mask |= out["decision"].fillna("").astype(str).str.contains(d_val, case=False, regex=False)
            out = out[mask]

        presentation_in = filters.get("presentation_in", None)
        if isinstance(presentation_in, list) and presentation_in and "presentation" in out.columns:
            mask = pd.Series([False] * len(out), index=out.index)
            for p_val in presentation_in:
                if p_val:
                     mask |= out["presentation"].fillna("").astype(str).str.contains(p_val, case=False, regex=False)
            out = out[mask]

        return out

    def execute_research(
        self,
        plan: Dict[str, Any],
        *,
        on_progress: Optional[Any] = None,
        cancel_event: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        执行研究：结构化过滤 + 语义检索（chunk）+ 生成可追溯研究笔记（含证据片段）。
        """
        t_all = time.time()
        check_cancel(cancel_event, stage="research_start")
        print("[Research] starting research phase...")
        research_notes: List[Dict[str, Any]] = []

        metadata_df = self.kb.search_structured()
        global_filters = plan.get("global_filters") or {}
        default_top_papers = int(plan.get("estimated_papers") or 10)
        default_top_papers = max(5, min(default_top_papers, 20))

        sections = plan.get("sections", []) or []
        if not isinstance(sections, list):
            sections = []
        total_sections = len(sections)
        print(f"[Research] sections={total_sections} default_top_papers={default_top_papers}")

        for si, section in enumerate(sections):
            t_sec = time.time()
            section_name = section.get("name") or "Section"
            query = section.get("search_query") or ""
            print(f"[Research] ({si+1}/{total_sections}) section={section_name} query={query!r}")
            check_cancel(cancel_event, stage=f"research_section:{section_name}")

            if callable(on_progress):
                try:
                    on_progress(
                        {
                            "stage": "research_section",
                            "current": si + 1,
                            "total": total_sections,
                            "section": section_name,
                            "query": query,
                        }
                    )
                except Exception:
                    pass

            section_filters = dict(global_filters)
            section_filters.update(section.get("filters") or {})
            if section_filters:
                try:
                    print(f"[Research] filters={json.dumps(section_filters, ensure_ascii=False)}")
                except Exception:
                    print("[Research] filters=<unprintable>")

            top_k_papers = int(section.get("top_k_papers") or default_top_papers)
            top_k_papers = max(3, min(top_k_papers, 20))

            top_k_chunks = int(section.get("top_k_chunks") or max(top_k_papers * 4, 40))
            top_k_chunks = max(20, min(top_k_chunks, 120))

            # 1) structured filtering -> 候选 paper_id 集合
            allowed_paper_ids: Optional[set[str]] = None
            allowed_papers_count: Optional[int] = None
            if isinstance(metadata_df, pd.DataFrame) and not metadata_df.empty and section_filters:
                check_cancel(cancel_event, stage=f"structured_filter:{section_name}")
                t_f = time.time()
                filtered = self._apply_filters(metadata_df, section_filters)
                allowed_paper_ids = set(filtered["id"].tolist())
                allowed_papers_count = len(allowed_paper_ids)
                print(
                    f"[Research] structured_filter: papers {len(metadata_df)} -> {allowed_papers_count} (dt={time.time()-t_f:.2f}s)"
                )
            else:
                if isinstance(metadata_df, pd.DataFrame):
                    allowed_papers_count = int(len(metadata_df))
                print("[Research] structured_filter: skipped (no filters or empty metadata)")

            # 2) chunk-level retrieval
            check_cancel(cancel_event, stage=f"chunk_retrieval:{section_name}")
            t_r = time.time()
            chunk_hits = self.kb.search_chunks(query, limit=top_k_chunks)
            dt_r = time.time() - t_r
            raw_hits = len(chunk_hits)
            if allowed_paper_ids is not None:
                chunk_hits = [h for h in chunk_hits if h.get("paper_id") in allowed_paper_ids]
            after_hits = len(chunk_hits)

            if not chunk_hits:
                print(
                    f"[Research] retrieval: hits={raw_hits} filtered_hits={after_hits} dt={dt_r:.2f}s -> no evidence"
                )
                research_notes.append(
                    {
                        "section": section_name,
                        "query": query,
                        "content": "未检索到足够证据（可能尚未入库/未生成向量/过滤条件过严）。",
                        "sources": [],
                        "evidence": [],
                        "filters": section_filters,
                    }
                )
                continue

            # 3) 选 Top-N papers，并为每篇 paper 取前若干 chunks 作为证据
            by_paper: Dict[str, List[Dict[str, Any]]] = {}
            for h in chunk_hits:
                check_cancel(cancel_event, stage=f"group_hits:{section_name}")
                pid = h.get("paper_id")
                if not pid:
                    continue
                by_paper.setdefault(pid, []).append(h)
            uniq_papers = len(by_paper)

            # 按最优距离排序 papers
            paper_ranked = sorted(
                by_paper.items(),
                key=lambda kv: min([x.get("_distance", 1e9) for x in kv[1]]),
            )[:top_k_papers]
            print(
                f"[Research] retrieval: hits={raw_hits} filtered_hits={after_hits} unique_papers={uniq_papers} "
                f"select_papers={len(paper_ranked)} top_k_chunks={top_k_chunks} (dt={dt_r:.2f}s)"
            )

            evidence: List[Dict[str, Any]] = []
            source_ids: List[str] = []
            chunks_per_paper = 2
            try:
                review_chunks_per_paper = int(os.getenv("MUJICA_EVIDENCE_REVIEW_CHUNKS_PER_PAPER", "1") or 1)
            except Exception:
                review_chunks_per_paper = 1
            review_chunks_per_paper = max(0, min(review_chunks_per_paper, 5))

            # 决策/作者回应：按需补充（默认各 1 条，可用 env 设为 0 关闭）
            try:
                decision_chunks_per_paper = int(os.getenv("MUJICA_EVIDENCE_DECISION_CHUNKS_PER_PAPER", "1") or 1)
            except Exception:
                decision_chunks_per_paper = 1
            decision_chunks_per_paper = max(0, min(decision_chunks_per_paper, 3))

            try:
                rebuttal_chunks_per_paper = int(os.getenv("MUJICA_EVIDENCE_REBUTTAL_CHUNKS_PER_PAPER", "1") or 1)
            except Exception:
                rebuttal_chunks_per_paper = 1
            rebuttal_chunks_per_paper = max(0, min(rebuttal_chunks_per_paper, 3))
            for pid, hits in paper_ranked:
                check_cancel(cancel_event, stage=f"collect_evidence:{section_name}")
                source_ids.append(pid)
                # 3.1) 强制补充 meta chunk（用于引用作者/关键词/评分/决策/年份等元信息）
                meta_chunk_id = f"{pid}::meta::0"
                paper_meta = self.kb.get_paper(pid) or {}
                paper_title = paper_meta.get("title") or (hits[0].get("title") if hits else "") or ""

                try:
                    meta_chunk = self.kb.get_chunk_by_id(meta_chunk_id)
                except Exception:
                    meta_chunk = None

                if isinstance(meta_chunk, dict) and (meta_chunk.get("text") or "").strip():
                    evidence.append(
                        {
                            "paper_id": pid,
                            "title": paper_title,
                            "chunk_id": meta_chunk_id,
                            "source": "meta",
                            "chunk_index": int(meta_chunk.get("chunk_index") or 0),
                            "text": (meta_chunk.get("text") or "")[:900],
                            "rating": paper_meta.get("rating"),
                            "decision": paper_meta.get("decision"),
                            "_distance": None,
                        }
                    )

                # 3.1a) 决策说明 chunk（如果存在）
                if decision_chunks_per_paper > 0:
                    for didx in range(decision_chunks_per_paper):
                        check_cancel(cancel_event, stage=f"collect_decision:{section_name}")
                        decision_chunk_id = f"{pid}::decision::{didx}"
                        try:
                            dc = self.kb.get_chunk_by_id(decision_chunk_id)
                        except Exception:
                            dc = None
                        if isinstance(dc, dict) and (dc.get("text") or "").strip():
                            evidence.append(
                                {
                                    "paper_id": pid,
                                    "title": paper_title,
                                    "chunk_id": decision_chunk_id,
                                    "source": dc.get("source") or "decision",
                                    "chunk_index": int(dc.get("chunk_index") or didx),
                                    "text": (dc.get("text") or "")[:1200],
                                    "rating": paper_meta.get("rating"),
                                    "decision": paper_meta.get("decision"),
                                    "_distance": None,
                                }
                            )
                            break

                # 3.1b) 作者 rebuttal/response chunk（如果存在）
                if rebuttal_chunks_per_paper > 0:
                    for ridx in range(rebuttal_chunks_per_paper):
                        check_cancel(cancel_event, stage=f"collect_rebuttal:{section_name}")
                        rebuttal_chunk_id = f"{pid}::rebuttal::{ridx}"
                        try:
                            rc = self.kb.get_chunk_by_id(rebuttal_chunk_id)
                        except Exception:
                            rc = None
                        if isinstance(rc, dict) and (rc.get("text") or "").strip():
                            evidence.append(
                                {
                                    "paper_id": pid,
                                    "title": paper_title,
                                    "chunk_id": rebuttal_chunk_id,
                                    "source": rc.get("source") or "rebuttal",
                                    "chunk_index": int(rc.get("chunk_index") or ridx),
                                    "text": (rc.get("text") or "")[:1200],
                                    "rating": paper_meta.get("rating"),
                                    "decision": paper_meta.get("decision"),
                                    "_distance": None,
                                }
                            )
                            break

                # 3.1b) 额外补充 review chunks（让“评审关注点/意见”分析更有证据；可用 env 关闭）
                if review_chunks_per_paper > 0:
                    try:
                        reviews_rows = self.kb.get_reviews(pid)
                    except Exception:
                        reviews_rows = []
                    if isinstance(reviews_rows, list) and reviews_rows:
                        for ridx in range(min(len(reviews_rows), review_chunks_per_paper)):
                            check_cancel(cancel_event, stage=f"collect_reviews:{section_name}")
                            review_chunk_id = f"{pid}::review_{ridx}::0"
                            try:
                                rc = self.kb.get_chunk_by_id(review_chunk_id)
                            except Exception:
                                rc = None
                            if isinstance(rc, dict) and (rc.get("text") or "").strip():
                                evidence.append(
                                    {
                                        "paper_id": pid,
                                        "title": paper_title,
                                        "chunk_id": review_chunk_id,
                                        "source": rc.get("source") or f"review_{ridx}",
                                        "chunk_index": int(rc.get("chunk_index") or 0),
                                        "text": (rc.get("text") or "")[:1200],
                                        "rating": paper_meta.get("rating"),
                                        "decision": paper_meta.get("decision"),
                                        "_distance": None,
                                    }
                                )

                # 3.2) 再取内容相关 chunks（排除 meta，避免重复）
                hits_sorted_all = sorted(hits, key=lambda x: x.get("_distance", 1e9))
                content_hits = [h for h in hits_sorted_all if h.get("source") != "meta"][:chunks_per_paper]
                for hh in content_hits:
                    check_cancel(cancel_event, stage=f"collect_content:{section_name}")
                    evidence.append(
                        {
                            "paper_id": pid,
                            "title": hh.get("title", "") or paper_title,
                            "chunk_id": hh.get("chunk_id"),
                            "source": hh.get("source"),
                            "chunk_index": hh.get("chunk_index"),
                            "text": (hh.get("text") or "")[:1400],
                            "rating": hh.get("rating"),
                            "decision": hh.get("decision"),
                            "_distance": hh.get("_distance"),
                        }
                    )

            # 4) LLM：基于证据生成“中间态笔记”
            #    - 让模型输出 JSON，便于后续 writer/verifier 使用
            print(
                f"[Research] evidence: papers={len(source_ids)} snippets={len(evidence)} "
                f"(meta+content, chunks_per_paper={chunks_per_paper})"
            )
            evidence_text = ""
            for e in evidence:
                check_cancel(cancel_event, stage=f"build_prompt:{section_name}")
                evidence_text += (
                    f"\n[Paper ID: {e['paper_id']} | Chunk: {e['chunk_id']} | Source: {e['source']}]\n"
                    f"Title: {e['title']}\n"
                    f"Snippet: {e['text']}\n"
                )

            system_prompt = (
                "你是 MUJICA 的 Researcher（中文输出）。"
                "只能基于给定的 Evidence Snippets 写研究笔记；不允许编造。"
                "请尽量利用证据中的元信息（例如 source=meta 里的作者/关键词/年份/评分/决策）进行综合分析，深入研究，提出有创新性深刻性的观点。"
                "如果证据不足，请明确说明未知/证据缺失。"
            )
            user_prompt = f"""
任务：为报告章节「{section_name}」撰写研究笔记（中间态）。
章节检索词：{query}
结构化过滤条件：{json.dumps(section_filters, ensure_ascii=False)}

Evidence Snippets（可引用 chunk_id 以便溯源）：
{evidence_text}

请返回 JSON：
{{
  "summary": "<本章节的核心发现，500-800字>",
  "key_points": [
    {{"point": "<要点>", "citations": [{{"paper_id": "...", "chunk_id": "..."}}]}}
  ]
}}
"""

            summary_content = ""
            key_points: List[Dict[str, Any]] = []
            try:
                t_llm = time.time()
                check_cancel(cancel_event, stage=f"llm_summarise_before:{section_name}")
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]

                # 优先 JSON mode；不支持时（如部分 GLM）退化为普通输出 + 提取 JSON
                # DeepSeek 等模型建议禁用 JSON Mode
                is_deepseek = "deepseek" in self.model.lower()
                try:
                    if _env_truthy("MUJICA_DISABLE_JSON_MODE") or is_deepseek:
                        raise RuntimeError("json_mode_disabled")
                    response = self.llm.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        response_format={"type": "json_object"},
                        timeout=120.0,
                        stream=False,
                    )
                    parsed = json.loads(response.choices[0].message.content or "{}")
                except Exception as e:
                    if str(e) != "json_mode_disabled":
                        print(f"Researcher json_mode failed: {e} (fallback to plain JSON)")
                    response = self.llm.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        timeout=120.0,
                        stream=False,
                    )
                    parsed = extract_json_object(response.choices[0].message.content or "")
                check_cancel(cancel_event, stage=f"llm_summarise_after:{section_name}")
                summary_content = parsed.get("summary", "") or ""
                key_points = parsed.get("key_points", []) or []
                print(
                    f"[Research] summarise: dt={time.time()-t_llm:.2f}s summary_len={len(summary_content)} key_points={len(key_points)}"
                )
            except MujicaCancelled:
                raise
            except Exception as e:
                print(f"Error summarising: {e}")
                summary_content = "研究笔记生成失败（LLM 调用/JSON 解析异常）。"

            if callable(on_progress):
                try:
                    on_progress(
                        {
                            "stage": "research_section_done",
                            "current": si + 1,
                            "total": total_sections,
                            "section": section_name,
                            "query": query,
                            "allowed_papers": allowed_papers_count,
                            "hits": raw_hits,
                            "hits_after_filter": after_hits,
                            "selected_papers": len(source_ids),
                            "evidence": len(evidence),
                            "elapsed": time.time() - t_sec,
                        }
                    )
                except Exception:
                    pass

            research_notes.append(
                {
                    "section": section_name,
                    "query": query,
                    "content": summary_content,
                    "key_points": key_points,
                    "sources": source_ids,
                    "evidence": evidence,
                    "filters": section_filters,
                }
            )

            print(f"[Research] section done: {section_name} dt={time.time()-t_sec:.2f}s")

        print(f"[Research] completed: sections={len(research_notes)} elapsed={time.time()-t_all:.2f}s")
        return research_notes
