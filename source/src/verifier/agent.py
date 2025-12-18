from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from src.utils.cancel import MujicaCancelled, check_cancel
from src.utils.json_utils import extract_json_object


def _env_truthy(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


class VerifierAgent:
    """
    事实核查（NLI/Entailment）：逐句对齐引用到的 evidence chunk。

    支持的引用格式（兼容多种报告风格）：
    1) Ref ID（推荐，对人友好）：[R1] / [R12][R3]
    2) Chunk ID 简写（兼容旧 UI）：[paper_id::source::chunk_index]
    3) 传统格式（旧 Writer）：[Paper ID: <paper_id> | Chunk: <chunk_id>]
    """

    _CIT_RE = re.compile(r"\[Paper ID:\s*([^\]|]+?)\s*\|\s*Chunk:\s*([^\]]+?)\]")
    _PAPER_ONLY_RE = re.compile(r"\[Paper ID:\s*([^\]]+?)\]")
    _CHUNK_ONLY_RE = re.compile(r"\[([^\[\]\s]+::[^\[\]\s]+::\d+)\]")
    _REF_RE = re.compile(r"\[(R\d+)\]")
    _REF_SECTION_RE = re.compile(r"(?im)^\s*#{1,6}\s+(references|参考文献)\s*$")
    # Unicode superscript pattern: ⁽ᴿ⁴⁰⁾ or ⁽ᴿ¹⁰,ᴿ⁵⁾ etc.
    _UNICODE_SUP_RE = re.compile(r"\u207d([\u1d3f\u00b9\u00b2\u00b3\u2070-\u2079,]+)\u207e")
    # Map Unicode superscript digits to ASCII
    _SUP_DIGIT_MAP = {
        '\u2070': '0', '\u00b9': '1', '\u00b2': '2', '\u00b3': '3',
        '\u2074': '4', '\u2075': '5', '\u2076': '6', '\u2077': '7',
        '\u2078': '8', '\u2079': '9', '\u1d3f': 'R', ',': ','
    }

    def __init__(self, llm_client, model: str = "gpt-4o"):
        self.llm = llm_client
        self.model = model

    def _normalize_superscript_refs(self, text: str) -> str:
        """Convert Unicode superscript citations like ⁽ᴿ⁴⁰⁾ to [R40] format."""
        def replace_match(m):
            inner = m.group(1)
            normalized = ''.join(self._SUP_DIGIT_MAP.get(c, c) for c in inner)
            # Handle comma-separated refs: R40,R5,R44 -> [R40][R5][R44]
            refs = [r.strip() for r in normalized.split(',') if r.strip()]
            return ''.join(f'[{r}]' for r in refs)
        return self._UNICODE_SUP_RE.sub(replace_match, text)

    def _extract_claims(self, report_text: str, *, ref_map: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        text = (report_text or "").replace("\r\n", "\n")
        # Normalize Unicode superscript citations first
        text = self._normalize_superscript_refs(text)

        # 忽略 References/参考文献 小节（避免把引用清单当成 claims 去核查）
        m = self._REF_SECTION_RE.search(text)
        if m:
            text = text[: m.start()]

        lines = [l.strip() for l in text.split("\n") if l.strip()]

        claims: List[Dict[str, Any]] = []
        for line in lines:
            # 进一步按句号/问号/感叹号切分，降低“一个段落多个句子”带来的误配
            parts = re.split(r"(?<=[。！？.!?])\s+", line)
            for part in parts:
                pair_cits = self._CIT_RE.findall(part)
                ref_cits = self._REF_RE.findall(part)
                chunk_cits = self._CHUNK_ONLY_RE.findall(part)

                if (not pair_cits) and (not ref_cits) and (not chunk_cits):
                    continue

                claim_text = part
                claim_text = self._CIT_RE.sub("", claim_text)
                claim_text = self._REF_RE.sub("", claim_text)
                claim_text = self._CHUNK_ONLY_RE.sub("", claim_text)
                claim_text = claim_text.strip()
                claim_text = re.sub(r"\s+", " ", claim_text).strip()
                if not claim_text:
                    continue

                citations: List[Dict[str, Any]] = []

                # 传统格式：带 paper_id
                for p, c in pair_cits:
                    citations.append({"paper_id": p.strip(), "chunk_id": c.strip()})

                # chunk_id-only：paper_id 从 chunk_id 前缀推断
                for cid in chunk_cits:
                    s = str(cid).strip()
                    pid = s.split("::", 1)[0] if "::" in s else ""
                    citations.append({"paper_id": pid, "chunk_id": s})

                # Ref ID：映射到 chunk_id
                for rid in ref_cits:
                    if not ref_map or rid not in ref_map:
                        # 交给上层统一报错（unknown ref）
                        citations.append({"paper_id": "", "chunk_id": "", "ref": rid})
                        continue
                    cid = str(ref_map.get(rid) or "").strip()
                    pid = cid.split("::", 1)[0] if "::" in cid else ""
                    citations.append({"paper_id": pid, "chunk_id": cid, "ref": rid})

                claims.append({"claim": claim_text, "raw": part, "citations": citations})

        return claims

    def verify_report(
        self,
        report_text: str,
        source_data: Dict[str, Any],
        *,
        cancel_event: Optional[Any] = None,
    ) -> Dict[str, Any]:
        print("Verifying report integrity...")
        check_cancel(cancel_event, stage="verify_start")

        # evidence index: chunk_id -> text
        chunk_map = source_data.get("chunks") if isinstance(source_data, dict) else None
        if not isinstance(chunk_map, dict):
            chunk_map = {}

        # Ref ID map: R# -> chunk_id
        ref_map = source_data.get("ref_map") if isinstance(source_data, dict) else None
        if not isinstance(ref_map, dict):
            ref_map = {}

        # 如果报告引用了未知的 Ref ID，直接报错（否则后续会表现为“找不到 chunk”）
        report_refs = set(self._REF_RE.findall(report_text or ""))
        unknown_refs = sorted([r for r in report_refs if r not in ref_map])
        if unknown_refs:
            return {
                "is_valid": False,
                "score": 0.0,
                "notes": f"发现未知引用标记（Ref ID 不在本次证据集中）：{', '.join(unknown_refs[:20])}",
                "unknown_refs": unknown_refs[:50],
            }

        claims = self._extract_claims(report_text, ref_map=ref_map)
        if not claims:
            # fallback：兼容旧格式，仅检查是否存在 [Paper ID: ...]
            citations = self._PAPER_ONLY_RE.findall(report_text or "")
            chunk_only = self._CHUNK_ONLY_RE.findall(report_text or "")
            refs = self._REF_RE.findall(report_text or "")
            if (not citations) and (not chunk_only) and (not refs):
                return {
                    "is_valid": False,
                    "score": 0.0,
                    "notes": "未发现任何引用。请在结论句末尾加入引用（支持 [R1] / [paper_id::source::idx] / [Paper ID: ... | Chunk: ...]）。",
                }
            if refs:
                return {
                    "is_valid": True,
                    "score": 0.5,
                    "notes": "检测到引用标记（Ref ID），但未能抽取可核查的句级 claims；跳过逐句 NLI。",
                    "comment": "⚠️ **验证未完成**\n检测到引用标记（Ref ID），但未能抽取可核查的句级论点。可能是引用格式不规范或位于参考文献段落之外。",
                    "stats": {"unique_refs": len(set([c.strip() for c in refs]))},
                }
            if chunk_only:
                return {
                    "is_valid": True,
                    "score": 0.5,
                    "notes": "检测到 chunk-level 引用（chunk_id-only），但未能抽取可核查的句级 claims；跳过逐句 NLI。",
                    "comment": "⚠️ **验证未完成**\n检测到 Chunk 级引用，但未能抽取可核查的句级论点。请确保引用标记紧跟在事实陈述之后。",
                    "stats": {"unique_chunk_citations": len(set([c.strip() for c in chunk_only]))},
                }
            return {
                "is_valid": True,
                "score": 0.5,
                "notes": "仅检测到 paper-level 引用（未提供 chunk 级证据），跳过逐句 NLI 核查。",
                "comment": "⚠️ **验证未完成**\n仅检测到论文级引用（Paper ID），未提供具体的 Evidence Chunk，无法进行深度事实核查。",
                "stats": {"unique_paper_citations": len(set([c.strip() for c in citations]))},
            }

        # 1) 结构性检查：引用的 chunk 是否存在
        missing_chunks = []
        if chunk_map:
            for c in claims:
                for cit in c["citations"]:
                    cid = cit["chunk_id"]
                    if cid not in chunk_map:
                        missing_chunks.append(cid)

        if missing_chunks:
            uniq = sorted(set(missing_chunks))
            return {
                "is_valid": False,
                "score": 0.0,
                "notes": f"发现引用了未知的 chunk（数量={len(uniq)}），无法溯源核查。",
                "missing_chunks": uniq[:50],
            }

        # 2) 若无 LLM：只做结构性核查
        if self.llm is None:
            return {
                "is_valid": True,
                "score": 0.6,
                "notes": "LLM 不可用：仅完成引用结构/可溯源性检查（未做 entailment）。",
                "stats": {"claims_checked": len(claims), "mode": "structural_only"},
            }

        # 3) entailment 核查（抽样/限额）
        max_claims = int(source_data.get("max_claims", 60)) if isinstance(source_data, dict) else 60
        max_claims = max(10, min(max_claims, 100))

        evaluations: List[Dict[str, Any]] = []
        contradicts = 0
        supports = 0
        scores: List[float] = []

        system_prompt = (
            "你是严格的事实核查/NLI 模型。"
            "给定 Claim 与 Evidence（来自论文片段），判断 Evidence 是否支持 Claim。"
            "只输出 JSON，不要输出其他文本。"
        )

        for item in claims[:max_claims]:
            check_cancel(cancel_event, stage="verify_claim")
            claim = item["claim"]
            cited_chunks = item["citations"]

            ev_texts = []
            for cit in cited_chunks:
                cid = cit["chunk_id"]
                t = chunk_map.get(cid, "")
                if t:
                    ev_texts.append(f"[Chunk: {cid}]\n{t}")

            evidence_block = "\n\n".join(ev_texts)[:6000]

            user_prompt = f"""
Claim:
{claim}

Evidence:
{evidence_block}

请返回 JSON：
{{
  "label": "entailed|contradicted|unknown",
  "score": 0.0,
  "reason": "一句话解释"
}}
"""
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]

                try:
                    if _env_truthy("MUJICA_DISABLE_JSON_MODE"):
                        raise RuntimeError("json_mode_disabled")
                    resp = self.llm.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        response_format={"type": "json_object"},
                    )
                    parsed = json.loads(resp.choices[0].message.content or "{}")
                except Exception as e:
                    if str(e) != "json_mode_disabled":
                        print(f"Verifier json_mode failed: {e} (fallback to plain JSON)")
                    resp = self.llm.chat.completions.create(
                        model=self.model,
                        messages=messages,
                    )
                    parsed = extract_json_object(resp.choices[0].message.content or "")
                check_cancel(cancel_event, stage="verify_after_llm")
            except MujicaCancelled:
                raise
            except Exception as e:
                parsed = {"label": "unknown", "score": 0.0, "reason": f"verification_error: {e}"}

            label = str(parsed.get("label", "unknown")).lower().strip()
            score = float(parsed.get("score", 0.0) or 0.0)
            if score != score: score = 0.0  # Handle NaN
            reason = str(parsed.get("reason", ""))

            if label == "contradicted":
                contradicts += 1
            elif label == "entailed":
                supports += 1
            scores.append(max(0.0, min(1.0, score)))

            # Convert List[Dict] to List[str] for display: extract ref or chunk_id
            cited_refs = [str(c.get("ref") or c.get("chunk_id", "?")) for c in cited_chunks if isinstance(c, dict)]

            evaluations.append(
                {
                    "claim": claim,
                    "citations": cited_refs,  # Now List[str], safe for join()
                    "label": label,
                    "score": score,
                    "reason": reason,
                }
            )

        overall = sum(scores) / len(scores) if scores else 0.0
        if overall != overall: overall = 0.0  # Handle NaN
        # Scale to 0-10
        final_score = round(overall * 10, 1)
        
        # Scale score to 0-10 for UI display
        final_score = round(overall * 10, 1)
        if final_score != final_score: final_score = 0.0
        is_valid = (overall >= 0.7) and (contradicts == 0)

        notes = f"checked={len(evaluations)}, supports={supports}, contradicts={contradicts}, score={final_score}/10"
        
        comment_lines = [f"**核查摘要**：共检验了 {len(evaluations)} 个关键论点。"]
        comment_lines.append(f"✅ 支持: {supports} | ⚠️ 存疑: {len(evaluations) - supports - contradicts} | ❌ 冲突: {contradicts}")
        comment_lines.append("")
        
        # 分类整理验证结果
        contradicted_claims = [ev for ev in evaluations if ev["label"] == "contradicted"]
        supported_claims = [ev for ev in evaluations if ev["label"] == "entailed"]
        unknown_claims = [ev for ev in evaluations if ev["label"] not in ("contradicted", "entailed")]
        
        # 1) 冲突论点（优先显示，因为风险最高）
        if contradicted_claims:
            comment_lines.append("### ❌ 发现冲突（幻觉风险）")
            for idx, ev in enumerate(contradicted_claims, 1):
                refs = ", ".join(str(c) for c in ev['citations']) if ev['citations'] else "无"
                comment_lines.append(f'**{idx}. 论点**: "{ev["claim"]}"')
                comment_lines.append(f"   - **引用**: {refs}")
                comment_lines.append(f"   - **原因**: {ev['reason']}")
                comment_lines.append("")
        
        # 2) 存疑论点
        if unknown_claims:
            comment_lines.append("### ⚠️ 存疑论点（证据不充分）")
            for idx, ev in enumerate(unknown_claims, 1):
                refs = ", ".join(str(c) for c in ev['citations']) if ev['citations'] else "无"
                comment_lines.append(f'**{idx}. 论点**: "{ev["claim"]}"')
                comment_lines.append(f"   - **引用**: {refs}")
                comment_lines.append(f"   - **原因**: {ev['reason']}")
                comment_lines.append("")
        
        # 3) 已验证论点（完整展示，不再限制5条）
        if supported_claims:
            comment_lines.append("### ✅ 已验证论点")
            for idx, ev in enumerate(supported_claims, 1):
                refs = ", ".join(str(c) for c in ev['citations']) if ev['citations'] else "无"
                comment_lines.append(f'**{idx}. 论点**: "{ev["claim"]}"')
                comment_lines.append(f"   - **引用**: {refs}")
                comment_lines.append(f"   - **原因**: {ev['reason']}")
                comment_lines.append("")
        
        # 总评
        comment_lines.append("---")
        if overall >= 0.8 and contradicts == 0:
            comment_lines.append("**总评**: ✅ 引用一致性优秀，报告内容可信度高")
        elif contradicts > 0:
            comment_lines.append("**总评**: ❌ 存在幻觉风险，建议复核上述冲突论点")
        else:
            comment_lines.append("**总评**: ⚠️ 部分论点证据不足，建议补充引用来源")
        
        # Debug: confirm new code is running
        print(f"[VerifierAgent] score={final_score}/10, comment_len={len(''.join(comment_lines))}")
        
        return {
            "is_valid": is_valid,
            "score": final_score,
            "comment": "\n".join(comment_lines),
            "notes": notes,
            "evaluations": evaluations,
            "stats": {"claims_total": len(claims), "claims_checked": len(evaluations)},
        }
