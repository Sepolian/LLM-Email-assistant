from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional
import uuid


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", (value or "unknown").strip().lower()).strip("-") or "unknown"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _overlap_score(query: str, content: str) -> int:
    query_tokens = {token for token in re.findall(r"[a-z0-9_@.-]+", _normalize_text(query)) if len(token) > 1}
    if not query_tokens:
        return 0
    content_tokens = set(re.findall(r"[a-z0-9_@.-]+", _normalize_text(content)))
    return len(query_tokens & content_tokens)


@dataclass
class MemoryRecord:
    id: str
    created_at: str
    user_id: str
    thread_id: str
    type: str
    scope: str
    scope_id: Optional[str]
    confidence: float
    source: str
    content: str
    path: Path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "user_id": self.user_id,
            "thread_id": self.thread_id,
            "type": self.type,
            "scope": self.scope,
            "scope_id": self.scope_id,
            "confidence": self.confidence,
            "source": self.source,
            "content": self.content,
            "path": str(self.path),
        }


class MarkdownMemoryStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = Path(root_dir)
        self._lock = RLock()

    def _user_dir(self, user_id: str) -> Path:
        return self.root_dir / _slug(user_id)

    def _note_path(self, user_id: str, memory_type: str, memory_id: str) -> Path:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        return self._user_dir(user_id) / _slug(memory_type) / month / f"{memory_id}.md"

    def _serialize(self, record: MemoryRecord) -> str:
        metadata = {
            "id": record.id,
            "created_at": record.created_at,
            "user_id": record.user_id,
            "thread_id": record.thread_id,
            "type": record.type,
            "scope": record.scope,
            "scope_id": record.scope_id,
            "confidence": record.confidence,
            "source": record.source,
        }
        return (
            "---\n"
            f"{json.dumps(metadata, ensure_ascii=False, indent=2)}\n"
            "---\n\n"
            f"{record.content.strip()}\n"
        )

    def _parse(self, path: Path) -> Optional[MemoryRecord]:
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            return None
        if not raw.startswith("---\n"):
            return None
        metadata_text, separator, body = raw[4:].partition("\n---\n")
        if not separator:
            return None
        try:
            metadata = json.loads(metadata_text)
        except Exception:
            return None
        content = body.strip()
        return MemoryRecord(
            id=metadata.get("id") or path.stem,
            created_at=metadata.get("created_at") or _utc_now(),
            user_id=metadata.get("user_id") or "unknown",
            thread_id=metadata.get("thread_id") or "",
            type=metadata.get("type") or "episodic",
            scope=metadata.get("scope") or "thread",
            scope_id=metadata.get("scope_id"),
            confidence=float(metadata.get("confidence") or 0.0),
            source=metadata.get("source") or "unknown",
            content=content,
            path=path,
        )

    def add_candidate(self, user_id: str, thread_id: str, candidate: Dict[str, Any]) -> Dict[str, Any]:
        memory_id = uuid.uuid4().hex
        record = MemoryRecord(
            id=memory_id,
            created_at=_utc_now(),
            user_id=user_id,
            thread_id=thread_id,
            type=(candidate.get("type") or "episodic"),
            scope=(candidate.get("scope") or "thread"),
            scope_id=candidate.get("scope_id"),
            confidence=float(candidate.get("confidence") or 0.0),
            source=(candidate.get("source") or "agent"),
            content=(candidate.get("content") or "").strip(),
            path=self._note_path(user_id, candidate.get("type") or "episodic", memory_id),
        )
        if not record.content:
            return {}
        with self._lock:
            record.path.parent.mkdir(parents=True, exist_ok=True)
            record.path.write_text(self._serialize(record), encoding="utf-8")
        return record.to_dict()

    def write_candidates(self, user_id: str, thread_id: str, candidates: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        written: List[Dict[str, Any]] = []
        seen = set()
        for candidate in candidates:
            key = (
                candidate.get("type"),
                candidate.get("scope"),
                candidate.get("scope_id"),
                _normalize_text(candidate.get("content") or ""),
            )
            if not key[-1] or key in seen:
                continue
            seen.add(key)
            record = self.add_candidate(user_id=user_id, thread_id=thread_id, candidate=candidate)
            if record:
                written.append(record)
        return written

    def list(self, user_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        user_dir = self._user_dir(user_id)
        if not user_dir.exists():
            return []
        records: List[MemoryRecord] = []
        for path in sorted(user_dir.rglob("*.md"), reverse=True):
            parsed = self._parse(path)
            if parsed:
                records.append(parsed)
        records.sort(key=lambda item: item.created_at, reverse=True)
        return [record.to_dict() for record in records[: max(1, limit)]]

    def search(
        self,
        user_id: str,
        query: Optional[str] = None,
        scope: Optional[str] = None,
        scope_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        records = self.list(user_id=user_id, limit=500)
        filtered: List[Dict[str, Any]] = []
        for record in records:
            if scope and record.get("scope") != scope:
                continue
            if scope_id and record.get("scope_id") != scope_id:
                continue
            filtered.append(record)

        if query:
            filtered.sort(
                key=lambda item: (
                    _overlap_score(query, f"{item.get('content', '')} {item.get('scope_id', '') or ''}"),
                    item.get("created_at", ""),
                ),
                reverse=True,
            )
        else:
            filtered.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return filtered[: max(1, limit)]

    def build_context(
        self,
        user_id: str,
        query: Optional[str] = None,
        scope_hints: Optional[Iterable[str]] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        notes = self.search(user_id=user_id, query=query, limit=limit)
        hinted: List[Dict[str, Any]] = []
        hints = [hint for hint in (scope_hints or []) if hint]
        if hints:
            known_ids = {note.get("id") for note in notes}
            for hint in hints:
                for note in self.search(user_id=user_id, query=hint, limit=2):
                    if note.get("id") in known_ids:
                        continue
                    hinted.append(note)
                    known_ids.add(note.get("id"))
        combined = (notes + hinted)[: max(1, limit)]
        return {
            "query": query,
            "notes": combined,
            "count": len(combined),
        }
