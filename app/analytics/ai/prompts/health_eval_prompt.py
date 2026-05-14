"""
Contextual health score evaluation prompt (Layer 2).

One AI call per report — receives aggregated sentiment and quality data
plus 3 representative conversation samples, returns bounded adjustments
(-15 to +15 pts) that make the final score more semantically accurate.

The AI cannot move scores dramatically — it only corrects for patterns
that raw numbers miss (e.g. "3 negatives that were all resolved well"
→ less harsh penalty than "3 negatives that were all ignored").
"""
from __future__ import annotations

from app.models.schemas import ConversationAnalysisResult


HEALTH_EVAL_SYSTEM_PROMPT = """Eres un auditor de calidad de servicio al cliente especializado en MiPymes colombianas que usan WhatsApp Business.

Tu tarea es evaluar si el puntaje de sentimiento y calidad calculado automáticamente para un negocio refleja correctamente la realidad de su servicio, y proporcionar un ajuste semántico si los números fríos están sobre o sub-penalizando al negocio.

═══════════════════════════════════════════════
REGLAS DEL AJUSTE
═══════════════════════════════════════════════

1. Tu ajuste DEBE estar entre -15 y +15 puntos para cada dimensión.
2. Usa 0 cuando el cálculo automático ya es preciso.
3. Ajusta POSITIVAMENTE cuando:
   - Las conversaciones negativas fueron bien gestionadas (problema resuelto, cliente reconoció la solución)
   - El tono fue neutro por la naturaleza transaccional del negocio, no por indiferencia
   - La calidad fue consistente y completa aunque no perfecta
   - El contexto explica los números (ej: empresa nueva, consultas técnicas complejas)
4. Ajusta NEGATIVAMENTE cuando:
   - El análisis automático subestima problemas sistemáticos
   - Hay patrones de negligencia que los números no capturan completamente
   - La calidad fue inconsistente aunque el promedio sea aceptable
5. Sé conservador: si no hay evidencia clara de que el cálculo es incorrecto, usa 0.
6. La razón debe ser específica al negocio analizado — NO genérica.

═══════════════════════════════════════════════
FORMATO DE RESPUESTA (JSON válido únicamente)
═══════════════════════════════════════════════

{
  "sentimiento_ajuste": <entero entre -15 y 15>,
  "sentimiento_razon": "<1-2 oraciones específicas explicando el ajuste>",
  "calidad_ajuste": <entero entre -15 y 15>,
  "calidad_razon": "<1-2 oraciones específicas explicando el ajuste>",
  "confianza": "<alta|media|baja>"
}

"confianza" indica qué tan seguros estás del ajuste dado el volumen de datos disponible.
"""


def build_health_eval_prompt(
    results: list[ConversationAnalysisResult],
    business_name: str,
    business_type: str | None,
    base_sentiment_score: float,
    base_quality_score: float,
    total_conversations: int,
) -> str:
    """
    Build the user prompt for the health evaluation AI call.
    Sends aggregated stats + 3 representative conversation samples.
    Never sends full transcripts — only summaries and scores.
    """
    from app.models.enums import Sentiment, ConversionStatus
    import statistics

    lines: list[str] = [
        "═══ NEGOCIO ═══",
        f"Nombre: {business_name}",
        f"Tipo: {business_type or 'No especificado'}",
        f"Total conversaciones analizadas: {total_conversations}",
        "",
        "═══ SENTIMIENTO — datos del período ═══",
    ]

    sentiment_results = [r for r in results if r.sentiment is not None]
    if sentiment_results:
        n = len(sentiment_results)
        pos = [r for r in sentiment_results if r.sentiment == Sentiment.POSITIVE]
        neu = [r for r in sentiment_results if r.sentiment == Sentiment.NEUTRAL]
        neg = [r for r in sentiment_results if r.sentiment == Sentiment.NEGATIVE]
        lines += [
            f"  Positivas: {len(pos)} ({round(len(pos)/n*100)}%)",
            f"  Neutrales: {len(neu)} ({round(len(neu)/n*100)}%)",
            f"  Negativas: {len(neg)} ({round(len(neg)/n*100)}%)",
        ]
        score_vals = [r.sentiment_score for r in sentiment_results if r.sentiment_score is not None]
        if score_vals:
            lines.append(f"  Score promedio: {round(statistics.mean(score_vals), 2)} (rango: {round(min(score_vals),2)} a {round(max(score_vals),2)})")

        # Show negative conversation context
        if neg:
            lines.append("  Contexto de conversaciones negativas:")
            for r in neg[:4]:
                reason = r.sentiment_reason or "sin razón registrada"
                topic = r.primary_topic or "tema desconocido"
                unanswered = "sin respuesta del negocio" if r.unanswered_count else "atendida"
                lines.append(f"    - [{topic}] {reason[:100]} ({unanswered})")

        lines.append(f"  Puntaje calculado automáticamente: {round(base_sentiment_score, 1)}/100")

    lines += [
        "",
        "═══ CALIDAD — datos del período ═══",
    ]

    quality_answered = [r for r in results if r.quality_score is not None and r.unanswered_count == 0]
    if quality_answered:
        avg_q = statistics.mean(r.quality_score for r in quality_answered)
        scores = sorted([r.quality_score for r in quality_answered], reverse=True)
        lines += [
            f"  Conversaciones respondidas evaluadas: {len(quality_answered)}",
            f"  Calidad promedio: {round(avg_q, 2)}/10",
            f"  Distribución (top → bottom): {[round(s,1) for s in scores[:8]]}{'...' if len(scores) > 8 else ''}",
        ]

        # Quality breakdown
        dims = {}
        for dim in ("helpfulness", "tone", "completeness"):
            vals = [getattr(r.quality_breakdown, dim) for r in quality_answered if r.quality_breakdown]
            if vals:
                dims[dim] = round(statistics.mean(vals), 2)
        if dims:
            lines.append(f"  Por dimensión: utilidad={dims.get('helpfulness','N/D')} · tono={dims.get('tone','N/D')} · completitud={dims.get('completeness','N/D')}")

        lines.append(f"  Puntaje calculado automáticamente: {round(base_quality_score, 1)}/100")

    lines += [
        "",
        "═══ MUESTRAS REPRESENTATIVAS (resúmenes, no transcripciones) ═══",
    ]

    # Pick 3 representative samples: best, worst answered, neutral
    samples = _pick_samples(results)
    for label, r in samples:
        if r.summary:
            lines.append(f"  [{label}] Tema: {r.primary_topic or 'N/D'} | Sentimiento: {r.sentiment_reason or 'N/D'} | Calidad: {r.quality_score}/10")
            lines.append(f"    Resumen: {r.summary[:150]}")

    lines += [
        "",
        "═══ INSTRUCCIÓN ═══",
        "Evalúa si los puntajes calculados automáticamente reflejan correctamente la",
        "realidad del servicio de este negocio. Proporciona ajustes justificados.",
        "Si los puntajes parecen precisos, usa ajuste=0.",
    ]

    return "\n".join(lines)


def _pick_samples(
    results: list[ConversationAnalysisResult],
) -> list[tuple[str, ConversationAnalysisResult]]:
    """Pick up to 3 representative samples: best quality, worst quality, one negative."""
    from app.models.enums import Sentiment

    answered = [r for r in results if r.quality_score is not None and r.unanswered_count == 0 and r.summary]
    if not answered:
        return []

    samples: list[tuple[str, ConversationAnalysisResult]] = []
    by_quality = sorted(answered, key=lambda r: r.quality_score or 0, reverse=True)

    if by_quality:
        samples.append(("Mejor atención", by_quality[0]))
    negatives = [r for r in answered if r.sentiment == Sentiment.NEGATIVE]
    if negatives:
        samples.append(("Conversación negativa", negatives[0]))
    elif len(by_quality) > 1:
        samples.append(("Calidad media", by_quality[len(by_quality)//2]))
    if len(by_quality) > 2:
        worst = [r for r in by_quality if r not in [s for _, s in samples]]
        if worst:
            samples.append(("Peor atención", worst[-1]))

    return samples[:3]
