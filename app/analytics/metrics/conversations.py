"""
Conversation-level stats — pure math.
"""
from app.analytics.metrics import activity, response_time, volume
from app.models.normalized import NormalizedConversation


def conversation_stats(conv: NormalizedConversation) -> dict:
    msgs = conv.messages
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
        "response_time_by_hour": response_time.by_hour(msgs),
        "duration_minutes": activity.conversation_duration_minutes(msgs),
        "first_message_at": activity.first_message_time(msgs),
        "last_message_at": activity.last_message_time(msgs),
        "peak_hour": activity.peak_hour(msgs),
        "by_hour": activity.by_hour(msgs),
    }
