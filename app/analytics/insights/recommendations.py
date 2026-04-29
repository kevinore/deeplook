"""
Rule-based recommendation engine. Generates 3-5 specific, actionable recommendations in Spanish.
No AI — pure rule logic based on Colombia MiPymes benchmarks from the DeepLook metrics framework.

Colombia MiPymes benchmarks used:
- First response time benchmark: 5 minutes (65% of Colombian consumers expect response in < 5 min)
- Avg response time benchmark: 15 minutes
- Unanswered rate critical threshold: any unanswered message
- Negative sentiment threshold: >20%
- Dominant topic threshold: >40% of conversations
- Lost lead threshold: >20% of applicable conversations
- Quality score threshold: <6/10
"""
from collections import Counter

from app.models.enums import ConversionStatus, Sentiment
from app.models.schemas import ConversationAnalysisResult


def _fmt_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)} segundos"
    if seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minuto{'s' if minutes != 1 else ''}"
    hours = seconds / 3600
    return f"{hours:.1f} horas"


def _fmt_cop(amount: float) -> str:
    """Format a number as Colombian pesos: $1.900.000 COP."""
    return f"${int(amount):,}".replace(",", ".") + " COP"


def generate_recommendations(
    results: list[ConversationAnalysisResult],
    first_response_time_seconds: float | None = None,
    avg_response_time_seconds: float | None = None,
    average_transaction_value: float | None = None,
) -> list[str]:
    recs: list[str] = []

    # Estimate lost conversations for revenue impact
    applicable = [r for r in results if r.conversion_status and r.conversion_status != ConversionStatus.NOT_APPLICABLE]
    lost = [r for r in applicable if r.conversion_status == ConversionStatus.LOST]
    lost_count = len(lost)
    revenue_note = ""
    if average_transaction_value and lost_count > 0:
        estimated_lost = lost_count * average_transaction_value * 0.30
        revenue_note = f" Esto representa aproximadamente {_fmt_cop(estimated_lost)} en ingresos potencialmente perdidos."

    # 1. First response time — the single most important Colombia MiPymes metric
    if first_response_time_seconds is not None and first_response_time_seconds > 300:
        human = _fmt_seconds(first_response_time_seconds)
        recs.append(
            f"Tu tiempo de primera respuesta es {human}. El 65% de los consumidores colombianos "
            f"esperan respuesta en menos de 5 minutos, y el 56% ha abandonado una compra por "
            f"respuesta lenta. Reducir este tiempo puede aumentar significativamente tu tasa de conversión."
            + revenue_note
        )
    elif avg_response_time_seconds is not None and avg_response_time_seconds > 300 and first_response_time_seconds is None:
        human = _fmt_seconds(avg_response_time_seconds)
        recs.append(
            f"Tu tiempo promedio de respuesta es {human}. El 65% de los consumidores colombianos "
            f"esperan respuesta en menos de 5 minutos. Considera configurar respuestas automáticas "
            f"para las preguntas más frecuentes."
            + revenue_note
        )

    # 2. Unanswered conversations — every unanswered chat is a lost sale.
    # `unanswered_count` is now 0|1 per conversation (chat-level), so the sum
    # equals the number of conversations awaiting a business reply.
    unanswered_convs = sum(r.unanswered_count for r in results)
    if unanswered_convs > 0:
        plural = unanswered_convs != 1
        recs.append(
            f"Tienes {unanswered_convs} conversaci{'ones' if plural else 'ón'} sin responder. "
            f"Cada conversación abandonada es una venta potencial perdida — "
            f"prioriza responderlas hoy mismo."
        )

    # 3. Negative sentiment — systemic problem if >20%
    with_sentiment = [r for r in results if r.sentiment is not None]
    if with_sentiment:
        negative = [r for r in with_sentiment if r.sentiment == Sentiment.NEGATIVE]
        neg_pct = len(negative) / len(with_sentiment) * 100
        if neg_pct > 20:
            neg_topics = [r.primary_topic for r in negative if r.primary_topic]
            topics_str = ", ".join(
                t for t, _ in sorted(Counter(neg_topics).items(), key=lambda x: (-x[1], x[0]))[:3]
            )
            recs.append(
                f"El {neg_pct:.0f}% de tus conversaciones tienen sentimiento negativo "
                f"(el umbral saludable es menos del 20%). "
                f"Los temas principales de insatisfacción son: {topics_str or 'varios temas'}."
            )

    # 4. Dominant topic — if >40%, create a ready response
    all_topics = [r.primary_topic for r in results if r.primary_topic]
    if all_topics:
        topic_counts = Counter(all_topics)
        top_topic, top_count = sorted(topic_counts.items(), key=lambda x: (-x[1], x[0]))[0]
        topic_pct = top_count / len(results) * 100
        if topic_pct > 40:
            recs.append(
                f"El {topic_pct:.0f}% de tus clientes preguntan sobre '{top_topic}'. "
                f"Crea una respuesta rápida o un catálogo con esta información para enviarla "
                f"de inmediato — esto puede reducir tu tiempo de respuesta a menos de 1 minuto para "
                f"estas consultas."
            )

    # 5. Lost leads — with Colombia benchmark comparison
    if applicable:
        lost_pct = len(lost) / len(applicable) * 100
        if lost_pct > 20:
            lost_reasons = [r.conversion_reason for r in lost if r.conversion_reason]
            reasons_str = "; ".join(
                t for t, _ in sorted(Counter(lost_reasons).items(), key=lambda x: (-x[1], x[0]))[:2]
            )
            recs.append(
                f"Estás perdiendo el {lost_pct:.0f}% de los leads. "
                f"El promedio de los negocios exitosos en Colombia con WhatsApp es del 35-42% de conversión. "
                f"Las principales razones de pérdida son: {reasons_str or 'sin datos específicos'}."
            )

    # 6. Quality — low completeness is the most actionable dimension.
    # speed_perception is no longer evaluated by the AI (timestamps cover that
    # side of "speed" deterministically). Only the 3 active dimensions surface here.
    with_quality = [r for r in results if r.quality_score is not None]
    if with_quality:
        avg_quality = sum(r.quality_score for r in with_quality) / len(with_quality)
        if avg_quality < 6:
            low_dims = []
            dim_labels = {
                "helpfulness": "Utilidad",
                "tone": "Tono",
                "completeness": "Completitud",
            }
            for dim, label in dim_labels.items():
                dim_scores = [getattr(r.quality_breakdown, dim) for r in with_quality if r.quality_breakdown]
                if dim_scores:
                    dim_avg = sum(dim_scores) / len(dim_scores)
                    if dim_avg < 6:
                        low_dims.append(f"{label} ({dim_avg:.1f}/10)")
            dims_str = ", ".join(low_dims) if low_dims else "varias áreas"
            recs.append(
                f"La calidad promedio de tus respuestas es {avg_quality:.1f}/10. "
                f"Las dimensiones con mayor oportunidad de mejora son: {dims_str}."
            )

    # Return 3-5 most relevant recommendations
    return recs[:5] if recs else [
        "¡Buen trabajo! Tus métricas generales se ven bien. "
        "Sigue manteniendo tiempos de primera respuesta menores a 5 minutos "
        "y un servicio de calidad para mantener tu ventaja competitiva en Colombia."
    ]


def generate_headline_recommendations(
    results: list[ConversationAnalysisResult],
    first_response_time_seconds: float | None = None,
    avg_response_time_seconds: float | None = None,
) -> list[str]:
    """
    Brief, one-sentence recommendations for the executive summary (page 1).
    These are shortened versions of the full recommendations — no duplication.
    """
    headlines: list[str] = []

    if first_response_time_seconds is not None and first_response_time_seconds > 300:
        human = _fmt_seconds(first_response_time_seconds)
        headlines.append(f"Reduce tu tiempo de primera respuesta de {human} a menos de 5 minutos.")
    elif avg_response_time_seconds is not None and avg_response_time_seconds > 300 and first_response_time_seconds is None:
        human = _fmt_seconds(avg_response_time_seconds)
        headlines.append(f"Reduce tu tiempo promedio de respuesta de {human} — el objetivo es menos de 5 minutos.")

    unanswered_convs = sum(r.unanswered_count for r in results)
    if unanswered_convs > 0:
        plural = unanswered_convs != 1
        headlines.append(
            f"Responde las {unanswered_convs} conversaci{'ones' if plural else 'ón'} sin contestar — "
            f"cada una es una venta potencial perdida."
        )

    all_topics = [r.primary_topic for r in results if r.primary_topic]
    if all_topics:
        topic_counts = Counter(all_topics)
        top_topic, top_count = sorted(topic_counts.items(), key=lambda x: (-x[1], x[0]))[0]
        topic_pct = top_count / len(results) * 100
        if topic_pct > 40:
            headlines.append(
                f"Crea respuestas rápidas para '{top_topic}' ({topic_pct:.0f}% de las consultas)."
            )

    applicable = [r for r in results if r.conversion_status and r.conversion_status != ConversionStatus.NOT_APPLICABLE]
    if applicable:
        lost = [r for r in applicable if r.conversion_status == ConversionStatus.LOST]
        lost_pct = len(lost) / len(applicable) * 100
        if lost_pct > 20:
            headlines.append(
                f"Mejora tu tasa de conversión: estás perdiendo el {lost_pct:.0f}% de los leads "
                f"(benchmark Colombia: 35-42%)."
            )

    return headlines[:3] if headlines else [
        "Mantén tus tiempos de respuesta por debajo de 5 minutos para maximizar conversiones."
    ]


def generate_next_steps(
    results: list[ConversationAnalysisResult],
    first_response_time_seconds: float | None = None,
    avg_response_time_seconds: float | None = None,
    is_subscribed: bool = False,
) -> list[str]:
    """
    Generate exactly 3 concrete next steps for the 'Próximos Pasos' section.
    Step 3 is always an upsell (or retention message if already subscribed).
    """
    steps: list[str] = []

    # Step 1: Top priority action — action-focused, no repeating the problem stats
    # (those are already stated in the Recomendaciones section)
    if first_response_time_seconds is not None and first_response_time_seconds > 300:
        all_topics = [r.primary_topic for r in results if r.primary_topic]
        if all_topics:
            top_topic = sorted(Counter(all_topics).items(), key=lambda x: (-x[1], x[0]))[0][0]
            steps.append(
                f"Configura respuestas rápidas en WhatsApp Business para '{top_topic}' "
                f"— el tema más frecuente de tus clientes. "
                f"Ve a Configuración → Herramientas para la empresa → Respuestas rápidas."
            )
        else:
            steps.append(
                "Configura respuestas rápidas en WhatsApp Business para tus consultas más frecuentes. "
                "Ve a Configuración → Herramientas para la empresa → Respuestas rápidas."
            )
    else:
        unanswered_convs = sum(r.unanswered_count for r in results)
        if unanswered_convs > 0:
            plural = unanswered_convs != 1
            steps.append(
                f"Revisa y responde las {unanswered_convs} conversaci{'ones' if plural else 'ón'} sin contestar. "
                f"Activa las notificaciones en WhatsApp Business para no perder nuevas consultas."
            )
        else:
            steps.append(
                "Aprovecha tu buen tiempo de respuesta configurando un catálogo de productos "
                "o servicios en WhatsApp Business. Ve a Configuración → Herramientas → Catálogo."
            )

    # Step 2: Standard recommendation about business hours and auto-replies
    steps.append(
        "Establece un horario de atención y configura un mensaje automático fuera de horario. "
        "Tus clientes sabrán cuándo esperar una respuesta, lo que reduce la frustración "
        "y las oportunidades perdidas."
    )

    # Step 3: Upsell or retention
    if is_subscribed:
        steps.append(
            "Tu próximo reporte se generará automáticamente en 30 días. "
            "Compararemos los resultados para medir tu progreso y el impacto de los cambios."
        )
    else:
        steps.append(
            "Programa tu próximo análisis en 30 días para medir el impacto de estos cambios. "
            "Con el Plan Básico de DeepLook ($160,000 COP/mes) recibes un reporte mensual "
            "con comparación de tendencias. Contáctanos: contacto@deeplook.co"
        )

    return steps
