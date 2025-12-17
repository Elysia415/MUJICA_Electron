from __future__ import annotations

import json
import re
from typing import Any, Dict


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def extract_json_object(text: str) -> Dict[str, Any]:
    """
    从 LLM 输出中提取 JSON object。

    兼容常见形式：
    - 纯 JSON：{...}
    - Markdown code fence：```json\n{...}\n```
    - JSON 前后夹杂解释文本（取首个 '{' 到最后一个 '}'）
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("empty text")

    m = _JSON_FENCE_RE.search(text)
    if m:
        text = (m.group(1) or "").strip()

    # 优先直接 parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 兜底：截取最大括号段
    l = text.find("{")
    r = text.rfind("}")
    if l < 0 or r < 0 or r <= l:
        raise ValueError("no json object braces found")

    candidate = text[l : r + 1].strip()
    obj = json.loads(candidate)
    if not isinstance(obj, dict):
        raise ValueError("json is not an object")
    return obj


