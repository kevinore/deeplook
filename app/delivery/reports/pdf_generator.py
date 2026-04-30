"""
PDF report generator: Jinja2 HTML template → WeasyPrint → PDF bytes.
"""
import base64
import logging
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.analytics.insights.alerts import generate_alerts
from app.analytics.insights.health_score import calculate_health_score, explain_health_score, get_health_score_breakdown
from app.analytics.insights.recommendations import (
    generate_headline_recommendations,
    generate_next_steps,
    generate_recommendations,
)
from app.analytics.metrics.response_time import percentile_of_values
from app.delivery.reports.chart_generator import (
    quality_bars_chart,
    response_time_by_hour_chart,
    sentiment_donut_chart,
    topics_bar_chart,
    volume_by_hour_chart,
)
from app.models.enums import ConversionStatus, Sentiment
from app.models.schemas import ConversationAnalysisResult

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Brand logo, embedded as a data URI so the PDF is self-contained (no base_url needed by WeasyPrint).
_LOGO_PATH = Path(__file__).resolve().parents[2] / "logo" / "logo-horizontal-landing.png"
try:
    _LOGO_DATA_URI = "data:image/png;base64," + base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
except OSError:
    _LOGO_DATA_URI = ""  # Logo missing → cover renders without it; not fatal.

# Minimum conversations for a reliable conversion rate
MIN_RELIABLE_CONV = 20

# Default average transaction value by business type (COP)
_DEFAULT_ATV_BY_TYPE: dict[str, float] = {
    "restaurante": 45_000,
    "clinica dental": 150_000,
    "dental": 150_000,
    "salon de belleza": 120_000,
    "belleza": 120_000,
    "gimnasio": 80_000,
    "gym": 80_000,
}


def _fmt_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}min"
    return f"{seconds / 3600:.1f}h"


def _fmt_cop(amount: float) -> str:
    """Format Colombian pesos: $1.900.000 COP."""
    return f"${int(amount):,}".replace(",", ".") + " COP"


def _traffic_light(value: float | None, green_max: float, amber_max: float, higher_is_better: bool = False) -> str:
    """Return 'green', 'amber', or 'red' based on Colombia MiPymes benchmarks."""
    if value is None:
        return "gray"
    if higher_is_better:
        if value >= green_max:
            return "green"
        if value >= amber_max:
            return "amber"
        return "red"
    else:
        if value <= green_max:
            return "green"
        if value <= amber_max:
            return "amber"
        return "red"


def _health_label(score: float) -> str:
    if score >= 85:
        return "Excelente"
    if score >= 70:
        return "Bueno"
    if score >= 55:
        return "Regular"
    if score >= 40:
        return "Deficiente"
    return "Crítico"


def _hour_label(h: int) -> str:
    if h == 0:
        return "12 AM"
    if h < 12:
        return f"{h} AM"
    if h == 12:
        return "12 PM"
    return f"{h - 12} PM"


def _one_line_summary(first_rt_status: str, quality_status: str, conversion_rate: float) -> str:
    if first_rt_status == "red" and quality_status in ("green", "amber"):
        return "Tu atención es de buena calidad, pero respondes demasiado tarde. Esto te está haciendo perder ventas."
    if first_rt_status == "red" and quality_status == "red":
        return "Tu velocidad de respuesta y calidad de atención necesitan mejorar para competir efectivamente."
    if first_rt_status == "green" and conversion_rate < 20:
        return "Respondes rápido pero no logras cerrar ventas. El problema está en el proceso de conversión."
    if first_rt_status == "green" and quality_status in ("green", "amber") and conversion_rate > 30:
        return "Tu operación está funcionando bien. Hay oportunidades de optimización, no de corrección."
    return "Tu operación tiene fortalezas y oportunidades de mejora. Revisa el detalle en las siguientes páginas."


def _conversion_analysis_text(conversion_rate: float, total_unanswered: int, avg_first_rt: float | None) -> str | None:
    if conversion_rate < 15 and total_unanswered > 0:
        plural = "es" if total_unanswered != 1 else ""
        return (
            f"Tu tasa de conversión es baja ({conversion_rate}%) y tienes {total_unanswered} "
            f"conversaci{'ones' if total_unanswered != 1 else 'ón'} sin responder. "
            f"El cuello de botella está en el inicio del proceso: muchos clientes se van antes de recibir respuesta."
        )
    if conversion_rate < 15 and avg_first_rt and avg_first_rt > 3600:
        return (
            f"Tu tasa de conversión es baja ({conversion_rate}%). La causa más probable es tu tiempo de respuesta "
            f"de {_fmt_seconds(avg_first_rt)} — cuando finalmente contestas, el cliente ya compró en otro lugar."
        )
    if 15 <= conversion_rate <= 30:
        return (
            f"Tu tasa de conversión está por debajo del benchmark (35-42%), pero hay una base sobre la cual mejorar. "
            f"Reducir tu tiempo de respuesta y hacer seguimiento proactivo a las conversaciones pendientes puede duplicar esta cifra."
        )
    if conversion_rate > 30:
        return (
            f"Tu tasa de conversión está cerca del benchmark colombiano (35-42%). "
            f"Estás haciendo un buen trabajo cerrando ventas. Enfócate en generar más tráfico de conversaciones."
        )
    return None


def _operational_interpretation(
    business_hours_pct: float | None,
    msgs_per_conv: float,
    top_hour: int | None,
    by_hour_data: dict[int, float],
) -> str | None:
    parts: list[str] = []
    if business_hours_pct is not None and business_hours_pct > 90:
        parts.append(
            f"El {business_hours_pct}% de tus mensajes llegan en horario laboral — "
            f"puedes enfocar tu atención en esas horas sin preocuparte por cubrir fines de semana o madrugadas."
        )
    if msgs_per_conv < 8:
        parts.append(
            f"Tus conversaciones son relativamente cortas ({msgs_per_conv} mensajes vs. 8-15 normal). "
            f"Esto puede indicar que resuelves rápido, o que el cliente se va antes de cerrar la venta."
        )
    if top_hour is not None and by_hour_data.get(top_hour, 0) > 3600:
        parts.append(
            f"Tu hora más activa ({_hour_label(top_hour)}) es también una de tus horas más lentas — "
            f"hay un desajuste entre cuándo llegan los clientes y cuándo estás disponible."
        )
    return " ".join(parts) if parts else None


def _hourly_extremes(by_hour_data: dict[int, float]) -> tuple[str | None, str | None, str | None]:
    """Returns (slowest_text, fastest_text, variability_text)."""
    if not by_hour_data:
        return None, None, None
    slowest_h = max(by_hour_data, key=lambda h: by_hour_data[h])
    fastest_h = min(by_hour_data, key=lambda h: by_hour_data[h])
    slowest_val = by_hour_data[slowest_h]
    fastest_val = by_hour_data[fastest_h]
    slowest_text = f"Tu hora más crítica: {_hour_label(slowest_h)} — tardas en promedio {_fmt_seconds(slowest_val)} en responder."
    fastest_text = f"Tu hora más rápida: {_hour_label(fastest_h)} — respondes en {_fmt_seconds(fastest_val)}."
    diff_hours = (slowest_val - fastest_val) / 3600
    if diff_hours > 10:
        variability_text = (
            f"Hay más de {int(diff_hours)} horas de diferencia entre tu mejor y tu peor momento. "
            f"Esto sugiere que tu atención no es consistente. "
            f"Configurar un horario claro con mensaje automático fuera de horario eliminaría gran parte de esta variabilidad."
        )
    elif (slowest_val - fastest_val) < 3600:
        variability_text = "Tu velocidad es consistente durante todo el día."
    else:
        variability_text = None
    return slowest_text, fastest_text, variability_text


def _select_strategic_conversations(results: list[ConversationAnalysisResult]) -> list[dict]:
    """Select 3 strategic conversations: best, lost opportunity, typical."""
    from app.models.enums import ConversionStatus, Sentiment

    _status_label = {
        "converted": "Convertida",
        "lost": "Oportunidad perdida",
        "pending": "Pendiente",
        "not_applicable": "No aplica",
    }
    _sentiment_label = {"positive": "Positivo", "neutral": "Neutral", "negative": "Negativo"}

    def _make_card(r: ConversationAnalysisResult, category: str, label: str, insight: str) -> dict:
        # Build a recognisable reference so the user can find this exact chat
        # in WhatsApp: contact name (or last 4 digits of phone) + start date.
        ref_parts: list[str] = []
        if r.contact_name and r.contact_name.strip():
            ref_parts.append(r.contact_name.strip())
        elif r.contact_phone:
            tail = r.contact_phone[-4:] if len(r.contact_phone) >= 4 else r.contact_phone
            ref_parts.append(f"Cliente ···{tail}")
        if r.started_at:
            try:
                ref_parts.append(r.started_at.strftime("%d %b %Y, %H:%M"))
            except Exception:
                pass
        reference = " · ".join(ref_parts) if ref_parts else None

        return {
            "category": category,
            "label": label,
            "reference": reference,
            "topic": r.primary_topic or "consulta general",
            "first_rt": _fmt_seconds(r.first_response_time_seconds),
            "quality": f"{r.quality_score:.1f}/10" if r.quality_score is not None else "—",
            "sentiment_label": _sentiment_label.get(r.sentiment.value if r.sentiment else "neutral", "Neutral"),
            "status_label": _status_label.get(r.conversion_status.value if r.conversion_status else "not_applicable", "—"),
            "summary": r.summary or "",
            "insight": insight,
        }

    cards: list[dict] = []
    used_ids: set[int] = set()

    # Card 1 — LA MEJOR
    converted = [r for r in results if r.conversion_status == ConversionStatus.CONVERTED]
    if converted:
        best = max(converted, key=lambda r: r.quality_score or 0)
        lbl = "🟢 LA MEJOR — Conversación convertida"
    else:
        positives = [r for r in results if r.sentiment == Sentiment.POSITIVE]
        candidates = positives or results
        best = max(candidates, key=lambda r: r.quality_score or 0) if candidates else None
        lbl = "🟢 LA MEJOR — Mayor calidad"

    if best:
        used_ids.add(id(best))
        if best.first_response_time_seconds and best.first_response_time_seconds < 300:
            insight = "La respuesta rápida generó confianza inmediata en el cliente."
        elif best.quality_score and best.quality_score >= 9.0:
            insight = "La combinación de información completa y tono profesional cerró la venta."
        else:
            insight = "La asesora invirtió tiempo en resolver dudas técnicas y dar información de valor."
        cards.append(_make_card(best, "LA MEJOR", lbl, insight))

    # Card 2 — OPORTUNIDAD PERDIDA
    pending = [r for r in results if r.conversion_status == ConversionStatus.PENDING and id(r) not in used_ids]
    slow_pending = [r for r in pending if r.first_response_time_seconds and r.first_response_time_seconds > 3600]
    if slow_pending:
        lost_opp = max(slow_pending, key=lambda r: r.first_response_time_seconds or 0)
        lbl2 = "🔴 OPORTUNIDAD PERDIDA — Cliente no respondió"
    elif pending:
        lost_opp = pending[0]
        lbl2 = "🔴 OPORTUNIDAD PERDIDA — Pendiente sin cierre"
    else:
        lost_actual = [r for r in results if r.conversion_status == ConversionStatus.LOST and id(r) not in used_ids]
        lost_opp = lost_actual[0] if lost_actual else None
        lbl2 = "🔴 OPORTUNIDAD PERDIDA — Lead perdido"

    if lost_opp:
        used_ids.add(id(lost_opp))
        if lost_opp.first_response_time_seconds and lost_opp.first_response_time_seconds > 36000:
            insight2 = "El cliente consultó a tu competencia mientras esperaba. Responder en menos de 1 hora podría haber salvado esta venta."
        elif lost_opp.sentiment == Sentiment.NEUTRAL:
            insight2 = "El cliente recibió la información pero no tenía urgencia inmediata. Un seguimiento proactivo podría reactivar el interés."
        else:
            insight2 = "Responder más rápido habría aumentado significativamente la probabilidad de conversión."
        cards.append(_make_card(lost_opp, "OPORTUNIDAD PERDIDA", lbl2, insight2))

    # Card 3 — CASO TÍPICO
    remaining = [r for r in results if id(r) not in used_ids and r.conversion_status == ConversionStatus.PENDING]
    if not remaining:
        remaining = [r for r in results if id(r) not in used_ids]
    if remaining:
        sorted_q = sorted(remaining, key=lambda r: r.quality_score or 0)
        typical = sorted_q[len(sorted_q) // 2]
        lbl3 = "🟡 CASO TÍPICO — Pendiente"
        if typical.duration_minutes and typical.duration_minutes > 2880:  # 48h
            insight3 = "Hacer seguimiento. Un mensaje corto puede reactivar al cliente."
        else:
            insight3 = "La conversación está activa. Ofrece agendar la cita o dar el siguiente paso ahora."
        cards.append(_make_card(typical, "CASO TÍPICO", lbl3, insight3))

    return cards


def _build_action_plan(
    score_breakdown: list[dict],
    health_score: float,
    first_rt_str: str,
    avg_first_rt: float | None,
    conversion_rate: float,
    total_unanswered: int,
    topic_counter: "Counter",
    results: list[ConversationAnalysisResult],
) -> list[dict]:
    """Generate 3 action cards from the 3 worst-performing health score dimensions."""
    sorted_dims = sorted(score_breakdown, key=lambda d: d["pct_of_max"])
    top_3 = sorted_dims[:3]
    actions: list[dict] = []

    for i, dim in enumerate(top_3, 1):
        key = dim["key"]

        if key == "velocidad":
            actions.append({
                "number": i,
                "title": "Reduce tu tiempo de primera respuesta",
                "current_value": f"Tu tiempo actual es {first_rt_str}",
                "target": "Menos de 1 hora (idealmente 5 minutos)",
                "why": "El 65% de los colombianos espera respuesta en menos de 5 minutos. Cada hora que tardas, tu cliente probablemente ya escribió a la competencia.",
                "steps": [
                    "Configura notificaciones push en WhatsApp Business",
                    "Define un horario de atención (ej. 8 AM — 7 PM)",
                    "Activa mensaje automático fuera de horario",
                    "Asigna a alguien responsable de revisar cada hora",
                ],
                "impact": f"Tu puntaje de salud podría subir de {int(health_score)} a ~{min(100, int(health_score) + 14)}.",
            })

        elif key == "cobertura":
            plural = total_unanswered != 1
            actions.append({
                "number": i,
                "title": "Responde todas las conversaciones pendientes",
                "current_value": f"Tienes {total_unanswered} conversaci{'ones' if plural else 'ón'} sin responder",
                "target": "0 conversaciones sin responder",
                "why": "Cada conversación sin respuesta es una venta potencial perdida. El cliente interpretó que no te importó.",
                "steps": [
                    f"Revisa tu WhatsApp Business ahora y responde las {total_unanswered} conversaciones pendientes",
                    "Pide disculpas por la demora de forma breve",
                    "Ofrece una acción concreta (agendar cita, enviar información)",
                    "Implementa un proceso para que esto no vuelva a pasar",
                ],
                "impact": "Cada respuesta puede recuperar una venta. Tu puntaje podría subir varios puntos.",
            })

        elif key == "conversion":
            actions.append({
                "number": i,
                "title": "Mejora tu proceso de cierre de ventas",
                "current_value": f"Solo el {conversion_rate}% de tus conversaciones termina en venta",
                "target": "35-42% (benchmark Colombia MiPymes)",
                "why": "La mayoría de tus clientes muestra interés pero no llega a comprar.",
                "steps": [
                    "Envía un mensaje de seguimiento 24-48h después si el cliente no respondió",
                    "Crea una oferta especial para clientes que preguntan por precios",
                    "Simplifica el proceso: pide solo nombre + fecha de cita en el primer mensaje",
                    "Ofrece agendar la cita directamente en el primer mensaje de respuesta",
                ],
                "impact": f"Pasar del {conversion_rate}% al 25% de conversión puede duplicar tus ventas desde WhatsApp.",
            })

        elif key == "sentimiento":
            with_sentiment = [r for r in results if r.sentiment is not None]
            neg_pct = round(sum(1 for r in with_sentiment if r.sentiment.value == "negative") / len(with_sentiment) * 100) if with_sentiment else 0
            actions.append({
                "number": i,
                "title": "Mejora la experiencia del cliente",
                "current_value": f"El {neg_pct}% de tus conversaciones terminan con cliente insatisfecho",
                "target": "Menos del 10% de conversaciones negativas",
                "why": "Los clientes insatisfechos no vuelven y muchas veces comparten su experiencia con otros.",
                "steps": [
                    "Revisa las conversaciones negativas y entiende la causa raíz",
                    "Capacita a tu equipo en manejo de objeciones comunes",
                    "Implementa un protocolo de respuesta ante quejas",
                    "Haz seguimiento proactivo a clientes que expresaron insatisfacción",
                ],
                "impact": "Reducir conversaciones negativas a menos del 10% mejora tu puntaje significativamente.",
            })

        elif key == "calidad":
            actions.append({
                "number": i,
                "title": "Mejora la calidad de tus respuestas",
                "current_value": "Tu calidad de atención está por debajo del objetivo",
                "target": "7.0/10 o superior en todas las dimensiones",
                "why": "Los clientes valoran respuestas completas, amables y útiles. Una respuesta incompleta genera más preguntas y más demora.",
                "steps": [
                    "Crea plantillas de respuesta para los temas más frecuentes",
                    "Incluye siempre: precio, disponibilidad y próximo paso en tu respuesta",
                    "Usa un tono amigable y profesional, con saludo y despedida",
                    "Verifica que cada respuesta resuelva completamente la pregunta del cliente",
                ],
                "impact": "Mejorar la calidad puede subir tu puntaje en 10-15 puntos en este componente.",
            })

        else:  # cobertura_horaria
            top_topic_name = ""
            if topic_counter:
                top_topic_name = sorted(topic_counter.items(), key=lambda x: -x[1])[0][0]
            top_pct = int(topic_counter.get(top_topic_name, 0) / max(1, sum(topic_counter.values())) * 100) if topic_counter else 0
            actions.append({
                "number": i,
                "title": "Crea respuestas rápidas para tus consultas frecuentes",
                "current_value": f"El {top_pct}% de tus clientes pregunta sobre '{top_topic_name}'" if top_topic_name else "Tus clientes repiten las mismas preguntas",
                "target": "Responder en menos de 1 minuto a consultas frecuentes",
                "why": "Estás escribiendo la misma respuesta una y otra vez — eso es tiempo perdido y respuesta lenta para el cliente.",
                "steps": [
                    "Abre WhatsApp Business → Configuración → Herramientas para la empresa → Respuestas rápidas",
                    f"Crea una respuesta para '{top_topic_name}' con toda la información relevante" if top_topic_name else "Crea respuestas para las consultas más comunes",
                    "Crea un atajo de 2-3 letras (ej. /cita)",
                    "Úsala cada vez que un cliente pregunte sobre este tema",
                ],
                "impact": f"Reducir tu tiempo de respuesta para el {top_pct}% de consultas frecuentes de horas a segundos." if top_pct else "Responder más rápido a las consultas frecuentes mejora tu puntaje de velocidad.",
            })

    return actions


def generate_pdf_report(
    results: list[ConversationAnalysisResult],
    business_name: str,
    job_id: str,
    files_processed: int = 1,
    ai_model: str = "unknown",
    average_transaction_value: float | None = None,
    business_type: str | None = None,
    is_subscribed: bool = False,
    previous_results: list[ConversationAnalysisResult] | None = None,
    previous_job_created_at: datetime | None = None,
) -> bytes:
    """
    Generate a PDF report from analysis results.

    `previous_results`, when provided, drives the F1 "vs reporte anterior"
    comparison block. It should be the analyses from the most recent completed
    job for the same client. If empty/None, the comparison block is omitted.
    """

    # Resolve average_transaction_value from business type default if not provided
    if average_transaction_value is None and business_type:
        bt_lower = business_type.lower().strip()
        for key, val in _DEFAULT_ATV_BY_TYPE.items():
            if key in bt_lower:
                average_transaction_value = val
                break

    # --- Aggregate metrics ---
    total_messages = sum(r.total_messages for r in results)

    # "Sin responder" must match the user's reality in WhatsApp:
    #   • Count UNIQUE chats (deduplicate sessions per contact_phone),
    #     because a single chat may have been split into multiple sessions
    #     and an old session that ended unanswered shouldn't double-count when
    #     the customer has come back later.
    #   • Use only the LATEST session per contact (sessions arrive in
    #     started_at-asc order from the repo, so the last seen per key wins).
    #   • Exclude muted/archived chats — those are intentionally silenced.
    #   • For .txt-uploaded results without a contact_phone, fall back to the
    #     conversation_id so each is treated as its own chat (no dedupe).
    _latest_per_chat: dict[str, ConversationAnalysisResult] = {}
    for r in results:
        if r.wa_is_muted or r.wa_is_archived:
            continue
        key = r.contact_phone or r.conversation_id
        _latest_per_chat[key] = r  # ascending order → last assignment is latest
    total_unanswered = sum(1 for r in _latest_per_chat.values() if r.unanswered_count)

    # First response times
    frt_values = [r.first_response_time_seconds for r in results if r.first_response_time_seconds is not None]
    avg_first_rt = statistics.mean(frt_values) if frt_values else None
    median_first_rt = statistics.median(frt_values) if frt_values else None

    # Avg response times
    rt_values = [r.avg_response_time_seconds for r in results if r.avg_response_time_seconds is not None]
    avg_rt = statistics.mean(rt_values) if rt_values else None
    median_rt = statistics.median(rt_values) if rt_values else None
    # Use proper linear-interpolation percentile (the prior `sorted(...)[int(0.95*n)]`
    # silently returned the max for any sample with n < 20 because int(0.95*n) == n-1)
    p95_rt = percentile_of_values(rt_values, 95.0)

    # F3: First-response-time bucketing — communicates DISTRIBUTION, not just average.
    # An average of "14 min" can hide either "everyone in 14 min" or
    # "half in 1 min, half in 30 min". The histogram makes the truth visible.
    frt_buckets = {
        "lt_5min": 0,      # <5 min  — Excelente
        "5_to_30min": 0,   # 5–30 min — Aceptable
        "30min_to_2h": 0,  # 30 min–2 h — Demora visible
        "gt_2h": 0,        # >2 h    — Muy demorado
        "no_reply": 0,     # nunca respondió
    }
    for r in results:
        if r.first_response_time_seconds is None:
            frt_buckets["no_reply"] += 1
        else:
            sec = r.first_response_time_seconds
            if sec < 300:
                frt_buckets["lt_5min"] += 1
            elif sec < 1800:
                frt_buckets["5_to_30min"] += 1
            elif sec < 7200:
                frt_buckets["30min_to_2h"] += 1
            else:
                frt_buckets["gt_2h"] += 1
    frt_bucket_total = sum(frt_buckets.values()) or 1
    frt_distribution = [
        {"key": k, "label": label, "count": frt_buckets[k],
         "pct": round(frt_buckets[k] / frt_bucket_total * 100, 1),
         "color": color}
        for k, label, color in (
            ("lt_5min",      "<5 min",         "green"),
            ("5_to_30min",   "5–30 min",       "amber"),
            ("30min_to_2h",  "30 min – 2 h",   "amber"),
            ("gt_2h",        ">2 h",           "red"),
            ("no_reply",     "Nunca respondido",  "red"),
        )
    ]

    # ─── Aggregated WAHA-derived deterministic metrics ──────────────────────
    # Each per-conversation rate is averaged across conversations that produced
    # a value (None means "not measurable for that conversation").
    delivery_values = [r.delivery_rate for r in results if r.delivery_rate is not None]
    read_values = [r.read_rate for r in results if r.read_rate is not None]
    avg_delivery_rate = round(sum(delivery_values) / len(delivery_values), 1) if delivery_values else None
    avg_read_rate = round(sum(read_values) / len(read_values), 1) if read_values else None
    ghosted_count = sum(1 for r in results if r.is_ghosted)
    op_cov_values = [r.operational_coverage_score for r in results if r.operational_coverage_score is not None]
    avg_operational_coverage = round(sum(op_cov_values) / len(op_cov_values), 1) if op_cov_values else None
    ooh_values = [r.out_of_hours_inbound_pct for r in results if r.out_of_hours_inbound_pct is not None]
    avg_out_of_hours_pct = round(sum(ooh_values) / len(ooh_values), 1) if ooh_values else None
    has_waha_metrics = bool(delivery_values or read_values or ghosted_count)

    # Sentiment
    with_sentiment = [r for r in results if r.sentiment is not None]
    positive_count = sum(1 for r in with_sentiment if r.sentiment == Sentiment.POSITIVE)
    neutral_count = sum(1 for r in with_sentiment if r.sentiment == Sentiment.NEUTRAL)
    negative_count = sum(1 for r in with_sentiment if r.sentiment == Sentiment.NEGATIVE)
    positive_pct = round(positive_count / len(with_sentiment) * 100) if with_sentiment else 0
    negative_pct = round(negative_count / len(with_sentiment) * 100) if with_sentiment else 0

    # Conversion
    applicable = [r for r in results if r.conversion_status and r.conversion_status != ConversionStatus.NOT_APPLICABLE]
    converted = sum(1 for r in applicable if r.conversion_status == ConversionStatus.CONVERTED)
    lost = [r for r in applicable if r.conversion_status == ConversionStatus.LOST]
    conversion_rate = round(converted / len(applicable) * 100) if applicable else 0

    # All-pending check: show context callout instead of a flat "0 converted" card
    all_applicable_pending = bool(applicable) and all(
        r.conversion_status == ConversionStatus.PENDING for r in applicable
    )

    # Lost reason breakdown (shown when there are actually lost conversations)
    lost_reasons_summary: list[tuple[str, int]] = []
    if lost:
        reason_counts = Counter(r.conversion_reason for r in lost if r.conversion_reason)
        # Stable sort: count DESC, reason text ASC to break ties deterministically
        lost_reasons_summary = sorted(reason_counts.items(), key=lambda x: (-x[1], x[0]))[:5]

    # Quality
    quality_results = [r for r in results if r.quality_score is not None]
    avg_quality = round(sum(r.quality_score for r in quality_results) / len(quality_results), 1) if quality_results else None

    # Inbound/outbound ratio
    total_inbound = sum(r.inbound_count for r in results)
    total_outbound = sum(r.outbound_count for r in results)

    # Health score
    health = calculate_health_score(
        results,
        first_response_time_seconds=avg_first_rt,
        avg_response_time_seconds=avg_rt,
    )
    health_explanation = explain_health_score(
        health,
        results,
        first_response_time_seconds=avg_first_rt,
        avg_response_time_seconds=avg_rt,
    )

    recommendations = generate_recommendations(
        results,
        first_response_time_seconds=avg_first_rt,
        avg_response_time_seconds=avg_rt,
        average_transaction_value=average_transaction_value,
    )
    headline_recommendations = generate_headline_recommendations(
        results,
        first_response_time_seconds=avg_first_rt,
        avg_response_time_seconds=avg_rt,
    )
    next_steps = generate_next_steps(
        results,
        first_response_time_seconds=avg_first_rt,
        avg_response_time_seconds=avg_rt,
        is_subscribed=is_subscribed,
    )
    alerts = generate_alerts(results, current_avg_response_time=avg_rt)

    # --- Traffic light status indicators ---
    first_rt_status = _traffic_light(avg_first_rt, green_max=300, amber_max=1800)
    avg_rt_status = _traffic_light(avg_rt, green_max=900, amber_max=3600)
    sentiment_status = _traffic_light(positive_pct, green_max=60, amber_max=40, higher_is_better=True)
    unanswered_status = "green" if total_unanswered == 0 else ("amber" if total_unanswered <= 3 else "red")
    quality_status = _traffic_light(avg_quality, green_max=7, amber_max=5, higher_is_better=True)

    # Conversion rate: gray when sample too small for reliable estimate
    small_sample_conversion = len(applicable) < MIN_RELIABLE_CONV
    if small_sample_conversion:
        conversion_status_color = "gray"
    else:
        conversion_status_color = _traffic_light(conversion_rate, green_max=35, amber_max=15, higher_is_better=True)

    # --- Sample size warning ---
    total_conv = len(results)
    if total_conv < 10:
        sample_warning = (
            f"Muestra muy pequeña: este reporte analiza solo {total_conv} "
            f"conversaci{'ón' if total_conv == 1 else 'ones'}. Para métricas más "
            f"confiables, recomendamos analizar al menos 20 conversaciones."
        )
        sample_warning_level = "critical"
    elif total_conv < 20:
        sample_warning = (
            f"Muestra limitada: este reporte analiza {total_conv} conversaciones. "
            f"Se recomiendan 20+ conversaciones para tendencias más confiables."
        )
        sample_warning_level = "warning"
    else:
        sample_warning = None
        sample_warning_level = None

    # --- Revenue impact estimation ---
    estimated_lost_revenue = None
    if average_transaction_value and lost:
        estimated_lost_revenue = len(lost) * average_transaction_value * 0.30

    # --- Charts ---
    rt_by_hour_agg: dict[int, list[float]] = {}
    for r in results:
        if r.response_time_by_hour:
            for hour_str, avg_sec in r.response_time_by_hour.items():
                h = int(hour_str)
                rt_by_hour_agg.setdefault(h, []).append(avg_sec)
    by_hour_data: dict[int, float] = {
        h: statistics.mean(vals) for h, vals in rt_by_hour_agg.items()
    }

    vol_by_hour_data: dict[int, int] = {}

    # When there's only one distinct topic, a single-bar chart adds no value.
    # Show a text callout instead. Use stable sort for deterministic topic selection.
    topic_counter = Counter(r.primary_topic for r in results if r.primary_topic)
    single_topic_callout: str | None = None
    if len(topic_counter) == 1 and total_conv > 0:
        only_topic, only_count = sorted(topic_counter.items(), key=lambda x: (-x[1], x[0]))[0]
        single_topic_callout = (
            f"El {round(only_count / total_conv * 100)}% de tus conversaciones son sobre "
            f"«{only_topic}»."
        )
        chart_topics = None
    else:
        chart_topics = topics_bar_chart(results)

    chart_sentiment = sentiment_donut_chart(results)
    chart_quality = quality_bars_chart(results)
    chart_response_time = response_time_by_hour_chart(by_hour_data) if by_hour_data else None
    chart_volume = volume_by_hour_chart(vol_by_hour_data) if vol_by_hour_data else None

    # --- Operational metrics ---
    msgs_per_conv = round(total_messages / total_conv, 1) if total_conv > 0 else 0

    # Derive busiest hours from response_time_by_hour data (proxy for activity)
    hour_conv_count: dict[int, int] = {}
    for r in results:
        if r.response_time_by_hour:
            for hour_str in r.response_time_by_hour:
                h = int(hour_str)
                hour_conv_count[h] = hour_conv_count.get(h, 0) + 1

    busiest_hour_str = None
    business_hours_pct = None
    limited_hourly_data = False

    if hour_conv_count:
        sorted_hours = sorted(hour_conv_count.items(), key=lambda x: x[1], reverse=True)
        top_hour = sorted_hours[0][0]
        busiest_hour_str = _hour_label(top_hour)
        total_hour_activity = sum(hour_conv_count.values())
        biz_activity = sum(v for h, v in hour_conv_count.items() if 8 <= h <= 18)
        business_hours_pct = round(biz_activity / total_hour_activity * 100) if total_hour_activity > 0 else None
        limited_hourly_data = total_messages < 10

    # Msgs per conversation benchmark interpretation
    if msgs_per_conv <= 6:
        msgs_per_conv_label = "Resolución rápida"
    elif msgs_per_conv <= 15:
        msgs_per_conv_label = "Conversación normal"
    else:
        msgs_per_conv_label = "Proceso largo"

    # --- Customer questions aggregation ---
    all_questions: list[str] = []
    for r in results:
        for q in r.customer_questions:
            normalized = q.strip().lower().lstrip("¿").rstrip("?").strip()
            if normalized:
                all_questions.append(normalized)

    question_counts = Counter(all_questions)
    top_questions: list[tuple[str, int]] = []
    # Stable sort: count DESC, question text ASC to break ties deterministically
    for q, count in sorted(question_counts.items(), key=lambda x: (-x[1], x[0]))[:8]:
        # Re-add question marks for display
        display_q = q.capitalize()
        if not display_q.endswith("?"):
            display_q = "¿" + display_q + "?"
        top_questions.append((display_q, count))

    # --- Conversation summaries (sorted by importance) ---
    lost_convs = [r for r in results if r.conversion_status == ConversionStatus.LOST]
    negative_convs = [
        r for r in results
        if r.sentiment == Sentiment.NEGATIVE and r not in lost_convs
    ]
    best_convs = sorted(
        [r for r in results if r not in lost_convs and r not in negative_convs],
        key=lambda x: (x.quality_score or 0),
        reverse=True,
    )
    sorted_results = (lost_convs + negative_convs + best_convs)[:8]

    def _conv_dot(r: ConversationAnalysisResult) -> str:
        if r.conversion_status == ConversionStatus.CONVERTED:
            return "green"
        if r.conversion_status == ConversionStatus.LOST or r.sentiment == Sentiment.NEGATIVE:
            return "red"
        if r.sentiment == Sentiment.POSITIVE and (r.quality_score or 0) >= 7:
            return "green"
        return "amber"

    conv_cards = []
    for i, r in enumerate(sorted_results, 1):
        if not r.summary:
            continue
        # Reference so the user can find this exact chat in WhatsApp.
        ref_parts: list[str] = []
        if r.contact_name and r.contact_name.strip():
            ref_parts.append(r.contact_name.strip())
        elif r.contact_phone:
            tail = r.contact_phone[-4:] if len(r.contact_phone) >= 4 else r.contact_phone
            ref_parts.append(f"Cliente ···{tail}")
        if r.started_at:
            try:
                ref_parts.append(r.started_at.strftime("%d %b %Y, %H:%M"))
            except Exception:
                pass
        card = {
            "number": i,
            "reference": " · ".join(ref_parts) if ref_parts else None,
            "dot_color": _conv_dot(r),
            "topic": r.primary_topic or "—",
            "sentiment_label": {
                "positive": "Positivo",
                "neutral": "Neutral",
                "negative": "Negativo",
            }.get(r.sentiment.value if r.sentiment else "neutral", "Neutral"),
            "sentiment_score": f"{r.sentiment_score:.1f}" if r.sentiment_score is not None else "—",
            "quality": f"{r.quality_score:.1f}/10" if r.quality_score is not None else "—",
            "status_label": {
                "converted": "Convertida",
                "lost": "Oportunidad perdida",
                "pending": "Pendiente",
                "not_applicable": "No aplica",
            }.get(r.conversion_status.value if r.conversion_status else "not_applicable", "—"),
            "first_rt": _fmt_seconds(r.first_response_time_seconds),
            "summary": r.summary,
            "action": (
                "Responder más rápido habría aumentado la probabilidad de conversión."
                if r.conversion_status == ConversionStatus.LOST
                else (
                    "Revisa el tono y la completitud de las respuestas."
                    if r.sentiment == Sentiment.NEGATIVE
                    else "¡Buena gestión! Usa esta como referencia para el equipo."
                )
            ),
        }
        conv_cards.append(card)

    # --- Confidence level for appendix ---
    if total_conv >= 20:
        confidence_level = "Alta"
    elif total_conv >= 10:
        confidence_level = f"Media ({total_conv} conversaciones)"
    else:
        confidence_level = f"Indicativa ({total_conv} conversaciones — se recomiendan 20+)"

    # --- Date range from results ---
    now = datetime.utcnow()

    # ─── F1: comparison vs previous report ──────────────────────────────────
    # `previous_results` is the analyses from the prior completed job for this
    # client. We compute a small set of deltas so the PDF can render a clear
    # "está mejorando / está empeorando" block. None when there's no prior job.
    previous_comparison: dict | None = None
    if previous_results:
        prev = previous_results

        # Aggregate the same set of metrics for the previous job
        prev_total_conv = len(prev)
        prev_unanswered_convs = sum(r.unanswered_count for r in prev)

        prev_frt_values = [r.first_response_time_seconds for r in prev if r.first_response_time_seconds is not None]
        prev_avg_frt = statistics.mean(prev_frt_values) if prev_frt_values else None

        prev_with_sentiment = [r for r in prev if r.sentiment is not None]
        prev_pos = sum(1 for r in prev_with_sentiment if r.sentiment == Sentiment.POSITIVE)
        prev_pos_pct = round(prev_pos / len(prev_with_sentiment) * 100) if prev_with_sentiment else None

        prev_applicable = [r for r in prev if r.conversion_status and r.conversion_status != ConversionStatus.NOT_APPLICABLE]
        prev_converted = sum(1 for r in prev_applicable if r.conversion_status == ConversionStatus.CONVERTED)
        prev_conversion_rate = round(prev_converted / len(prev_applicable) * 100) if prev_applicable else None

        prev_quality_results = [r for r in prev if r.quality_score is not None]
        prev_avg_quality = round(sum(r.quality_score for r in prev_quality_results) / len(prev_quality_results), 1) if prev_quality_results else None

        prev_health = calculate_health_score(
            prev,
            first_response_time_seconds=prev_avg_frt,
            avg_response_time_seconds=prev_avg_frt,
        )

        def _delta(curr: float | int | None, previous: float | int | None) -> dict | None:
            """Return {value, direction, label} for displaying a delta, or None if not comparable."""
            if curr is None or previous is None:
                return None
            d = curr - previous
            if abs(d) < 0.05:
                return {"value": 0, "direction": "flat", "label": "sin cambio"}
            return {"value": round(d, 1), "direction": "up" if d > 0 else "down",
                    "label": ("subió" if d > 0 else "bajó")}

        # For metrics where "down" is good (response time, unanswered), invert direction labels
        def _delta_inverted(curr, previous):
            d = _delta(curr, previous)
            if d and d["direction"] != "flat":
                # swap direction semantics — "down" is improvement
                d["direction"] = "down" if d["direction"] == "up" else "up"
                d["label"] = "empeoró" if d["direction"] == "up" else "mejoró"
            return d

        previous_comparison = {
            "previous_date": previous_job_created_at.strftime("%d %b %Y") if previous_job_created_at else None,
            "previous_total_conversations": prev_total_conv,
            "health_delta": _delta(health, prev_health),
            "conversion_delta": _delta(conversion_rate if applicable else None, prev_conversion_rate),
            "positive_pct_delta": _delta(positive_pct if with_sentiment else None, prev_pos_pct),
            "quality_delta": _delta(avg_quality, prev_avg_quality),
            "frt_delta": _delta_inverted(avg_first_rt, prev_avg_frt),
            "unanswered_delta": _delta_inverted(total_unanswered, prev_unanswered_convs),
            # Pre-rendered strings so the template stays simple
            "frt_prev_str": _fmt_seconds(prev_avg_frt),
            "frt_curr_str": _fmt_seconds(avg_first_rt),
        }

    # --- Score breakdown for visual display ---
    score_breakdown = get_health_score_breakdown(
        results,
        first_response_time_seconds=avg_first_rt,
        avg_response_time_seconds=avg_rt,
    )

    # --- One-line summary ---
    one_line_summary = _one_line_summary(first_rt_status, quality_status, conversion_rate)

    # --- Hourly extremes analysis ---
    slowest_hour_text, fastest_hour_text, variability_text = _hourly_extremes(by_hour_data)

    # --- Neutral majority note for donut ---
    neutral_pct_val = round(neutral_count / len(with_sentiment) * 100) if with_sentiment else 0
    neutral_majority_note = None
    if neutral_pct_val > 70:
        neutral_majority_note = (
            "La mayoría de tus conversaciones son neutrales — esto puede significar que las interacciones "
            "son transaccionales (el cliente pregunta, tú respondes) sin generar emoción fuerte. "
            "No es malo, pero hay oportunidad de construir más conexión."
        )

    # --- Strategic 3 conversations ---
    strategic_convs = _select_strategic_conversations(results)

    # --- Conversion analysis text ---
    conversion_text = _conversion_analysis_text(conversion_rate, total_unanswered, avg_first_rt)

    # --- Operational interpretation ---
    top_hour_num = None
    if hour_conv_count:
        top_hour_num = sorted(hour_conv_count.items(), key=lambda x: x[1], reverse=True)[0][0]
    operational_text = _operational_interpretation(business_hours_pct, msgs_per_conv, top_hour_num, by_hour_data)

    # --- Action plan ---
    action_plan = _build_action_plan(
        score_breakdown=score_breakdown,
        health_score=health,
        first_rt_str=_fmt_seconds(avg_first_rt),
        avg_first_rt=avg_first_rt,
        conversion_rate=conversion_rate,
        total_unanswered=total_unanswered,
        topic_counter=topic_counter,
        results=results,
    )

    # --- Report metadata ---
    report_version = "2.1"
    period_start = now.strftime("%d %b %Y")
    period_end = now.strftime("%d %b %Y")

    context = {
        "business_name": business_name,
        "generated_at": now.strftime("%d %b %Y, %H:%M UTC"),
        "date_range_start": now.strftime("%d %b %Y"),
        "date_range_end": now.strftime("%d %b %Y"),
        "health_score": health,
        "health_label": _health_label(health),
        "health_explanation": health_explanation,
        # Conversation counts
        "total_conversations": total_conv,
        "total_messages": total_messages,
        "total_unanswered": total_unanswered,
        "total_inbound": total_inbound,
        "total_outbound": total_outbound,
        # Response times
        "first_rt_str": _fmt_seconds(avg_first_rt),
        "median_first_rt_str": _fmt_seconds(median_first_rt),
        "avg_response_time_str": _fmt_seconds(avg_rt),
        "median_response_time_str": _fmt_seconds(median_rt),
        "p95_response_time_str": _fmt_seconds(p95_rt),
        # Sentiment
        "positive_pct": positive_pct,
        "neutral_pct": neutral_pct_val,
        "negative_pct": negative_pct,
        # Conversion
        "conversion_rate": conversion_rate,
        "applicable_count": len(applicable),
        "converted_count": converted,
        "lost_count": len(lost),
        "small_sample_conversion": small_sample_conversion,
        # Quality
        "avg_quality": avg_quality,
        # Traffic light statuses
        "first_rt_status": first_rt_status,
        "avg_rt_status": avg_rt_status,
        "sentiment_status": sentiment_status,
        "conversion_status_color": conversion_status_color,
        "unanswered_status": unanswered_status,
        "quality_status": quality_status,
        # Sample size warning
        "sample_warning": sample_warning,
        "sample_warning_level": sample_warning_level,
        # Revenue impact
        "average_transaction_value": average_transaction_value,
        "average_transaction_value_fmt": _fmt_cop(average_transaction_value) if average_transaction_value else None,
        "estimated_lost_revenue": estimated_lost_revenue,
        "estimated_lost_revenue_fmt": _fmt_cop(estimated_lost_revenue) if estimated_lost_revenue else None,
        # Operational metrics
        "msgs_per_conv": msgs_per_conv,
        "msgs_per_conv_label": msgs_per_conv_label,
        "busiest_hour_str": busiest_hour_str,
        "business_hours_pct": business_hours_pct,
        "limited_hourly_data": limited_hourly_data,
        # Customer questions
        "top_questions": top_questions,
        # Conversation summaries
        "conv_cards": conv_cards,
        # Insights
        "recommendations": recommendations,
        "headline_recommendations": headline_recommendations,
        "next_steps": next_steps,
        "alerts": alerts,
        # Charts
        "chart_sentiment": chart_sentiment,
        "chart_topics": chart_topics,
        "chart_quality": chart_quality,
        "chart_response_time": chart_response_time,
        "chart_volume": chart_volume,
        # Topics
        "single_topic_callout": single_topic_callout,
        # Conversion context
        "all_applicable_pending": all_applicable_pending,
        "lost_reasons_summary": lost_reasons_summary,
        # Meta / Appendix
        "files_processed": files_processed,
        "ai_model": ai_model,
        "confidence_level": confidence_level,
        # New v2.1 context
        "one_line_summary": one_line_summary,
        "score_breakdown": score_breakdown,
        "slowest_hour_text": slowest_hour_text,
        "fastest_hour_text": fastest_hour_text,
        "variability_text": variability_text,
        "neutral_majority_note": neutral_majority_note,
        "strategic_convs": strategic_convs,
        "conversion_text": conversion_text,
        "operational_text": operational_text,
        "action_plan": action_plan,
        "report_version": report_version,
        "period_start": period_start,
        "period_end": period_end,
        # F3 — first-response-time distribution
        "frt_distribution": frt_distribution,
        # WAHA-derived deterministic metrics
        "has_waha_metrics": has_waha_metrics,
        "avg_delivery_rate": avg_delivery_rate,
        "avg_read_rate": avg_read_rate,
        "ghosted_count": ghosted_count,
        "avg_operational_coverage": avg_operational_coverage,
        "avg_out_of_hours_pct": avg_out_of_hours_pct,
        # F1 — comparison with previous completed report
        "previous_comparison": previous_comparison,
        # Brand logo (data URI; empty string if asset missing)
        "logo_data_uri": _LOGO_DATA_URI,
    }

    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)))
    template = env.get_template("report.html")
    html_content = template.render(**context)

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content).write_pdf()
    except Exception as exc:
        logger.error("WeasyPrint PDF generation failed: %s", exc)
        raise

    return pdf_bytes
