from __future__ import annotations

from typing import Any, Callable, Optional


class MujicaCancelled(RuntimeError):
    """
    协作式取消（cooperative cancellation）。

    说明：
    - Streamlit/HTTP/LLM 单次阻塞请求无法“硬中断”，我们通过在关键检查点主动抛出该异常来尽快退出。
    - 上层（UI/job runner）捕获后应将任务标记为 cancelled，并停止后续阶段。
    """


def is_cancelled(cancel_event: Optional[Any]) -> bool:
    """
    判断是否需要取消。

    支持：
    - threading.Event（.is_set）
    - callable（返回 truthy 表示取消）
    - bool
    """
    if cancel_event is None:
        return False
    try:
        if isinstance(cancel_event, bool):
            return bool(cancel_event)
        if hasattr(cancel_event, "is_set"):
            return bool(cancel_event.is_set())  # type: ignore[attr-defined]
        if callable(cancel_event):
            fn: Callable[[], Any] = cancel_event  # type: ignore[assignment]
            return bool(fn())
    except Exception:
        return False
    return False


def check_cancel(cancel_event: Optional[Any], *, stage: str = "") -> None:
    if is_cancelled(cancel_event):
        msg = f"cancelled{': ' + stage if stage else ''}"
        raise MujicaCancelled(msg)


