"""Rule management and processed-email tracking for auto labeling."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class AutoLabelRule:
    id: str
    label: str
    reason: str
    label_id: Optional[str]
    created_at: str

    @classmethod
    def create(cls, label: str, reason: str, label_id: Optional[str] = None) -> "AutoLabelRule":
        return cls(
            id=uuid.uuid4().hex,
            label=label,
            reason=reason,
            label_id=label_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )


class RuleManager:
    def __init__(self, storage_path: Path, default_enabled: bool = False) -> None:
        self.storage_path = storage_path
        self.default_enabled = default_enabled
        self._lock = Lock()
        self._state: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.storage_path.exists():
            return {"automation_enabled": self.default_enabled, "rules": []}
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
            payload.setdefault("automation_enabled", self.default_enabled)
            payload.setdefault("rules", [])
            return payload
        except Exception:
            return {"automation_enabled": self.default_enabled, "rules": []}

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("w", encoding="utf-8") as fh:
            json.dump(self._state, fh, ensure_ascii=False, indent=2)

    def list_rules(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(rule) for rule in self._state.get("rules", [])]

    def add_rule(self, label: str, reason: str, label_id: Optional[str] = None) -> Dict[str, Any]:
        rule = AutoLabelRule.create(label=label, reason=reason, label_id=label_id)
        with self._lock:
            rules = self._state.setdefault("rules", [])
            rules.append(asdict(rule))
            self._save()
            return dict(rules[-1])

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            rules = self._state.get("rules", [])
            initial = len(rules)
            self._state["rules"] = [r for r in rules if r.get("id") != rule_id]
            if len(self._state["rules"]) != initial:
                self._save()
                return True
            return False

    def update_rule(self, rule_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        with self._lock:
            for rule in self._state.get("rules", []):
                if rule.get("id") == rule_id:
                    rule.update({k: v for k, v in fields.items() if v is not None})
                    self._save()
                    return dict(rule)
        return None

    def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for rule in self._state.get("rules", []):
                if rule.get("id") == rule_id:
                    return dict(rule)
        return None

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "automation_enabled": bool(self._state.get("automation_enabled", self.default_enabled)),
                "rules": [dict(rule) for rule in self._state.get("rules", [])],
            }

    def set_automation_enabled(self, enabled: bool) -> Dict[str, Any]:
        with self._lock:
            self._state["automation_enabled"] = bool(enabled)
            self._save()
            return self.get_state()

    def automation_enabled(self) -> bool:
        with self._lock:
            return bool(self._state.get("automation_enabled", self.default_enabled))


class ProcessedEmailStore:
    def __init__(self, storage_path: Path, max_age_days: int = 30, max_entries: int = 2000) -> None:
        self.storage_path = storage_path
        self.max_age_days = max_age_days
        self.max_entries = max_entries
        self._lock = Lock()
        self._state = self._load()

    def _load(self) -> Dict[str, str]:
        if not self.storage_path.exists():
            return {}
        try:
            return json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("w", encoding="utf-8") as fh:
            json.dump(self._state, fh, ensure_ascii=False, indent=2)

    def _prune_locked(self) -> None:
        if not self._state:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)
        self._state = {mid: ts for mid, ts in self._state.items() if _is_recent(ts, cutoff)}
        if len(self._state) > self.max_entries:
            # Keep the newest entries only
            sorted_items = sorted(self._state.items(), key=lambda item: item[1], reverse=True)
            self._state = dict(sorted_items[: self.max_entries])

    def mark_processed(self, message_id: str) -> None:
        with self._lock:
            self._state[message_id] = datetime.now(timezone.utc).isoformat()
            self._prune_locked()
            self._save()

    def is_processed(self, message_id: str) -> bool:
        with self._lock:
            return message_id in self._state

    def reset(self) -> None:
        with self._lock:
            self._state = {}
            self._save()


def _is_recent(timestamp: str, cutoff: datetime) -> bool:
    try:
        mark = datetime.fromisoformat(timestamp)
        if mark.tzinfo is None:
            mark = mark.replace(tzinfo=timezone.utc)
    except Exception:
        return False
    return mark >= cutoff
