"""
Anomaly detection and alert generation. Rule-based, no AI.
"""
from app.models.enums import Sentiment
from app.models.schemas import ConversationAnalysisResult


def generate_alerts(
    results: list[ConversationAnalysisResult],
    previous_avg_response_time: float | None = None,
    current_avg_response_time: float | None = None,
) -> list[str]:
    alerts: list[str] = []

    # Response time spike: current >50% higher than previous period
    if (
        current_avg_response_time is not None
        and previous_avg_response_time is not None
        and previous_avg_response_time > 0
        and current_avg_response_time > previous_avg_response_time * 1.5
    ):
        alerts.append(
            f"⚠️ Spike en tiempo de respuesta: {current_avg_response_time / 60:.0f} min (era "
            f"{previous_avg_response_time / 60:.0f} min — subió más del 50%)."
        )

    # Quality drop
    low_quality = [r for r in results if r.quality_score is not None and r.quality_score < 4.0]
    for r in low_quality:
        alerts.append(
            f"⚠️ Calidad baja ({r.quality_score}/10) en conversación con cliente."
        )

    # 3+ consecutive negative conversations
    sentiments = [r.sentiment for r in results if r.sentiment is not None]
    consecutive_neg = 0
    for s in sentiments:
        if s == Sentiment.NEGATIVE:
            consecutive_neg += 1
            if consecutive_neg >= 3:
                alerts.append("⚠️ 3 o más conversaciones consecutivas con sentimiento negativo detectadas.")
                break
        else:
            consecutive_neg = 0

    # Unanswered messages
    total_unanswered = sum(r.unanswered_count for r in results)
    if total_unanswered > 0:
        alerts.append(
            f"⚠️ {total_unanswered} mensaje{'s' if total_unanswered != 1 else ''} sin respuesta detectado{'s' if total_unanswered != 1 else ''}."
        )

    return alerts
