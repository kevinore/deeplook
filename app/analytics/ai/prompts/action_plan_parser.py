"""
Parse the action plan AI JSON response safely.
Falls back to empty list on any error — caller handles fallback.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_VALID_URGENCY = {"urgente", "esta_semana", "este_mes"}

_URGENCY_LABEL = {
    "urgente":      "🔴 Urgente",
    "esta_semana":  "🟡 Esta semana",
    "este_mes":     "🟢 Este mes",
}

_URGENCY_COLOR = {
    "urgente":      "red",
    "esta_semana":  "amber",
    "este_mes":     "green",
}


def parse_action_plan_response(raw: str, conversation_id: str = "action_plan") -> list[dict]:
    """
    Parse AI JSON → list of action card dicts.
    Returns [] on failure — caller must fall back to deterministic plan.
    """
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("action_plan parse error: %s | raw: %.200s", exc, raw)
        return []

    plan_raw = data.get("plan", [])
    if not isinstance(plan_raw, list) or not plan_raw:
        return []

    cards = []
    for i, item in enumerate(plan_raw[:3], 1):
        if not isinstance(item, dict):
            continue
        urgencia = str(item.get("urgencia", "esta_semana")).strip()
        if urgencia not in _VALID_URGENCY:
            urgencia = "esta_semana"
        pasos = item.get("pasos", [])
        if not isinstance(pasos, list):
            pasos = []
        cards.append({
            "number":            i,
            "title":             str(item.get("titulo", f"Acción {i}"))[:120],
            "urgency":           urgencia,
            "urgency_label":     _URGENCY_LABEL[urgencia],
            "urgency_color":     _URGENCY_COLOR[urgencia],
            "que_esta_pasando":  str(item.get("que_esta_pasando", ""))[:500],
            "por_que_importa":   str(item.get("por_que_importa", ""))[:300],
            "steps":             [str(s)[:200] for s in pasos[:4]],
            "impact":            str(item.get("impacto_esperado", ""))[:300],
        })

    return cards
