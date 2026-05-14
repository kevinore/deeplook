"""
Parse health evaluation AI response safely.
Returns default (zero adjustments) on any parse failure.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_CONFIANZA_VALID = {"alta", "media", "baja"}


def parse_health_eval_response(raw: str) -> dict:
    """
    Parse AI JSON → health evaluation adjustments dict.

    Returns safe defaults (0 adjustments) on parse failure so the
    deterministic base score is used unchanged.
    """
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("health_eval parse error: %s | raw: %.200s", exc, raw)
        return _default()

    def _clamp_int(val, lo: int = -15, hi: int = 15) -> int:
        try:
            return max(lo, min(hi, int(float(val))))
        except (TypeError, ValueError):
            return 0

    sent_adj = _clamp_int(data.get("sentimiento_ajuste", 0))
    qual_adj = _clamp_int(data.get("calidad_ajuste", 0))
    confianza = str(data.get("confianza", "media")).lower().strip()
    if confianza not in _CONFIANZA_VALID:
        confianza = "media"

    return {
        "sentimiento_ajuste": sent_adj,
        "sentimiento_razon": str(data.get("sentimiento_razon", ""))[:300],
        "calidad_ajuste": qual_adj,
        "calidad_razon": str(data.get("calidad_razon", ""))[:300],
        "confianza": confianza,
        "ai_applied": True,
    }


def _default() -> dict:
    return {
        "sentimiento_ajuste": 0,
        "sentimiento_razon": "",
        "calidad_ajuste": 0,
        "calidad_razon": "",
        "confianza": "baja",
        "ai_applied": False,
    }
