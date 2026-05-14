"""
Regenerate PDFs for existing jobs using the updated pdf_generator logic
(median-based health score, corrected response time labels).

Usage:
    python scripts/regen_pdfs.py [job_id_fragment ...]

If no arguments are given, it regenerates the 3 hardcoded prod example jobs.
Output files are written to the project root.
"""
import asyncio
import os
import sys
import statistics
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text

from app.config import settings
from app.models.database import (
    AnalysisJob, Client, ConversationAnalysis, Conversation, Contact,
    WhatsAppConnection,
)
from app.models.schemas import ConversationAnalysisResult, QualityBreakdown
from app.delivery.reports.pdf_generator import generate_pdf_report

# Job ID fragments for the 3 example PDFs (last 8 hex chars of each job UUID)
DEFAULT_JOB_FRAGMENTS = ["3af132ca", "37761578", "aaa171f3"]


async def regen(job_fragments: list[str]) -> None:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        connect_args={"statement_cache_size": 0},  # required for PgBouncer transaction mode
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        for fragment in job_fragments:
            # Find job by UUID prefix (filename uses first 8 chars of UUID)
            result = await session.execute(
                select(AnalysisJob).where(
                    text(f"CAST(id AS TEXT) LIKE '{fragment}%'")
                )
            )
            job = result.scalar_one_or_none()
            if not job:
                print(f"  [!] Job fragment '{fragment}' not found — skipping")
                continue

            job_id = str(job.id)
            print(f"  → Job {job_id} (status={job.status})")

            # Fetch client
            client_result = await session.execute(
                select(Client).where(Client.id == job.client_id)
            )
            client = client_result.scalar_one_or_none()
            if not client:
                print(f"  [!] Client not found for job {job_id} — skipping")
                continue

            # Fetch connection display name if applicable
            account_name = None
            if job.connection_id:
                conn_result = await session.execute(
                    select(WhatsAppConnection).where(WhatsAppConnection.id == job.connection_id)
                )
                conn = conn_result.scalar_one_or_none()
                if conn:
                    account_name = conn.display_name

            # Fetch analysis results joined with conversation + contact
            rows_result = await session.execute(
                select(ConversationAnalysis, Conversation, Contact)
                .join(Conversation, ConversationAnalysis.conversation_id == Conversation.id)
                .join(Contact, Conversation.contact_id == Contact.id)
                .where(ConversationAnalysis.analysis_job_id == job_id)
                .order_by(Conversation.started_at.asc(), ConversationAnalysis.conversation_id.asc())
            )
            rows = list(rows_result.all())
            if not rows:
                print(f"  [!] No analysis rows found for job {job_id} — skipping")
                continue

            print(f"     {len(rows)} conversations found")

            results = [
                ConversationAnalysisResult(
                    conversation_id=str(a.conversation_id),
                    contact_phone=contact.phone,
                    contact_name=contact.name,
                    started_at=conv.started_at,
                    sentiment=a.sentiment,
                    sentiment_score=a.sentiment_score,
                    sentiment_reason=a.sentiment_reason,
                    primary_topic=a.primary_topic,
                    secondary_topics=a.secondary_topics or [],
                    quality_score=a.quality_score,
                    quality_breakdown=QualityBreakdown(**a.quality_breakdown) if a.quality_breakdown else QualityBreakdown(),
                    conversion_status=a.conversion_status,
                    conversion_reason=a.conversion_reason,
                    summary=a.summary,
                    key_points=a.key_points or [],
                    customer_questions=a.customer_questions or [],
                    tokens_used=a.tokens_used,
                    analysis_cost_usd=a.analysis_cost_usd,
                    ai_provider=a.ai_provider,
                    ai_model=a.ai_model,
                    first_response_time_seconds=a.first_response_time_seconds,
                    avg_response_time_seconds=a.avg_response_time_seconds,
                    median_response_time_seconds=a.median_response_time_seconds,
                    p95_response_time_seconds=a.p95_response_time_seconds,
                    avg_response_time_bh_seconds=getattr(a, "avg_response_time_bh_seconds", None),
                    unanswered_count=a.unanswered_count or 0,
                    trailing_inbound_messages=getattr(a, "trailing_inbound_messages", 0) or 0,
                    total_messages=a.total_messages or 0,
                    inbound_count=a.inbound_count or 0,
                    outbound_count=a.outbound_count or 0,
                    duration_minutes=a.duration_minutes,
                    response_time_by_hour=a.response_time_by_hour,
                    delivery_rate=getattr(a, "delivery_rate", None),
                    read_rate=getattr(a, "read_rate", None),
                    is_ghosted=bool(getattr(a, "is_ghosted", False)),
                    last_business_msg_ack=getattr(a, "last_business_msg_ack", None),
                    operational_coverage_score=getattr(a, "operational_coverage_score", None),
                    out_of_hours_inbound_pct=getattr(a, "out_of_hours_inbound_pct", None),
                    wa_unread_count=getattr(a, "wa_unread_count", None),
                    wa_is_muted=bool(getattr(a, "wa_is_muted", False)),
                    wa_is_archived=bool(getattr(a, "wa_is_archived", False)),
                    client_relationship=getattr(a, "client_relationship", None),
                    client_relationship_source=getattr(a, "client_relationship_source", None),
                    client_relationship_signals=getattr(a, "client_relationship_signals", None) or [],
                    has_purchase_intent=bool(getattr(a, "has_purchase_intent", False)),
                    intent_stage=getattr(a, "intent_stage", None),
                    intent_first_at=getattr(a, "intent_first_at", None),
                    quote_requested_at=getattr(a, "quote_requested_at", None),
                    quote_sent_at=getattr(a, "quote_sent_at", None),
                    quote_response_time_seconds=getattr(a, "quote_response_time_seconds", None),
                    post_quote_followup_count=getattr(a, "post_quote_followup_count", None),
                    followup_delay_hours=getattr(a, "followup_delay_hours", None),
                    lost_reason=getattr(a, "lost_reason", None),
                    lost_reason_detail=getattr(a, "lost_reason_detail", None),
                )
                for (a, conv, contact) in rows
            ]

            # --- AI calls: health evaluation + action plan ---
            ai_health_adjustments: dict = {}
            ai_action_plan: list = []
            try:
                from app.analytics.ai.factory import create_provider
                from app.analytics.insights.health_score import calculate_health_score
                from app.analytics.insights.health_score_orchestrator import evaluate_health_context
                from app.analytics.insights.action_plan_orchestrator import generate_action_plan

                _provider = create_provider()
                frt_vals = [r.first_response_time_seconds for r in results if r.first_response_time_seconds is not None]
                rt_vals  = [r.avg_response_time_seconds   for r in results if r.avg_response_time_seconds   is not None]
                _med_frt = statistics.median(frt_vals) if frt_vals else None
                _avg_rt  = statistics.mean(rt_vals)   if rt_vals  else None

                base_health = calculate_health_score(results, first_response_time_seconds=_med_frt, avg_response_time_seconds=_avg_rt)

                print(f"     → Calling AI: health evaluation...", end=" ", flush=True)
                ai_health_adjustments, h_cost, h_tin, h_tout = await evaluate_health_context(
                    results=results,
                    ai_provider=_provider,
                    business_name=client.business_name or client.name,
                    business_type=client.business_type,
                    first_response_time_seconds=_med_frt,
                    avg_response_time_seconds=_avg_rt,
                )
                final_health = calculate_health_score(results, first_response_time_seconds=_med_frt, avg_response_time_seconds=_avg_rt, health_adjustments=ai_health_adjustments)
                sent_adj = ai_health_adjustments.get("sentimiento_ajuste", 0)
                qual_adj = ai_health_adjustments.get("calidad_ajuste", 0)
                print(f"done (sent:{sent_adj:+d} qual:{qual_adj:+d} | {h_tin+h_tout} tokens ${h_cost:.4f})")

                print(f"     → Calling AI: action plan...", end=" ", flush=True)
                ai_action_plan, ap_cost, ap_tin, ap_tout = await generate_action_plan(
                    results=results,
                    ai_provider=_provider,
                    business_name=client.business_name or client.name,
                    business_type=client.business_type,
                    health_score=final_health,
                )
                print(f"done ({len(ai_action_plan)} action cards | {ap_tin+ap_tout} tokens ${ap_cost:.4f})")

            except Exception as e:
                print(f"\n     [!] AI calls failed ({e}) — using deterministic fallbacks")

            pdf_bytes = generate_pdf_report(
                results=results,
                business_name=client.business_name or client.name,
                job_id=job_id,
                files_processed=1,
                ai_model=job.ai_model or "unknown",
                average_transaction_value=client.average_transaction_value,
                business_type=client.business_type,
                is_subscribed=client.plan not in ("free",),
                account_name=account_name,
                previous_results=None,
                previous_job_created_at=None,
                action_plan=ai_action_plan or None,
                health_adjustments=ai_health_adjustments or None,
            )

            # Build filename same as the delivery router does
            slug = (client.business_name or client.name or "reporte").lower()
            slug = "".join(c if c.isalnum() else "-" for c in slug).strip("-")[:40]
            if account_name:
                acc_slug = "".join(c if c.isalnum() else "-" for c in account_name.lower()).strip("-")[:20]
                slug = f"{slug}-{acc_slug}"
            short_id = job_id.replace("-", "")[:8]
            out_path = Path(__file__).resolve().parents[1] / f"reporte-v2-{slug}-{short_id}.pdf"

            out_path.write_bytes(pdf_bytes)
            print(f"     ✓ Saved → {out_path.name}")

    await engine.dispose()


if __name__ == "__main__":
    fragments = sys.argv[1:] or DEFAULT_JOB_FRAGMENTS
    print(f"Regenerating {len(fragments)} PDFs with full AI pipeline (health eval + action plan)...")
    asyncio.run(regen(fragments))
    print("Done.")
