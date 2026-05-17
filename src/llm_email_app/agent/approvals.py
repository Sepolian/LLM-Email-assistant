from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional
import uuid


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_list(payload: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _sort_work_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = list(items)
    ordered.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    ordered.sort(key=lambda item: 0 if item.get("status") == "pending" and item.get("blocking") else 1)
    return ordered


class JsonListStore:
    storage_key = "items"

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self._lock = RLock()

    def _empty_payload(self) -> Dict[str, Any]:
        return {
            "generated_at": _utc_now(),
            "count": 0,
            self.storage_key: [],
        }

    def _load_payload(self) -> Dict[str, Any]:
        if not self.storage_path.exists():
            return self._empty_payload()
        try:
            return json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            return self._empty_payload()

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(payload)
        payload["generated_at"] = _utc_now()
        payload["count"] = len(_safe_list(payload, self.storage_key))
        self.storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_items(self) -> List[Dict[str, Any]]:
        payload = self._load_payload()
        return _safe_list(payload, self.storage_key)

    def _save_items(self, items: List[Dict[str, Any]]) -> None:
        self._save_payload({self.storage_key: items})

    def clear(self) -> None:
        with self._lock:
            self._save_items([])


class WorkItemStore(JsonListStore):
    storage_key = "work_items"

    def _load_items(self) -> List[Dict[str, Any]]:
        payload = self._load_payload()
        items = _safe_list(payload, self.storage_key)
        if items:
            return items
        legacy = _safe_list(payload, "approvals")
        for item in legacy:
            item.setdefault("type", "approval")
            item.setdefault("blocking", True)
            item.setdefault("allowed_actions", ["approve", "reject", "edit", "respond"])
        return legacy

    def create(self, **fields: Any) -> Dict[str, Any]:
        item_type = str(fields.get("type") or "approval")
        allowed_actions = list(fields.get("allowed_actions") or self.default_allowed_actions(item_type))
        allowed_responses = list(fields.get("allowed_responses") or [])
        now = _utc_now()
        record = {
            "id": fields.get("id") or uuid.uuid4().hex,
            "type": item_type,
            "status": fields.get("status") or "pending",
            "blocking": bool(fields.get("blocking", True)),
            "created_at": fields.get("created_at") or now,
            "updated_at": fields.get("updated_at") or now,
            "allowed_actions": allowed_actions,
            "allowed_responses": allowed_responses,
            **{key: value for key, value in fields.items() if key not in {"allowed_actions", "allowed_responses"}},
        }
        with self._lock:
            items = self._load_items()
            items.append(record)
            self._save_items(items)
        return dict(record)

    def list(
        self,
        *,
        status: Optional[str] = None,
        thread_id: Optional[str] = None,
        item_type: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            items = self._load_items()
        if status:
            items = [item for item in items if item.get("status") == status]
        if thread_id:
            items = [item for item in items if item.get("thread_id") == thread_id]
        if item_type:
            items = [item for item in items if item.get("type") == item_type]
        items = _sort_work_items(items)
        return [dict(item) for item in items[: max(1, limit)]]

    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            items = self._load_items()
        for item in items:
            if item.get("id") == item_id:
                return dict(item)
        return None

    def update(self, item_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        with self._lock:
            items = self._load_items()
            for item in items:
                if item.get("id") == item_id:
                    item.update(fields)
                    item["updated_at"] = _utc_now()
                    self._save_items(items)
                    return dict(item)
        return None

    def find_pending(
        self,
        *,
        thread_id: str,
        item_type: Optional[str] = None,
        step: Optional[int] = None,
        tool_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            items = self._load_items()
        for item in items:
            if item.get("status") != "pending":
                continue
            if item.get("thread_id") != thread_id:
                continue
            if item_type and item.get("type") != item_type:
                continue
            if step is not None and int(item.get("step") or -1) != step:
                continue
            if tool_name and item.get("tool_name") != tool_name:
                continue
            return dict(item)
        return None

    def resolve(self, item_id: str, *, resolution: Dict[str, Any], status: str = "resolved") -> Optional[Dict[str, Any]]:
        return self.update(item_id, status=status, resolution=resolution, resolved_at=_utc_now())

    @staticmethod
    def default_allowed_actions(item_type: str) -> List[str]:
        if item_type == "conflict_decision":
            return ["choose"]
        if item_type == "draft_review":
            return ["approve", "reject", "edit"]
        return ["approve", "reject", "edit", "respond"]


class ThreadStore(JsonListStore):
    storage_key = "threads"

    def create_or_replace(self, thread: Dict[str, Any]) -> Dict[str, Any]:
        record = dict(thread)
        now = _utc_now()
        record.setdefault("created_at", now)
        record["updated_at"] = now
        record.setdefault("messages", [])
        record.setdefault("status", "ready")
        record.setdefault("thread_kind", "free")
        with self._lock:
            items = self._load_items()
            next_items = [item for item in items if item.get("thread_id") != record.get("thread_id")]
            next_items.append(record)
            self._save_items(next_items)
        return dict(record)

    def get(self, thread_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            items = self._load_items()
        for item in items:
            if item.get("thread_id") == thread_id:
                return dict(item)
        return None

    def update(self, thread_id: str, **fields: Any) -> Dict[str, Any]:
        with self._lock:
            items = self._load_items()
            for item in items:
                if item.get("thread_id") == thread_id:
                    item.update(fields)
                    item["updated_at"] = _utc_now()
                    self._save_items(items)
                    return dict(item)
            record = {"thread_id": thread_id, **fields}
            return self.create_or_replace(record)

    def list(self, *, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            items = self._load_items()
        items.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return [dict(item) for item in items[: max(1, limit)]]

    def append_message(self, thread_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        thread = self.get(thread_id) or {"thread_id": thread_id, "messages": []}
        messages = list(thread.get("messages") or [])
        messages.append(message)
        thread["messages"] = messages
        thread_copy = dict(thread)
        thread_copy.pop("thread_id", None)
        return self.update(thread_id, **thread_copy)


class TimelineStore:
    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self._lock = RLock()

    def _load(self) -> Dict[str, Any]:
        if not self.storage_path.exists():
            return {"generated_at": _utc_now(), "threads": {}}
        try:
            return json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            return {"generated_at": _utc_now(), "threads": {}}

    def _save(self, payload: Dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(payload)
        payload["generated_at"] = _utc_now()
        self.storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list(self, thread_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            payload = self._load()
        threads = payload.get("threads") or {}
        events = threads.get(thread_id) or []
        return [dict(item) for item in events]

    def append(self, thread_id: str, event: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            payload = self._load()
            threads = payload.setdefault("threads", {})
            events = list(threads.get(thread_id) or [])
            record = {
                "id": event.get("id") or uuid.uuid4().hex,
                "timestamp": event.get("timestamp") or _utc_now(),
                **event,
            }
            events.append(record)
            threads[thread_id] = events
            self._save(payload)
        return dict(record)

    def replace(self, thread_id: str, events: List[Dict[str, Any]]) -> None:
        with self._lock:
            payload = self._load()
            payload.setdefault("threads", {})[thread_id] = events
            self._save(payload)

    def clear(self, thread_id: Optional[str] = None) -> None:
        with self._lock:
            if thread_id is None:
                self._save({"threads": {}})
                return
            payload = self._load()
            payload.setdefault("threads", {}).pop(thread_id, None)
            self._save(payload)


class RunStore(JsonListStore):
    storage_key = "runs"

    def append(self, thread_id: str, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex,
            "thread_id": thread_id,
            "event": event,
            "timestamp": _utc_now(),
            "payload": payload,
        }
        with self._lock:
            items = self._load_items()
            items.append(record)
            self._save_items(items[-1000:])
        return dict(record)

    def list(self, thread_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            items = self._load_items()
        if thread_id:
            items = [item for item in items if item.get("thread_id") == thread_id]
        items.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        return [dict(item) for item in items[: max(1, limit)]]


class ApprovalStore:
    """Legacy compatibility wrapper over the unified work-item store."""

    def __init__(self, storage_path: Path) -> None:
        self._store = WorkItemStore(storage_path)

    def create(self, **fields: Any) -> Dict[str, Any]:
        fields.setdefault("type", "approval")
        return self._store.create(**fields)

    def list(self, status: Optional[str] = None, thread_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        return self._store.list(status=status, thread_id=thread_id, item_type="approval", limit=limit)

    def get(self, approval_id: str) -> Optional[Dict[str, Any]]:
        item = self._store.get(approval_id)
        if item and item.get("type") == "approval":
            return item
        return None

    def find_pending(self, thread_id: str, tool_name: str, step: int) -> Optional[Dict[str, Any]]:
        return self._store.find_pending(thread_id=thread_id, item_type="approval", step=step, tool_name=tool_name)

    def update(self, approval_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        return self._store.update(approval_id, **fields)
