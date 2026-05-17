from __future__ import annotations

from typing import Dict

from llm_email_app.agent.state import AgentMode, RiskLevel


RISK_ORDER: Dict[RiskLevel, int] = {
    "read_only": 0,
    "reversible": 1,
    "external_write": 2,
    "destructive": 3,
}


def normalize_risk_level(value: str) -> RiskLevel:
    candidate = (value or "read_only").strip().lower()
    if candidate in RISK_ORDER:
        return candidate  # type: ignore[return-value]
    return "read_only"


def risk_at_or_below(candidate: RiskLevel, limit: RiskLevel) -> bool:
    return RISK_ORDER[candidate] <= RISK_ORDER[limit]


def should_require_approval(
    mode: AgentMode,
    risk_level: RiskLevel,
    confidence: float,
    min_confidence: float,
    auto_write_risk_limit: RiskLevel,
    shadow_mode: bool,
) -> bool:
    if risk_level == "read_only":
        return False
    if shadow_mode:
        return False
    if mode == "semi_auto":
        return True
    if confidence < min_confidence:
        return True
    return not risk_at_or_below(risk_level, auto_write_risk_limit)
