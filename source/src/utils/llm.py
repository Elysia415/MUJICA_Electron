from openai import OpenAI
import os
import hashlib
import re
import time
import random
from typing import List, Dict, Optional

from src.utils.env import load_env


def _env_truthy(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


_EMBED_ERR_ONCE = set()
_LAST_EMBED_REQ_AT = 0.0
_LAST_EMBED_RL_LOG_AT = 0.0


def _print_embedding_error_once(*, kind: str, model: str, err: Exception) -> None:
    msg = str(err)
    key = f"{kind}:{model}:{msg}"
    if key in _EMBED_ERR_ONCE:
        return
    _EMBED_ERR_ONCE.add(key)

    lower = msg.lower()
    if "model does not exist" in lower or "code': 20012" in msg or "code\": 20012" in msg:
        print(
            f"{kind}: Embedding 模型不存在/不支持（model={model}）。"
            "请检查 Embedding Model（通常不是聊天模型名），或开启 MUJICA_FAKE_EMBEDDINGS=1 走离线向量。"
            f" 原始错误: {err}"
        )
        return

    print(f"{kind}: {err}")


def _fake_embedding(text: str, *, dim: int = 384) -> list:
    """
    离线/测试用的确定性 embedding（不依赖外部服务）。
    - 仅用于无 API Key 或希望可复现的单元测试场景
    - 维度可通过 MUJICA_FAKE_EMBEDDING_DIM 调整
    """
    text = (text or "").encode("utf-8")
    dim = max(16, int(dim))

    # 生成足够多的 bytes
    need = dim * 4
    buf = b""
    counter = 0
    while len(buf) < need:
        buf += hashlib.sha256(text + str(counter).encode("utf-8")).digest()
        counter += 1

    vec = []
    for i in range(dim):
        b = buf[i * 4 : (i + 1) * 4]
        u = int.from_bytes(b, "little", signed=False)
        # 映射到 [0,1)
        vec.append((u % 1_000_000) / 1_000_000.0)
    return vec


def _is_rate_limited(err: Exception) -> bool:
    """
    兼容 OpenAI SDK / OpenAI-compatible 网关的 429 限流异常判断。
    """
    try:
        sc = getattr(err, "status_code", None)
        if sc is not None and int(sc) == 429:
            return True
    except Exception:
        pass

    msg = str(err or "")
    lower = msg.lower()
    if "error code: 429" in lower:
        return True
    if ("429" in lower) and ("rate limit" in lower or "rate limiting" in lower or "tpm" in lower):
        return True
    return False


def _extract_retry_after_seconds(err: Exception) -> Optional[float]:
    """
    尝试从异常中提取服务端建议的重试等待时间（Retry-After）。
    - OpenAI SDK 可能把 httpx.Response 放在 err.response
    - 部分网关会把 “retry-after” 写在错误文本里
    """
    # 1) headers
    for obj in [getattr(err, "response", None), getattr(err, "__cause__", None), getattr(err, "__context__", None)]:
        try:
            if obj is None:
                continue
            headers = getattr(obj, "headers", None)
            if headers and isinstance(headers, dict):
                ra = headers.get("retry-after") or headers.get("Retry-After")
                if ra is not None:
                    return float(ra)
        except Exception:
            continue

    # 2) message
    msg = str(err or "")
    m = re.search(r"retry[- ]after\\s*([0-9]+(?:\\.[0-9]+)?)", msg, flags=re.I)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    return None


def _throttle_embedding_requests() -> None:
    """
    通过最小请求间隔来“限速”，降低触发 TPM/RPM 的概率。
    - MUJICA_EMBEDDING_MIN_INTERVAL: 每次 embedding 请求之间至少间隔多少秒（默认 0，不限速）
    """
    global _LAST_EMBED_REQ_AT
    try:
        min_interval = float(os.getenv("MUJICA_EMBEDDING_MIN_INTERVAL", "0") or 0.0)
    except Exception:
        min_interval = 0.0
    if min_interval <= 0:
        return

    now = time.time()
    wait = min_interval - (now - float(_LAST_EMBED_REQ_AT or 0.0))
    if wait > 0:
        time.sleep(min(wait, 60.0))
    _LAST_EMBED_REQ_AT = time.time()


def _embeddings_create_with_retry(client: OpenAI, *, model: str, input_texts: List[str], tag: Optional[str] = None):
    """
    对 embedding create 做 429 自动退避重试。
    关键：不要在外层“吞掉异常后返回空向量”，否则会导致入库但没有向量，检索失效。
    """
    global _LAST_EMBED_RL_LOG_AT

    try:
        max_retries = int(os.getenv("MUJICA_EMBEDDING_RETRY_MAX", "8") or 8)
    except Exception:
        max_retries = 8
    max_retries = max(0, min(max_retries, 30))

    try:
        base_delay = float(os.getenv("MUJICA_EMBEDDING_RETRY_BASE_DELAY", "1.0") or 1.0)
    except Exception:
        base_delay = 1.0
    base_delay = max(0.2, min(base_delay, 30.0))

    try:
        max_delay = float(os.getenv("MUJICA_EMBEDDING_RETRY_MAX_DELAY", "60") or 60.0)
    except Exception:
        max_delay = 60.0
    max_delay = max(1.0, min(max_delay, 600.0))

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            _throttle_embedding_requests()
            return client.embeddings.create(input=input_texts, model=model)
        except Exception as e:
            last_err = e
            if _is_rate_limited(e) and attempt < max_retries:
                retry_after = _extract_retry_after_seconds(e)
                wait = retry_after if (retry_after is not None and retry_after > 0) else min(base_delay * (2**attempt), max_delay)
                # jitter
                wait = min(max_delay, wait * (0.85 + random.random() * 0.30))

                now = time.time()
                if now - float(_LAST_EMBED_RL_LOG_AT or 0.0) >= 3.0:
                    _LAST_EMBED_RL_LOG_AT = now
                    prefix = f"[{tag}] " if tag else ""
                    print(
                        f"{prefix}Embedding 触发限流(429, TPM/RPM)。等待 {wait:.1f}s 后自动重试... "
                        f"({attempt+1}/{max_retries})"
                    )
                time.sleep(wait)
                continue

            raise

    # 理论上不会到这里
    raise last_err if last_err else RuntimeError("Embedding create failed")

def get_llm_client(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    *,
    allow_env_fallback: bool = True,
):
    """
    Returns an initialized OpenAI client.
    Args:
        api_key: User-provided API key. If None, falls back to env var.
        base_url: User-provided Base URL. If None, falls back to env var.
        allow_env_fallback: 是否允许从环境变量读取 OPENAI_API_KEY/OPENAI_BASE_URL。
            - True（默认）：兼容脚本/本地直接用 .env 配置的方式
            - False：严格模式，只使用显式传入的 api_key/base_url（用于 Demo 门禁）
    """
    load_env()
    
    # Helper to check if a value is a masked/placeholder (should not be used)
    def _is_masked(v: str) -> bool:
        return v and ("***" in v or v.strip() in {"", "null", "undefined"})
    
    # 1. Determine API Key (ignore masked values)
    effective_key = api_key if (api_key and not _is_masked(api_key)) else None
    if allow_env_fallback:
        final_api_key = effective_key if effective_key else os.getenv("OPENAI_API_KEY")
    else:
        final_api_key = effective_key
    
    if not final_api_key:
        print("Warning: API Key not found (neither provided nor in env).")
        return None
    
    # 2. Determine Base URL
    if allow_env_fallback:
        final_base_url = base_url if base_url else os.getenv("OPENAI_BASE_URL")
    else:
        final_base_url = base_url if base_url else None
    
    return OpenAI(api_key=final_api_key, base_url=final_base_url)

def get_embedding(text: str, model="text-embedding-3-small", 
                 api_key: Optional[str] = None, 
                 base_url: Optional[str] = None,
                 tag: Optional[str] = None) -> list:
    """
    Generates vector embedding for the given text.
    """
    load_env()
    if _env_truthy("MUJICA_FAKE_EMBEDDINGS"):
        dim = int(os.getenv("MUJICA_FAKE_EMBEDDING_DIM", "384"))
        return _fake_embedding(text, dim=dim)

    client = get_llm_client(api_key=api_key, base_url=base_url)
    if not client:
        return []
    try:
        text = text.replace("\n", " ")
        resp = _embeddings_create_with_retry(client, model=str(model), input_texts=[text], tag=tag)
        return resp.data[0].embedding
    except Exception as e:
        _print_embedding_error_once(kind="Error generating embedding", model=str(model), err=e)
        return []


def get_embeddings(
    texts: List[str],
    model: str = "text-embedding-3-small",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    tag: Optional[str] = None,
) -> List[list]:
    """
    批量生成 embedding（比逐条请求更快/更省）。
    失败时会返回与输入等长的空向量列表。
    """
    load_env()
    if not texts:
        return []

    if _env_truthy("MUJICA_FAKE_EMBEDDINGS"):
        dim = int(os.getenv("MUJICA_FAKE_EMBEDDING_DIM", "384"))
        return [_fake_embedding(t, dim=dim) for t in texts]

    client = get_llm_client(api_key=api_key, base_url=base_url)
    if not client:
        return [[] for _ in texts]

    try:
        cleaned = [(t or "").replace("\n", " ") for t in texts]
        resp = _embeddings_create_with_retry(client, model=str(model), input_texts=cleaned, tag=tag)
        # OpenAI 返回顺序与输入一致（每条包含 index）
        out = [None] * len(cleaned)
        for item in resp.data:
            out[item.index] = item.embedding
        return [v if v is not None else [] for v in out]
    except Exception as e:
        # 兼容部分 OpenAI-compatible 网关：对单次请求的 input 数组长度有限制
        # 例如：SiliconFlow 常见报错 "input batch size 100 > maximum allowed batch size 64"（code 20042）
        msg = str(e)
        m = re.search(r"maximum allowed batch size\s+(\d+)", msg)
        if m:
            try:
                max_batch = int(m.group(1))
            except Exception:
                max_batch = 64

            max_batch = max(1, min(max_batch, 256))
            out_all: List[list] = []
            for start in range(0, len(cleaned), max_batch):
                batch = cleaned[start : start + max_batch]
                try:
                    sub_tag = f"{tag} split {start}-{start+len(batch)-1}" if tag else None
                    r = _embeddings_create_with_retry(client, model=str(model), input_texts=batch, tag=sub_tag)
                    batch_out = [None] * len(batch)
                    for item in r.data:
                        batch_out[item.index] = item.embedding
                    out_all.extend([v if v is not None else [] for v in batch_out])
                except Exception as ee:
                    _print_embedding_error_once(kind="Error generating embeddings", model=str(model), err=ee)
                    out_all.extend([[] for _ in batch])

            # 保证返回长度一致
            if len(out_all) == len(texts):
                return out_all

        _print_embedding_error_once(kind="Error generating embeddings", model=str(model), err=e)
        return [[] for _ in texts]

def chat(messages: List[Dict[str, str]], 
         model: str = "gpt-4o",
         temperature: float = 0.2,
         client: Optional[OpenAI] = None) -> str:
    """
    Generic chat wrapper.
    """
    # Client should be passed in, but if not, logic inside get_llm_client handles env fallback
    if client is None:
        client = get_llm_client()
        if client is None:
            return ""
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in chat: {e}")
        return ""
