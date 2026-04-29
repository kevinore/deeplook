"""
Conversation-level stats — pure math.
"""
from app.analytics.metrics import ack_metrics, activity, response_time, volume
from app.models.normalized import NormalizedConversation


def conversation_stats(conv: NormalizedConversation) -> dict:
    """
    Build the deterministic stats dict for one conversation.

    All values are derived purely from message timestamps + direction + ack —
    no AI involvement. The dict is forwarded to AnalyticsEngine, which merges
    it into the final ConversationAnalysisResult before/after AI annotation.
    """
    msgs = conv.messages

    # Skip ack/operational metrics entirely for conversations the user has
    # explicitly silenced — muted/archived chats are not signals of bad service.
    skip_ack_metrics = conv.wa_is_muted or conv.wa_is_archived

    return {
        "total_messages": volume.total_messages(msgs),
        "by_direction": volume.by_direction(msgs),
        "by_type": volume.by_type(msgs),
        "first_response_time_seconds": response_time.first_response_time(msgs),
        "avg_response_time_seconds": response_time.average(msgs),
        "median_response_time_seconds": response_time.median(msgs),
        "p95_response_time_seconds": response_time.percentile_95(msgs),
        "max_response_time_seconds": response_time.max_response_time(msgs),
        "unanswered_count": response_time.unanswered_count(msgs),
        "trailing_inbound_messages": response_time.trailing_inbound_messages(msgs),
        "is_unanswered": response_time.is_unanswered(msgs),
        "response_time_by_hour": response_time.by_hour(msgs),
        "duration_minutes": activity.conversation_duration_minutes(msgs),
        "first_message_at": activity.first_message_time(msgs),
        "last_message_at": activity.last_message_time(msgs),
        "peak_hour": activity.peak_hour(msgs),
        "by_hour": activity.by_hour(msgs),
        # Ack-derived (only meaningful for WAHA-sourced conversations)
        "delivery_rate": None if skip_ack_metrics else ack_metrics.delivery_rate(msgs),
        "read_rate": None if skip_ack_metrics else ack_metrics.read_rate(msgs),
        "is_ghosted": False if skip_ack_metrics else ack_metrics.is_ghosted(msgs),
        "last_business_msg_ack": ack_metrics.last_business_msg_ack(msgs),
        # Operational coverage (in-hours answered-within-1h rate)
        "operational_coverage_score": ack_metrics.operational_coverage_score(msgs),
        "out_of_hours_inbound_pct": ack_metrics.out_of_hours_rate(msgs),
        # Chat metadata cross-checks (WAHA only)
        "wa_unread_count": conv.wa_unread_count,
        "wa_is_muted": conv.wa_is_muted,
        "wa_is_archived": conv.wa_is_archived,
    }
