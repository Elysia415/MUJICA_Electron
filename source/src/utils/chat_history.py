from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_ts() -> float:
    return float(time.time())


def new_conversation_id() -> str:
    # e.g. 20251215-210533-a1b2c3d4
    t = time.strftime("%Y%m%d-%H%M%S")
    return f"{t}-{uuid.uuid4().hex[:8]}"


def _get_data_dir() -> Path:
    """Get data directory, handling PyInstaller bundling."""
    if getattr(sys, 'frozen', False):
        # Packaged mode - use user directory
        if os.name == 'nt':
            user_config = Path(os.environ.get('APPDATA', os.path.expanduser('~'))) / 'MUJICA'
        else:
            user_config = Path.home() / '.mujica'
        return user_config / 'data'
    else:
        # Dev mode - use relative path
        return Path("data")


def _history_dir() -> Path:
    d = _get_data_dir() / "ui_history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _conv_path(cid: str) -> Path:
    safe = "".join(ch for ch in (cid or "") if ch.isalnum() or ch in {"-", "_"})
    return _history_dir() / f"{safe}.json"


def _index_path() -> Path:
    return _history_dir() / "index.json"


def load_index() -> List[Dict[str, Any]]:
    p = _index_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_index(items: List[Dict[str, Any]]) -> None:
    p = _index_path()
    try:
        p.write_text(json.dumps(items or [], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # best-effort persistence
        return


def list_conversations(limit: int = 100) -> List[Dict[str, Any]]:
    items = load_index()
    # sort by updated_ts desc
    try:
        items.sort(key=lambda x: float((x or {}).get("updated_ts") or 0.0), reverse=True)
    except Exception:
        pass
    return items[: max(1, min(int(limit), 500))]


def _derive_title(snapshot: Dict[str, Any]) -> str:
    msgs = snapshot.get("messages") if isinstance(snapshot, dict) else None
    if isinstance(msgs, list):
        for m in msgs:
            if isinstance(m, dict) and m.get("role") == "user":
                s = str(m.get("content") or "").strip()
                if s:
                    s = s.splitlines()[0].strip()
                    return (s[:48] + "…") if len(s) > 48 else s
    return "未命名对话"


def save_conversation(cid: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    保存一个对话快照（messages + 报告/核查等）。
    注意：snapshot 必须是“脱敏”的（不要包含 API Key/Access Code）。
    """
    if not cid:
        return {"ok": False, "error": "missing cid"}

    data = snapshot if isinstance(snapshot, dict) else {}
    title = str(data.get("title") or "").strip() or _derive_title(data)
    now = _now_ts()

    meta = {
        "cid": cid,
        "title": title,
        "updated_ts": now,
        "created_ts": float(data.get("created_ts") or now),
    }

    # write conversation file
    try:
        payload = {"meta": meta, "snapshot": data}
        _conv_path(cid).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # update index (upsert)
    items = load_index()
    out: List[Dict[str, Any]] = []
    found = False
    for it in items:
        if isinstance(it, dict) and it.get("cid") == cid:
            out.append(meta)
            found = True
        else:
            out.append(it if isinstance(it, dict) else {})
    if not found:
        out.append(meta)
    save_index(out)
    return {"ok": True, "meta": meta}


def load_conversation(cid: str) -> Optional[Dict[str, Any]]:
    if not cid:
        return None
    p = _conv_path(cid)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        snap = data.get("snapshot")
        return snap if isinstance(snap, dict) else None
    except Exception:
        return None


def rename_conversation(cid: str, new_title: str) -> Dict[str, Any]:
    title = str(new_title or "").strip()
    if not cid:
        return {"ok": False, "error": "missing cid"}
    if not title:
        return {"ok": False, "error": "empty title"}

    now = _now_ts()
    p = _conv_path(cid)
    payload: Dict[str, Any] = {}
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                payload = raw
        except Exception:
            payload = {}

    snap = payload.get("snapshot") if isinstance(payload, dict) else None
    if not isinstance(snap, dict):
        snap = {}

    meta = payload.get("meta") if isinstance(payload, dict) else None
    if not isinstance(meta, dict):
        meta = {}

    try:
        created_ts = float(meta.get("created_ts") or snap.get("created_ts") or now)
    except Exception:
        created_ts = now

    meta2 = {"cid": cid, "title": title, "updated_ts": now, "created_ts": created_ts}
    snap["title"] = title
    if "created_ts" not in snap:
        snap["created_ts"] = created_ts

    try:
        p.write_text(json.dumps({"meta": meta2, "snapshot": snap}, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # update index
    items = load_index()
    out: List[Dict[str, Any]] = []
    found = False
    for it in items:
        if isinstance(it, dict) and it.get("cid") == cid:
            out.append(meta2)
            found = True
        else:
            out.append(it if isinstance(it, dict) else {})
    if not found:
        out.append(meta2)
    save_index(out)

    return {"ok": True, "meta": meta2}


def delete_conversation(cid: str) -> Dict[str, Any]:
    if not cid:
        return {"ok": False, "error": "missing cid"}

    # delete file (best-effort)
    try:
        p = _conv_path(cid)
        if p.exists():
            p.unlink()
    except Exception:
        pass

    # delete from index
    try:
        items = load_index()
        out = [it for it in items if not (isinstance(it, dict) and it.get("cid") == cid)]
        save_index(out)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True}

