"""Tests for v4 prompt improvements: P1 (drop speed_perception),
P2 (deterministic facts), P3 (business_type adaptation), P4 (normalised questions)."""
import json

import pytest

from app.analytics.ai.prompts.combined import build_system_prompt, build_user_prompt
from app.analytics.ai.prompts.response_parser import parse_ai_response


# ─── P1: speed_perception dropped from quality_score average ────────────────


def test_quality_score_uses_three_dimensions_only():
    """When AI sends a 4-dim breakdown, quality_score must average only the 3 active dims."""
    payload = json.dumps({
        "sentiment": "neutral",
        "sentiment_score": 0.0,
        "sentiment_reason": "transactional",
        "primary_topic": "precios",
        "secondary_topics": [],
        "quality_score": 4.0,                 # AI averaged 4 dims (incl. speed=2)
        "quality_breakdown": {
            "helpfulness": 6.0,
            "tone": 6.0,
            "completeness": 6.0,
            "speed_perception": 2.0,         # legacy, ignored
        },
        "conversion_status": "pending",
        "summary": "x",
        "key_points": [],
        "customer_questions": [],
    })
    result = parse_ai_response(payload, "conv-x")
    # 3-dim average = (6+6+6)/3 = 6.0; AI sent 4.0. |4.0-6.0|=2.0 > 0.5 → recomputed.
    assert result.quality_score == pytest.approx(6.0, abs=0.05)


def test_quality_score_keeps_ai_score_when_close_to_three_dim_avg():
    """If AI score is within 0.5 of the 3-dim avg, trust the AI (it agreed with us)."""
    payload = json.dumps({
        "sentiment": "neutral",
        "primary_topic": "precios",
        "quality_score": 7.3,
        "quality_breakdown": {"helpfulness": 7.0, "tone": 7.0, "completeness": 7.0},
        "conversion_status": "pending",
    })
    result = parse_ai_response(payload, "conv-x")
    # 3-dim avg = 7.0; AI = 7.3; deviation 0.3 ≤ 0.5 → keep AI's 7.3
    assert result.quality_score == pytest.approx(7.3, abs=0.05)


def test_quality_breakdown_speed_perception_default_when_missing():
    payload = json.dumps({
        "sentiment": "neutral",
        "primary_topic": "precios",
        "quality_breakdown": {"helpfulness": 8.0, "tone": 8.0, "completeness": 8.0},
        "conversion_status": "pending",
    })
    result = parse_ai_response(payload, "conv-x")
    # Default for missing speed_perception is 5.0 — schema-level back-compat.
    assert result.quality_breakdown.speed_perception == 5.0
    # quality_score still derived from the 3 active dims only.
    assert result.quality_score == pytest.approx(8.0, abs=0.05)


# ─── P2: deterministic facts block in user prompt ───────────────────────────


def test_user_prompt_includes_facts_when_stats_provided():
    stats = {
        "first_response_time_seconds": 8400,   # 2.3 h
        "avg_response_time_seconds": 600,      # 10 min
        "total_messages": 12,
        "by_direction": {"inbound": 8, "outbound": 4},
        "is_unanswered": True,
        "is_ghosted": False,
        "last_business_msg_ack": 3,           # READ
        "out_of_hours_inbound_pct": 25.0,
    }
    prompt = build_user_prompt("[10:00] CUSTOMER: hola", stats=stats, business_type="clinica dental")
    assert "HECHOS" in prompt
    assert "2.3h" in prompt
    assert "READ" in prompt
    assert "sí" in prompt          # is_unanswered=true rendered as "sí"
    assert "clinica dental" in prompt


def test_user_prompt_without_stats_is_legacy_format():
    prompt = build_user_prompt("[10:00] CUSTOMER: hola")
    assert "HECHOS" not in prompt
    assert "[10:00]" in prompt


def test_user_prompt_unknown_ack_renders_dash():
    stats = {
        "total_messages": 2,
        "by_direction": {"inbound": 1, "outbound": 1},
        "last_business_msg_ack": None,
    }
    prompt = build_user_prompt("[10:00] CUSTOMER: hi", stats=stats)
    assert "Último ack del negocio: —" in prompt


# ─── P3: business_type adaptation hooks ──────────────────────────────────────


def test_system_prompt_includes_topic_list():
    """System prompt always renders the closed taxonomy."""
    sp = build_system_prompt(None)
    assert "agendar cita" in sp
    assert "consulta general" in sp
    # Velocidad de respuesta no longer in quality_breakdown taxonomy
    assert "speed_perception" not in sp


def test_system_prompt_three_dim_quality_only():
    """Quality breakdown JSON shape in the prompt must list only 3 dimensions."""
    sp = build_system_prompt(None)
    # The prompt's response-format example must NOT instruct the AI to send speed_perception.
    qb_section_marker = '"quality_breakdown": {'
    qb_idx = sp.find(qb_section_marker)
    assert qb_idx != -1, "quality_breakdown section missing in prompt"
    # Snippet around the response format:
    snippet = sp[qb_idx: qb_idx + 400]
    assert "helpfulness" in snippet
    assert "tone" in snippet
    assert "completeness" in snippet
    assert "speed_perception" not in snippet


# ─── P4: customer_questions trimming ─────────────────────────────────────────


def test_customer_questions_strip_whitespace_and_drop_empty():
    payload = json.dumps({
        "sentiment": "neutral",
        "primary_topic": "precios",
        "quality_breakdown": {"helpfulness": 7, "tone": 7, "completeness": 7},
        "conversion_status": "pending",
        "customer_questions": ["  cuánto cuesta  ", "", "tienen disponibilidad"],
    })
    result = parse_ai_response(payload, "conv-x")
    assert result.customer_questions == ["cuánto cuesta", "tienen disponibilidad"]
