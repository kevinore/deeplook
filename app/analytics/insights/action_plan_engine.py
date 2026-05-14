"""
Deterministic action plan signal engine.

Scans ~14 rules against aggregated report metrics and individual
ConversationAnalysisResult objects. Returns up to 5 ActionSignal objects
sorted by severity — the AI prompt layer converts these into readable text.

Rules:
  V1 velocidad_cotizacion — QRT much slower for lost vs won deals
  V2 hora_critica         — specific hour 3× slower than daily average
  V3 primera_respuesta    — overall first RT > 5 min
  C1 sin_responder        — unanswered conversations (with insistence context)
  C2 cobertura_baja       — low operational coverage score
  F1 cobertura_cotizacion — interested clients who never got a price
  F2 pipeline_estancado   — pending deals open too many days
  F3 razon_perdida        — 50%+ of losses share one root cause
  F4 seguimiento          — no follow-up or follow-up too late after price
  R1 clientes_nuevos      — new clients wait much longer than returning ones
  Q1 calidad_dimension    — specific quality dimension below 6/10
  Q2 sentimiento_negativo — high negative sentiment percentage
  Q3 insistencia          — clients who kept sending unanswered messages
  Q4 tasa_conversion_baja — overall conversion below 20%
"""
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from app.models.enums import ConversionStatus, Sentiment
from app.models.schemas import ConversationAnalysisResult


def _fmt_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        m = int(seconds / 60)
        return f"{m} min"
    return f"{seconds / 3600:.1f}h"


@dataclass
class ActionSignal:
    rule_id: str
    category: str            # "velocidad" | "cobertura" | "embudo" | "calidad"
    severity: float          # 0–10; higher = more urgent
    data: dict               # all specific numbers the AI will reference
    fallback_title: str      # used when AI call fails
    fallback_steps: list[str] = field(default_factory=list)


def detect_signals(
    results: list[ConversationAnalysisResult],
    metrics: dict,           # aggregated values from pdf_generator (see below)
) -> list[ActionSignal]:
    """
    Run all rules and return up to 5 signals sorted by severity desc.

    `metrics` keys expected (all optional — rules skip gracefully when absent):
      median_first_rt, total_unanswered, by_hour_data, health_score,
      qrt_speed_ratio, median_qrt_converted, median_qrt_lost,
      median_qrt_converted_str, median_qrt_lost_str,
      quote_coverage_rate, quote_to_close_rate,
      intent_count, quoted_count, funnel_lost_count,
      funnel_lost_convs (list of results), funnel_pending_count,
      avg_followup_lost, followup_delay_distribution,
      frt_multiplier, median_frt_new_clients_str, median_frt_returning_clients_str,
      new_client_count, returning_client_count,
      avg_quality, conversion_rate,
      op_cov_values (list of floats),
      positive_pct, negative_pct,
      total_conversations,
    """
    signals: list[ActionSignal] = []
    now = datetime.utcnow()

    # ── V1: QRT speed gap (price delivery speed predicts closings) ─────────
    qrt_ratio = metrics.get("qrt_speed_ratio")
    if qrt_ratio and qrt_ratio >= 2.0:
        lost_count = metrics.get("funnel_lost_count", 0)
        signals.append(ActionSignal(
            rule_id="velocidad_cotizacion",
            category="velocidad",
            severity=min(10.0, 4.0 + qrt_ratio * 0.9),
            data={
                "ratio": qrt_ratio,
                "tiempo_ganados": metrics.get("median_qrt_converted_str", "N/D"),
                "tiempo_perdidos": metrics.get("median_qrt_lost_str", "N/D"),
                "perdidos_count": lost_count,
                "intent_count": metrics.get("intent_count", 0),
            },
            fallback_title="Responde más rápido cuando un cliente pregunta el precio",
            fallback_steps=[
                "Prepara plantillas de precio por cada servicio para responder en segundos",
                "Define regla interna: máximo 30 minutos para enviar cualquier cotización",
                "Prioriza las conversaciones con preguntas de precio sobre cualquier otra tarea",
            ],
        ))

    # ── V2: Specific critical hour ─────────────────────────────────────────
    by_hour = metrics.get("by_hour_data", {})
    if len(by_hour) >= 3:
        avg_all = statistics.mean(by_hour.values())
        slowest_h = max(by_hour, key=lambda h: by_hour[h])
        slowest_v = by_hour[slowest_h]
        ratio_h = slowest_v / avg_all if avg_all > 0 else 1
        if ratio_h >= 2.5:
            h_label = f"{'12' if slowest_h == 12 else slowest_h} {'AM' if slowest_h < 12 else 'PM'}"
            signals.append(ActionSignal(
                rule_id="hora_critica",
                category="velocidad",
                severity=min(8.0, 3.0 + ratio_h * 0.8),
                data={
                    "hora": h_label,
                    "tiempo_hora": _fmt_seconds(slowest_v),
                    "tiempo_promedio": _fmt_seconds(avg_all),
                    "ratio": round(ratio_h, 1),
                },
                fallback_title=f"Refuerza la cobertura a las {h_label}",
                fallback_steps=[
                    f"Asigna atención prioritaria a WhatsApp en el horario de las {h_label}",
                    "Revisa si hay reuniones o tareas que bloqueen las respuestas en ese horario",
                    "Considera activar una respuesta automática temporal si no puedes atender",
                ],
            ))

    # ── V3: Overall first response too slow ────────────────────────────────
    frt = metrics.get("median_first_rt")
    if frt and frt > 300 and not any(s.rule_id == "velocidad_cotizacion" for s in signals):
        signals.append(ActionSignal(
            rule_id="primera_respuesta",
            category="velocidad",
            severity=min(8.0, 3.0 + (frt - 300) / 600),
            data={"tiempo": _fmt_seconds(frt), "segundos": int(frt)},
            fallback_title="Reduce el tiempo de primera respuesta",
            fallback_steps=[
                "Configura notificaciones push activas en WhatsApp Business",
                "Activa respuesta automática de bienvenida mientras el equipo llega",
                "Define un responsable específico para responder en las primeras horas del día",
            ],
        ))

    # ── C1: Unanswered conversations ────────────────────────────────────────
    total_unanswered = metrics.get("total_unanswered", 0)
    if total_unanswered > 0:
        insistent = [
            r for r in results
            if r.unanswered_count > 0 and r.trailing_inbound_messages >= 2
        ]
        signals.append(ActionSignal(
            rule_id="sin_responder",
            category="cobertura",
            severity=min(10.0, 5.0 + total_unanswered * 1.5),
            data={
                "total": total_unanswered,
                "insistentes": len(insistent),
                "nombres": [r.contact_name or r.contact_phone or "Desconocido"
                            for r in insistent[:3]],
            },
            fallback_title="Responde las conversaciones pendientes hoy mismo",
            fallback_steps=[
                f"Abre WhatsApp Business y responde las {total_unanswered} conversación(es) pendientes",
                "Ofrece disculpa breve + acción concreta (cita, información, precio)",
                "Activa notificaciones para que esto no vuelva a ocurrir",
            ],
        ))

    # ── C2: Low operational coverage ────────────────────────────────────────
    op_cov = metrics.get("avg_operational_coverage")
    if op_cov is not None and op_cov < 75:
        signals.append(ActionSignal(
            rule_id="cobertura_baja",
            category="cobertura",
            severity=min(7.5, (75 - op_cov) / 5),
            data={"pct": round(op_cov, 1)},
            fallback_title="Mejora la cobertura de respuesta en horario laboral",
            fallback_steps=[
                "Revisa qué horas del día laboral tienen más mensajes sin respuesta",
                "Asigna turnos de atención WhatsApp durante todo el horario (8 AM–6 PM)",
                "Configura respuesta automática de 'en breve te atendemos' para picos de volumen",
            ],
        ))

    # ── F1: Low quote coverage ──────────────────────────────────────────────
    qcr = metrics.get("quote_coverage_rate")
    intent_count = metrics.get("intent_count", 0)
    quoted_count = metrics.get("quoted_count", 0)
    if qcr is not None and qcr < 80 and intent_count >= 3:
        sin_precio = intent_count - quoted_count
        signals.append(ActionSignal(
            rule_id="cobertura_cotizacion",
            category="embudo",
            severity=min(9.0, (80 - qcr) / 5 + sin_precio * 0.8),
            data={
                "pct_cobertura": qcr,
                "sin_precio": sin_precio,
                "total_intent": intent_count,
            },
            fallback_title="Asegúrate de responder SIEMPRE con el precio",
            fallback_steps=[
                "Revisa las conversaciones con intención donde no enviaste precio",
                "Crea una lista de precios actualizada para responder sin demora",
                "Define como regla: toda consulta de precio recibe respuesta en menos de 1h",
            ],
        ))

    # ── F2: Stale pipeline ──────────────────────────────────────────────────
    pending_intent = [
        r for r in results
        if r.intent_stage in ("pending", "quoted", "negotiating") and r.intent_first_at
    ]
    if pending_intent:
        # Strip tzinfo so naive - naive subtraction works regardless of DB tz storage
        days_list = [
            (now - (r.intent_first_at.replace(tzinfo=None) if r.intent_first_at.tzinfo else r.intent_first_at)).days
            for r in pending_intent
        ]
        avg_days = round(statistics.mean(days_list), 1) if days_list else 0
        if avg_days >= 3 or len(pending_intent) >= 3:
            stage_ctr = Counter(r.intent_stage for r in pending_intent)
            signals.append(ActionSignal(
                rule_id="pipeline_estancado",
                category="embudo",
                severity=min(8.5, len(pending_intent) * 1.2 + avg_days * 0.3),
                data={
                    "count": len(pending_intent),
                    "avg_days": avg_days,
                    "etapas": dict(stage_ctr),
                    "nombres": [r.contact_name or r.contact_phone or "Cliente"
                                for r in pending_intent[:3]],
                },
                fallback_title="Reactiva los clientes con propuesta sin cierre",
                fallback_steps=[
                    "Envía un mensaje de seguimiento a cada cliente pendiente hoy",
                    "Ofrece una ventaja adicional (descuento, fecha especial) para incentivar la decisión",
                    "Si no responden en 72h, márcalos como inactivos y actualiza tu pipeline",
                ],
            ))

    # ── F3: Dominant lost reason ────────────────────────────────────────────
    funnel_lost_convs = metrics.get("funnel_lost_convs", [])
    if len(funnel_lost_convs) >= 2:
        reason_ctr = Counter(r.lost_reason for r in funnel_lost_convs if r.lost_reason)
        if reason_ctr:
            top_reason, top_count = reason_ctr.most_common(1)[0]
            ratio_loss = top_count / len(funnel_lost_convs)
            if ratio_loss >= 0.5 or top_count >= 3:
                label_map = {
                    "price": "precio alto",
                    "competition": "competencia",
                    "timing": "mal momento",
                    "no_reply": "sin respuesta post-seguimiento",
                    "changed_mind": "cambio de opinión",
                    "other": "otro motivo",
                }
                signals.append(ActionSignal(
                    rule_id="razon_perdida",
                    category="embudo",
                    severity=min(8.0, 4.0 + top_count * 0.8),
                    data={
                        "razon": label_map.get(top_reason, top_reason),
                        "razon_key": top_reason,
                        "count": top_count,
                        "total_lost": len(funnel_lost_convs),
                        "pct": round(ratio_loss * 100),
                    },
                    fallback_title=f"Aborda el problema de {label_map.get(top_reason, top_reason)}",
                    fallback_steps=[
                        "Analiza si el precio está alineado con el valor que percibes que ofreces",
                        "Prepara una respuesta de valor para clientes que mencionen precio o competencia",
                        "Ofrece opciones de pago flexibles en la cotización",
                    ],
                ))

    # ── F4: Missing or late follow-up ───────────────────────────────────────
    fup_delay_med = metrics.get("median_followup_delay_hours")
    no_followup_count = quoted_count - len([
        r for r in results
        if r.quote_sent_at and (r.post_quote_followup_count or 0) > 0
    ])
    if (fup_delay_med and fup_delay_med > 24) or no_followup_count >= 3:
        signals.append(ActionSignal(
            rule_id="seguimiento",
            category="embudo",
            severity=min(7.5, 3.0 + (no_followup_count * 0.8) + (max(0, (fup_delay_med or 0) - 24) * 0.05)),
            data={
                "sin_seguimiento": no_followup_count,
                "demora_mediana": f"{fup_delay_med:.1f}h" if fup_delay_med else "N/D",
                "cotizaciones": quoted_count,
            },
            fallback_title="Haz seguimiento después de enviar el precio",
            fallback_steps=[
                "Agenda un recordatorio de 24h después de cada cotización enviada",
                f"Revisa las {no_followup_count} cotizaciones sin seguimiento y escríbeles hoy",
                "Usa un mensaje corto y natural: '¿Pudiste revisar la propuesta? ¿Tienes alguna duda?'",
            ],
        ))

    # ── R1: New clients wait much longer than returning ────────────────────
    frt_mult = metrics.get("frt_multiplier")
    if frt_mult and frt_mult >= 2.0:
        signals.append(ActionSignal(
            rule_id="clientes_nuevos",
            category="calidad",
            severity=min(7.0, 2.0 + frt_mult * 0.8),
            data={
                "multiplicador": frt_mult,
                "tiempo_nuevos": metrics.get("median_frt_new_clients_str", "N/D"),
                "tiempo_habituales": metrics.get("median_frt_returning_clients_str", "N/D"),
                "nuevos_count": metrics.get("new_client_count", 0),
            },
            fallback_title="Mejora la atención a clientes nuevos",
            fallback_steps=[
                "Identifica las consultas de primeros contactos y dales prioridad",
                "Crea un protocolo de bienvenida: respuesta en <10 min para clientes nuevos",
                "La primera impresión determina si el cliente regresa — no la descuides",
            ],
        ))

    # ── Q1: Lowest quality dimension ───────────────────────────────────────
    quality_results = [r for r in results if r.quality_breakdown and r.unanswered_count == 0]
    if quality_results:
        dim_avgs = {}
        for dim in ("helpfulness", "tone", "completeness"):
            scores = [getattr(r.quality_breakdown, dim) for r in quality_results]
            dim_avgs[dim] = statistics.mean(scores) if scores else 0.0
        worst_dim = min(dim_avgs, key=lambda d: dim_avgs[d])
        worst_val = dim_avgs[worst_dim]
        if worst_val < 6.5:
            labels = {"helpfulness": "Utilidad", "tone": "Tono", "completeness": "Completitud"}
            signals.append(ActionSignal(
                rule_id="calidad_dimension",
                category="calidad",
                severity=min(7.0, (6.5 - worst_val) * 1.5 + 2.0),
                data={
                    "dimension": labels[worst_dim],
                    "dimension_key": worst_dim,
                    "valor": round(worst_val, 1),
                    "otras": {labels[k]: round(v, 1) for k, v in dim_avgs.items() if k != worst_dim},
                },
                fallback_title=f"Mejora la {labels[worst_dim].lower()} de tus respuestas",
                fallback_steps=[
                    f"Revisa las conversaciones con puntaje de {labels[worst_dim].lower()} más bajo",
                    "Crea una guía de respuesta que incluya siempre precio + disponibilidad + próximo paso",
                    "Practica respuestas completas — el cliente no debería necesitar preguntar dos veces",
                ],
            ))

    # ── Q2: High negative sentiment ────────────────────────────────────────
    neg_pct = metrics.get("negative_pct", 0)
    total_conv = metrics.get("total_conversations", 0)
    if neg_pct > 20 and total_conv >= 5:
        with_sentiment = [r for r in results if r.sentiment == Sentiment.NEGATIVE]
        neg_topics = Counter(r.primary_topic for r in with_sentiment if r.primary_topic)
        top_neg_topic = neg_topics.most_common(1)[0][0] if neg_topics else None
        signals.append(ActionSignal(
            rule_id="sentimiento_negativo",
            category="calidad",
            severity=min(7.5, neg_pct / 5),
            data={
                "pct": round(neg_pct),
                "count": len(with_sentiment),
                "tema_principal": top_neg_topic,
            },
            fallback_title="Reduce la insatisfacción del cliente",
            fallback_steps=[
                "Revisa las conversaciones con sentimiento negativo y detecta el patrón",
                "Implementa un protocolo de manejo de quejas: escuchar, disculparse, resolver",
                "Haz seguimiento proactivo a los clientes que expresaron insatisfacción",
            ],
        ))

    # ── Q4: Low overall conversion ─────────────────────────────────────────
    conv_rate = metrics.get("conversion_rate", 0)
    applicable_count = metrics.get("applicable_count", 0)
    if conv_rate < 20 and applicable_count >= 5:
        signals.append(ActionSignal(
            rule_id="tasa_conversion_baja",
            category="embudo",
            severity=min(7.0, (20 - conv_rate) / 3),
            data={
                "tasa": conv_rate,
                "aplicables": applicable_count,
                "benchmark": "35–42%",
            },
            fallback_title="Mejora tu proceso de cierre de ventas",
            fallback_steps=[
                "Simplifica el proceso: precio + cita en el mismo mensaje de respuesta",
                "Ofrece opciones concretas ('¿te acomoda el martes o el jueves?')",
                "Envía un mensaje de seguimiento 24h después si el cliente no confirmó",
            ],
        ))

    signals.sort(key=lambda s: -s.severity)
    return signals[:5]
