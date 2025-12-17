from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from src.utils.cancel import MujicaCancelled, check_cancel
from src.utils.json_utils import extract_json_object


def _env_truthy(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


class PlannerAgent:
    def __init__(self, llm_client, model: str = "gpt-4o"):
        self.llm = llm_client
        self.model = model

    def generate_plan(
        self,
        user_query: str,
        db_stats: Dict,
        *,
        cancel_event: Optional[Any] = None,
    ) -> Dict:
        """
        Generates a research plan/outline based on user query and DB stats using LLM.
        """
        print(f"Planning research for: {user_query} using {self.model}")
        check_cancel(cancel_event, stage="planner_start")
        
        system_prompt = """
你是 MUJICA 的 Planner（中文输出）。你的任务是：根据用户主题与数据库统计信息，生成一个**极具深度**的研究计划（JSON）。

强约束（必须遵守）：
1) 只输出一个 JSON object，不要输出任何额外文字/解释/Markdown/代码块。
2) JSON 必须包含字段：
   - title: string
   - sections: array（**建议 4~6 个**，必须覆盖背景、方法对比、实验结果、局限性讨论等多个深度维度）
   - estimated_papers: number（**建议 15~25**，以保证充足的证据量）
3) 每个 section 必须包含：
   - name: string
   - search_query: string（用于语义检索/关键词检索）
   - 可选 filters（min_rating / decision_in / presentation_in / year_in / min_year / max_year / author_contains / keyword_contains / title_contains / venue_contains）
   - top_k_papers（建议 15） / top_k_chunks（建议 60+）

JSON 示例结构（仅结构示意，不要照抄内容）：
{
  "title": "…",
  "global_filters": {
    "min_rating": 6.0,
    "decision_in": ["Accept"],
    "year_in": [2024]
  },
  "sections": [
    {
      "name": "…",
      "search_query": "…",
      "filters": {"min_rating": 6.0},
      "top_k_papers": 15,
      "top_k_chunks": 60
    }
  ],
  "estimated_papers": 20
}
""".strip()
        
        hints = []
        if db_stats.get("max_rating") is not None and db_stats.get("min_rating") is not None:
             hints.append(f"- 评分范围: {db_stats['min_rating']} ~ {db_stats['max_rating']} (切勿设置超出此范围过滤)")
        
        if db_stats.get("years"):
             # Convert to string to avoid list brackets format issues if needed, but list is fine
             hints.append(f"- 可用年份: {db_stats['years']}")

        if db_stats.get("decisions"):
             hints.append(f"- 决策类型: {db_stats['decisions']} (请优先使用列表中存在的决策值)")
             
        if db_stats.get("venues"):
             hints.append(f"- 来源会议: {db_stats['venues']}")

        data_hint = ""
        if hints:
            data_hint = "\n\n【数据库实际分布提示】\n" + "\n".join(hints) + "\n请根据上述分布调整 plan 中的过滤条件，避免检索为空。"

        user_prompt = f"""
用户主题: "{user_query}"
数据库统计: {db_stats}{data_hint}
""".strip()
        
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            # 优先尝试 JSON mode（部分模型/网关不支持，会报 code=20024）
            # DeepSeek 等模型建议禁用 JSON Mode (兼容性问题)
            is_deepseek = "deepseek" in self.model.lower()
            if not _env_truthy("MUJICA_DISABLE_JSON_MODE") and not is_deepseek:
                try:
                    print(f"[Planner] Trying JSON Mode with {self.model}...")
                    check_cancel(cancel_event, stage="planner_llm_json_before")
                    response = self.llm.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        response_format={"type": "json_object"},
                        timeout=120.0, # 防止无限卡住
                        stream=False,
                    )
                    content = response.choices[0].message.content or ""
                    print(f"[Planner] JSON Response received (len={len(content)})")
                    check_cancel(cancel_event, stage="planner_llm_json_after")
                    
                    plan = json.loads(content)
                    if isinstance(plan, dict) and plan.get("sections"):
                        return plan
                except Exception as e:
                    print(f"Planner json_mode failed: {e} (fallback to plain JSON)")

            # fallback：不用 response_format，让模型按提示输出 JSON，再做提取/解析
            print(f"[Planner] Using Plain Mode with {self.model}...")
            check_cancel(cancel_event, stage="planner_llm_plain_before")
            response = self.llm.chat.completions.create(
                model=self.model,
                messages=messages,
                timeout=120.0,
                stream=False,
            )
            content = response.choices[0].message.content or ""
            print(f"[Planner] Plain Response received (len={len(content)})")
            check_cancel(cancel_event, stage="planner_llm_plain_after")
            
            plan = extract_json_object(content)
            if isinstance(plan, dict) and plan.get("sections"):
                return plan

            raise ValueError("Planner returned invalid plan JSON.")
        except MujicaCancelled:
            raise
        except Exception as e:
            import traceback
            print(f"[PLANNER ERROR] Error generating plan: {e}")
            print(f"[PLANNER ERROR] Model: {self.model}")
            print(f"[PLANNER ERROR] Traceback:\n{traceback.format_exc()}")
            # Fallback mock plan with visible error
            return {
                "title": f"规划失败: {str(e)[:50]}",
                "sections": [{"name": "错误", "search_query": "error", "error_detail": str(e)}],
                "estimated_papers": 0,
                "_error": str(e),
                "_traceback": traceback.format_exc(),
            }

    def refine_plan(self, original_plan: Dict, user_feedback: str) -> Dict:
        """
        Updates the plan based on user feedback.
        """
        # For simplicity in this iteration, we just return the original or could add logic here.
        print("Refining plan (Mock implementation)...")
        return original_plan
