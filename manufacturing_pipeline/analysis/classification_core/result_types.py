from __future__ import annotations

from typing import Any, Dict, Optional


Step0Result = Dict[str, Any]


def _result(
    *,
    label: str,
    step: str,
    method: str,
    confidence: float,
    fallthrough: bool,
    reason: str,
    features: Optional[Dict[str, Any]] = None,
) -> Step0Result:
    return {
        "label": label,
        "step": step,
        "method": method,
        "confidence": confidence,
        "fallthrough": fallthrough,
        "reason": reason,
        "features": features or {},
    }
