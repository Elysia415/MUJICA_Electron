from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from typing import Any, Dict, List, Tuple, Optional

from src.utils.cancel import MujicaCancelled, check_cancel


class WriterAgent:
    def __init__(self, llm_client, model: str = "gpt-4o"):
        self.llm = llm_client
        self.model = model

    _REF_RE = re.compile(r"\[((?:R\d+\s*[,，、]\s*)*R\d+)\]")
    _SENT_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s+")

    def _build_ref_catalog(self, research_notes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        为所有 evidence chunk 分配稳定的 Ref ID（R1/R2/...）。

        目标：
        - 报告正文只出现 [R#]（对人友好、避免 paper_id 乱码/冗长）
        - References 小节由我们自动生成（标题+来源+片段+snippet）
        - Verifier 用 ref_map 把 [R#] 映射回 chunk_id 再做核查
        """
        ref_items: List[Dict[str, Any]] = []
        chunk_to_ref: Dict[str, str] = {}

        for note in research_notes or []:
            for e in (note.get("evidence") or []):
                cid = str(e.get("chunk_id") or "").strip()
                if not cid:
                    continue
                if cid in chunk_to_ref:
                    continue

                ref_id = f"R{len(ref_items) + 1}"
                chunk_to_ref[cid] = ref_id

                ref_items.append(
                    {
                        "ref": ref_id,
                        "paper_id": e.get("paper_id"),
                        "title": e.get("title") or "",
                        "chunk_id": cid,
                        "source": e.get("source") or "",
                        "chunk_index": e.get("chunk_index"),
                        "text": e.get("text") or "",
                    }
                )

        ref_map = {it["ref"]: it["chunk_id"] for it in ref_items}
        return {"ref_items": ref_items, "chunk_to_ref": chunk_to_ref, "ref_map": ref_map}

    def _render_references(self, report_text: str, ref_items: List[Dict[str, Any]]) -> str:
        """
        解析正文中的 [R1], [R1, R2] 等格式，生成去重的 References 列表。
        """
        used_refs: List[str] = []
        seen = set()
        
        # 解析所有引用
        matches = self._REF_RE.findall(report_text or "")
        for group in matches:
            # group 可能是 "R1" 或 "R1, R2"
            # Split by common separators
            single_refs = re.split(r"[,，、]\s*", group)
            for r in single_refs:
                r = r.strip()
                if not r or r in seen:
                    continue
                seen.add(r)
                used_refs.append(r)

        # Sort refs numerically (R1, R2, R10...) not lexically (R1, R10, R2)
        try:
            used_refs.sort(key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
        except Exception:
            used_refs.sort()

        if not used_refs:
            return ""

        by_ref = {it.get("ref"): it for it in (ref_items or []) if it.get("ref")}

        def _source_label(src: str) -> str:
            s = (src or "").strip()
            if s.startswith("review_"):
                try:
                    # review_0 => 评审 #1（对用户更直观）
                    idx = int(s.split("_", 1)[1])
                    return f"评审 #{idx + 1}"
                except Exception:
                    return "评审"
            return {
                "meta": "元信息",
                "title_abstract": "标题+摘要",
                "tldr": "TL;DR",
                "full_text": "正文",
                "decision": "最终决策说明",
                "rebuttal": "作者 Rebuttal/Response",
            }.get(s, s or "unknown")

        lines = ["", "### 参考文献", ""]
        for rid in used_refs:
            it = by_ref.get(rid) or {}
            title = (it.get("title") or "").strip() or "（无标题）"
            src = _source_label(str(it.get("source") or ""))
            cidx = it.get("chunk_index")
            try:
                cidx_disp = int(cidx) if cidx is not None else None
            except Exception:
                cidx_disp = None

            snippet = (it.get("text") or "").strip()
            snippet = re.sub(r"\s+", " ", snippet)
            # 增加一点长度限制，防止展示太少。但也不要太长。
            if len(snippet) > 300:
                snippet = snippet[:300].rstrip() + "…"

            loc = f"{src}" + (f" · 片段 {cidx_disp}" if cidx_disp is not None else "")
            # 展示 Ref ID，并在列表中使用 Markdown 格式
            lines.append(f"- **[{rid}]《{title}》**：{loc}\n  > {snippet}")

        return "\n".join(lines).rstrip() + "\n"

    def write_report(
        self,
        plan: Dict[str, Any],
        research_notes: List[Dict[str, Any]],
        *,
        on_progress: Any = None,
        cancel_event: Optional[Any] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        循证写作：严格基于 research_notes.evidence 生成 Markdown 报告。
        - 句级引用：使用 Ref ID（对人友好）：[R1] [R2] ...
        - 参考文献（References）由系统自动补全：标题 + 来源类型 + 片段 + snippet
        """
        print("Writing final report...")
        check_cancel(cancel_event, stage="write_start")

        title = plan.get("title", "Research Report")

        def _emit(stage: str, **payload):  # noqa: ANN001
            if callable(on_progress):
                try:
                    on_progress({"stage": stage, **payload})
                except Exception:
                    pass

        t_all = time.time()
        _emit("write_start", title=title)
        check_cancel(cancel_event, stage="write_build_refs")
        ref_ctx = self._build_ref_catalog(research_notes)
        ref_items = ref_ctx.get("ref_items") or []
        chunk_to_ref = ref_ctx.get("chunk_to_ref") or {}
        _emit("write_refs_built", refs_total=len(ref_items))

        sections_payload = []
        evidence_total = 0
        for note in research_notes:
            check_cancel(cancel_event, stage="write_build_payload")
            evidence = note.get("evidence") or []
            evidence_total += len(evidence)

            # 将 key_points 的 citations（paper_id/chunk_id）映射为 refs（R#）
            key_points_out = []
            for kp in (note.get("key_points") or []):
                if not isinstance(kp, dict):
                    continue
                refs = []
                for cit in (kp.get("citations") or []):
                    if not isinstance(cit, dict):
                        continue
                    cid = str(cit.get("chunk_id") or "").strip()
                    rid = chunk_to_ref.get(cid)
                    if rid and rid not in refs:
                        refs.append(rid)
                key_points_out.append({"point": kp.get("point"), "refs": refs})

            allowed_refs = []
            for e in evidence:
                cid = str(e.get("chunk_id") or "").strip()
                rid = chunk_to_ref.get(cid)
                if rid and rid not in allowed_refs:
                    allowed_refs.append(rid)
            sections_payload.append(
                {
                    "section": note.get("section"),
                    "query": note.get("query"),
                    "summary": note.get("content"),
                    "key_points": key_points_out,
                    "evidence": [
                        {
                            "ref": chunk_to_ref.get(str(e.get("chunk_id") or "").strip()),
                            "paper_id": e.get("paper_id"),
                            "title": e.get("title"),
                            "year": e.get("year"),
                            "rating": e.get("rating"),
                            "decision": e.get("decision"),
                            "presentation": e.get("presentation"),
                            "chunk_id": e.get("chunk_id"),
                            "source": e.get("source"),
                            "chunk_index": e.get("chunk_index"),
                            "text": e.get("text"),
                        }
                        for e in evidence
                    ],
                    "allowed_refs": allowed_refs,
                }
            )
        _emit(
            "write_payload_built",
            sections=len(sections_payload),
            evidence_snippets=evidence_total,
            allowed_refs_total=len(ref_items),
        )
        check_cancel(cancel_event, stage="write_before_llm")

        system_prompt = """
你是 MUJICA 的 Writer（循证写作专家，中文输出）。
你的目标：基于提供的研究笔记与 Evidence Snippets，撰写一篇**深度、连贯、长篇**的学术综述报告。

严格规则（必须遵守）：
1) 【排版格式 - 关键】**必须使用标准的 Markdown 标题语法**（如 `## 核心发现`、`### 创新性分析`）来区分章节。**绝对禁止**使用加粗（如 `**1. 核心发现**`）来代替标题。
2) 【循证原则 - 防幻觉】**严格基于提供的证据（Evidence）**进行写作。
   - 每一个事实性陈述必须附上 Ref ID，如 [R1]。
   - 如果证据中没有提及某事，**绝对不要编造**。
   - 不要为了通顺而添加证据中不存在的细节。
3) 【引用规范】引用必须使用 [R#] 格式。禁止出现 paper_id/chunk_id。禁止生成 References 小节（系统会自动补全）。
4) 【篇幅与深度】拒绝简短的总结。请深入分析证据细节，逻辑要连贯。整篇报告应像一篇高质量的 Survey Paper。
5) 【禁止开场白】直接输出报告正文，禁止任何"好的，我将..."、"请注意..."、"以下是..."等开头语。报告第一行必须是标题（# 标题）。

写作风格要求：
6) 【连贯性】不要机械地堆砌“本章节结论概述”。请将各个章节的内容有机融合，使用流畅的过渡句。
7) 【结构化】文章应包含引言（背景与目标）、核心发现（分类讨论）、详细案例分析、以及结论。确保层级分明（使用 ## 和 ###）。
8) 【适度洞察】在对比分析时，应基于证据提供的线索进行合理推断，**避免无中生有的过度臆测**。分析评审逻辑时，引用具体的评审意见作为支撑。
9) 【证据细节】在论述关键观点时，请直接引用证据中的具体措辞或案例（配合 [R#]），增强说服力。引用应具体到“根据评审 R1 所述...[R1]”。

目标字数：如果证据充足，请尽量写出一篇详尽的报告（2000字以上），能够作为该领域的深度参考资料。
"""

        user_prompt = f"""
Report Title: {title}

Sections (JSON):
{json.dumps(sections_payload, ensure_ascii=False)}

请生成完整 Markdown 报告。
"""

        try:
            prompt_chars = len(system_prompt) + len(user_prompt)
            _emit("write_llm_call", model=self.model, prompt_chars=prompt_chars, refs_total=len(ref_items))
            t_llm = time.time()

            # max_tokens：允许输出更长的报告；可用 MUJICA_WRITER_MAX_TOKENS 控制
            llm_kwargs: Dict[str, Any] = {}
            try:
                max_tokens = int(os.getenv("MUJICA_WRITER_MAX_TOKENS", "4096") or 4096)
            except Exception:
                max_tokens = 4096
            max_tokens = max(256, min(max_tokens, 16_384))
            llm_kwargs["max_tokens"] = max_tokens

            response = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                **llm_kwargs,
            )
            dt_llm = time.time() - t_llm
            check_cancel(cancel_event, stage="write_after_llm")

            # token usage（部分 OpenAI-compatible provider 可能不返回 usage）
            usage = getattr(response, "usage", None)
            prompt_tokens = getattr(usage, "prompt_tokens", None) if usage is not None else None
            completion_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None
            total_tokens = getattr(usage, "total_tokens", None) if usage is not None else None

            body = response.choices[0].message.content or ""
            
            # Strip common AI preambles that shouldn't appear in final report
            # Strip common AI preambles (relying on system prompt mostly now)
            # Reverted explicit stripping loop to avoid accidental truncation
            body = body.strip()
            
            # Normalize citation formats to [R#] before processing
            body = re.sub(r"[（(]R(\d+)[)）]", r"[R\1]", body)  # (R1) or （R1）
            body = re.sub(r"《R(\d+)》", r"[R\1]", body)  # 《R1》
            body = re.sub(r"\{R(\d+)\}", r"[R\1]", body)  # {R1}
            
            refs_md = self._render_references(body, ref_items)
            
            # Convert [R1] -> ⁽ᴿ¹⁾ (Unicode Superscript)
            # This avoids needing frontend to support HTML <sup> tags
            # Convert [R1] or [R1, R2] -> ⁽ᴿ¹⁾ or ⁽ᴿ¹˒ᴿ²⁾
            # This avoids needing frontend to support HTML <sup> tags
            def _to_super(m):
                content = m.group(1) # e.g. "R12" or "R1, R2"
                # Map digits to superscript
                upload_map = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
                
                parts = []
                for ref in re.split(r"[,，]\s*", content):
                    ref = ref.strip()
                    if ref.upper().startswith("R"):
                        num_part = ref[1:].translate(upload_map)
                        parts.append(f"ᴿ{num_part}")
                
                if not parts:
                    return m.group(0)
                    
                return f"⁽{','.join(parts)}⁾"

            # Match [R1], [R1, R2], [R1,R2,R3]
            body_display = re.sub(r"\[((?:R\d+\s*[,，]\s*)*R\d+)\]", _to_super, body)
            
            final = (body_display.rstrip() + "\n" + refs_md).strip() + "\n"

            # ---------- 高级统计（用于 UI 日志与排查） ----------
            used_refs = []
            seen = set()
            for rid in self._REF_RE.findall(body or ""):
                if rid in seen:
                    continue
                seen.add(rid)
                used_refs.append(rid)

            # 证据来源分布（meta/full_text/review/decision/rebuttal 等）
            src_counter = Counter()
            for it in ref_items:
                src_counter[str(it.get("source") or "unknown")] += 1

            # 句子级引用覆盖率（粗略指标，用于 debug）
            sents = []
            for line in (body or "").splitlines():
                s = line.strip()
                if not s:
                    continue
                if s.startswith("#"):
                    continue
                # 简单跳过明显的引用清单/分隔线
                if s.lower() in {"references", "参考文献"}:
                    continue
                sents.extend([x.strip() for x in self._SENT_SPLIT_RE.split(s) if x.strip()])

            total_sents = len(sents)
            cited_sents = sum(1 for s in sents if self._REF_RE.search(s))
            coverage = (cited_sents / total_sents) if total_sents > 0 else 0.0

            writer_stats = {
                "title": title,
                "sections": int(len(sections_payload)),
                "evidence_snippets": int(evidence_total),
                "refs_total": int(len(ref_items)),
                "refs_used": int(len(used_refs)),
                "refs_unused": int(max(0, len(ref_items) - len(used_refs))),
                "sources_top": dict(src_counter.most_common(10)),
                "prompt_chars": int(prompt_chars),
                "body_chars": int(len(body)),
                "final_chars": int(len(final)),
                "dt_llm_sec": float(dt_llm),
                "dt_total_sec": float(time.time() - t_all),
                "sentences_total_est": int(total_sents),
                "sentences_cited_est": int(cited_sents),
                "citation_coverage_est": float(coverage),
                "prompt_tokens": int(prompt_tokens) if isinstance(prompt_tokens, int) else None,
                "completion_tokens": int(completion_tokens) if isinstance(completion_tokens, int) else None,
                "total_tokens": int(total_tokens) if isinstance(total_tokens, int) else None,
            }
            ref_ctx["writer_stats"] = writer_stats

            _emit(
                "write_done",
                dt_llm_sec=writer_stats["dt_llm_sec"],
                refs_used=writer_stats["refs_used"],
                refs_total=writer_stats["refs_total"],
                coverage=writer_stats["citation_coverage_est"],
                body_chars=writer_stats["body_chars"],
                total_tokens=writer_stats["total_tokens"],
            )
            return final, ref_ctx
        except MujicaCancelled:
            raise
        except Exception as e:
            print(f"Error writing report: {e}")
            try:
                ref_ctx["writer_stats"] = {
                    "title": title,
                    "error": str(e),
                    "dt_total_sec": float(time.time() - t_all),
                }
            except Exception:
                pass
            _emit("write_error", error=str(e))
            return "Error generating report.", ref_ctx
