from __future__ import annotations

from typing import List


def chunk_text(
    text: str,
    *,
    max_tokens: int = 350,
    overlap_tokens: int = 60,
    encoding_name: str = "cl100k_base",
) -> List[str]:
    """
    将长文本切成带 overlap 的 chunk（token 级），用于向量化与证据溯源。

    - 默认使用 tiktoken 的 cl100k_base（兼容大多数 OpenAI 系模型）
    - 若 tiktoken 不可用，则退化为按字符长度切分
    """
    text = (text or "").strip()
    if not text:
        return []

    max_tokens = max(50, int(max_tokens))
    overlap_tokens = max(0, int(overlap_tokens))
    if overlap_tokens >= max_tokens:
        overlap_tokens = max_tokens // 5

    try:
        import tiktoken

        enc = tiktoken.get_encoding(encoding_name)
        tokens = enc.encode(text)
        if len(tokens) <= max_tokens:
            return [text]

        chunks: List[str] = []
        start = 0
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            chunk = enc.decode(tokens[start:end]).strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(tokens):
                break
            start = max(0, end - overlap_tokens)
        return chunks
    except Exception:
        # fallback：按字符切（粗糙但可用）
        approx_chars = max_tokens * 4  # 粗略估计 1 token ≈ 3~4 chars
        overlap_chars = overlap_tokens * 4
        if len(text) <= approx_chars:
            return [text]

        chunks: List[str] = []
        start = 0
        while start < len(text):
            end = min(start + approx_chars, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start = max(0, end - overlap_chars)
        return chunks


