"""
Generate a sample PDF report with high-quality synthetic data (~85/100 score)
to validate the report styling without hitting the database or AI providers.

Run from project root:
    python scripts/generate_sample_report.py

Output: ./reporte-deeplook-sample.pdf
"""
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make `app.*` importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.delivery.reports.pdf_generator import generate_pdf_report
from app.models.enums import ConversionStatus, Sentiment
from app.models.schemas import ConversationAnalysisResult, QualityBreakdown


random.seed(42)  # deterministic output

# Mix designed to land ~82-85/100 ("Bueno"):
#   • Velocidad: avg first response ~90-180s   → ~24/25
#   • Cobertura: 1 unanswered of 30  (3.3%)    → ~13/15
#   • Sentimiento: 70% pos / 23% neu / 7% neg  → ~17/20
#   • Calidad: avg ~8.5/10                     → ~13/15
#   • Conversión: ~67% of applicable           → ~9/15
#   • Cobertura horaria: default 50            → 5/10
PROFILES = (
    [("converted", "positive", 8.8, 75)] * 18  # 18 happy converted
    + [("pending",   "neutral",  7.5, 200)] * 4   # 4 pending neutral
    + [("lost",      "negative", 6.0, 600)] * 2   # 2 lost negative
    + [("lost",      "neutral",  6.5, 450)] * 3   # 3 lost neutral
    + [("not_applicable", "neutral", 7.0, 120)] * 3  # 3 N/A
)


TOPICS = [
    "precios y cotizaciones",
    "disponibilidad y horarios",
    "información de servicios",
    "agendar cita",
    "promociones",
    "ubicación",
]

POSITIVE_REASONS = [
    "La cliente confirmó la cita y agradeció la atención rápida",
    "El cliente quedó satisfecho con la información y reservó",
    "La conversación cerró con compra inmediata",
]
NEUTRAL_REASONS = [
    "El cliente recibió la información solicitada sin manifestar entusiasmo",
    "La conversación fue informativa, sin compromiso de compra",
]
NEGATIVE_REASONS = [
    "El cliente expresó frustración por el tiempo de espera inicial",
    "La cliente no encontró la opción que buscaba",
]


def _make_result(idx: int, profile: tuple) -> ConversationAnalysisResult:
    status, sentiment, quality, frt = profile
    started = datetime(2026, 4, random.randint(1, 30), random.randint(8, 19), random.randint(0, 59), tzinfo=timezone.utc)
    avg_rt = frt + random.randint(20, 120)
    inbound = random.randint(4, 9)
    outbound = inbound + random.randint(0, 2)
    is_unanswered = idx == 7  # exactly one unanswered conversation
    return ConversationAnalysisResult(
        conversation_id=str(uuid.uuid4()),
        contact_phone=f"57301{random.randint(1000000, 9999999)}",
        contact_name=f"Cliente {idx + 1}",
        started_at=started,
        sentiment=Sentiment(sentiment),
        sentiment_score={"positive": 0.85, "neutral": 0.55, "negative": 0.25}[sentiment],
        sentiment_reason=random.choice(
            POSITIVE_REASONS if sentiment == "positive"
            else NEGATIVE_REASONS if sentiment == "negative"
            else NEUTRAL_REASONS
        ),
        primary_topic=random.choice(TOPICS),
        secondary_topics=random.sample(TOPICS, 2),
        quality_score=round(quality + random.uniform(-0.4, 0.4), 1),
        quality_breakdown=QualityBreakdown(
            helpfulness=round(quality + random.uniform(-0.5, 0.5), 1),
            tone=round(quality + 0.3 + random.uniform(-0.3, 0.3), 1),
            completeness=round(quality - 0.2 + random.uniform(-0.4, 0.4), 1),
        ),
        conversion_status=ConversionStatus(status),
        conversion_reason={
            "converted":      "El cliente confirmó la cita y realizó el pago anticipado",
            "lost":           "El cliente decidió no continuar con el servicio",
            "pending":        "El cliente quedó en pensarlo y volver a contactar",
            "not_applicable": "Consulta general sin intención de compra",
        }[status],
        summary=(
            "El cliente consultó por el servicio. La asesora respondió con claridad, "
            "ofreció opciones y guió al cliente hacia una decisión. "
            "La interacción fue profesional y eficiente."
        ),
        key_points=[
            "Respuesta rápida en menos de 2 minutos",
            "Información completa enviada de inmediato",
            "Cliente confirmó interés",
        ],
        customer_questions=[
            "¿Cuánto cuesta el servicio?",
            "¿Tienen disponibilidad esta semana?",
        ],
        first_response_time_seconds=None if is_unanswered else float(frt + random.randint(-30, 60)),
        avg_response_time_seconds=None if is_unanswered else float(avg_rt),
        median_response_time_seconds=None if is_unanswered else float(avg_rt - 30),
        p95_response_time_seconds=None if is_unanswered else float(avg_rt + 200),
        unanswered_count=1 if is_unanswered else 0,
        trailing_inbound_messages=2 if is_unanswered else 0,
        total_messages=inbound + outbound,
        inbound_count=inbound,
        outbound_count=outbound,
        duration_minutes=float(random.randint(8, 45)),
        delivery_rate=1.0,
        read_rate=round(random.uniform(0.85, 0.98), 2),
        wa_is_muted=False,
        wa_is_archived=False,
    )


def main() -> None:
    results = [_make_result(i, p) for i, p in enumerate(PROFILES)]

    pdf_bytes = generate_pdf_report(
        results=results,
        business_name="DeepLook",
        job_id=str(uuid.uuid4()),
        files_processed=1,
        ai_model="gpt-4o-mini",
        average_transaction_value=120_000,
        business_type="salon de belleza",
        is_subscribed=True,
        previous_results=None,
    )

    out_path = Path(__file__).resolve().parents[1] / "reporte-deeplook-sample.pdf"
    out_path.write_bytes(pdf_bytes)
    print(f"✔ Reporte generado: {out_path}  ({len(pdf_bytes) / 1024:.1f} KB, {len(results)} conversaciones)")


if __name__ == "__main__":
    main()
