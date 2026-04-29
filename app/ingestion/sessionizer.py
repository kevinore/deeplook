"""
Conversation sessionizer.

A WhatsApp "chat" can span months or years and contain dozens of independent
buying journeys. Treating the whole chat as a single NormalizedConversation
produces one giant transcript that is impossible for the AI to summarise
coherently and a single quality_score that averages a 6-month-old great
interaction with a recent bad one.

This module splits a chat into "sessions" wherever there's a quiet gap longer
than `gap_hours` between consecutive messages. Each session is a self-contained
interaction that gets its own AI analysis, sentiment, quality, and conversion
classification.

Design choice — gap threshold:
    Default 6 hours. Empirical reasoning for Colombian MiPymes:
      • A normal back-and-forth conversation rarely pauses > 4h
      • Customer follow-ups within the same day stay one session
      • Next-day return = new buying intention = new session
      • Tunable via env / settings if a business has different cadence
"""
from typing import Iterable

from app.models.normalized import NormalizedConversation, NormalizedMessage

DEFAULT_SESSION_GAP_HOURS = 6.0


def split_into_sessions(
    conv: NormalizedConversation,
    gap_hours: float = DEFAULT_SESSION_GAP_HOURS,
) -> list[NormalizedConversation]:
    """
    Split a conversation into sessions wherever the gap between consecutive
    messages reaches `gap_hours`.

    Returns:
      • [conv] (with session_count=1) if the chat has < 2 messages or
        gap_hours <= 0 — nothing to split.
      • A list of new NormalizedConversation objects, each carrying:
          - the same contact + WAHA chat metadata,
          - a contiguous slice of messages,
          - session_index (0-based) and session_count (total sessions for the chat).

    The original `conv` is not mutated.
    """
    msgs = list(conv.messages)
    if gap_hours <= 0 or len(msgs) < 2:
        return [conv.model_copy(update={"session_index": 0, "session_count": 1})]

    sorted_msgs = sorted(msgs, key=lambda m: m.timestamp)
    gap_seconds = gap_hours * 3600.0

    # Group messages into sessions
    groups: list[list[NormalizedMessage]] = [[sorted_msgs[0]]]
    for prev, curr in zip(sorted_msgs, sorted_msgs[1:]):
        delta = (curr.timestamp - prev.timestamp).total_seconds()
        if delta >= gap_seconds:
            groups.append([curr])
        else:
            groups[-1].append(curr)

    if len(groups) == 1:
        return [conv.model_copy(update={"session_index": 0, "session_count": 1})]

    sessions: list[NormalizedConversation] = []
    total = len(groups)
    for idx, group in enumerate(groups):
        sessions.append(
            conv.model_copy(update={
                "messages": group,
                "session_index": idx,
                "session_count": total,
            })
        )
    return sessions


def split_batch_into_sessions(
    conversations: Iterable[NormalizedConversation],
    gap_hours: float = DEFAULT_SESSION_GAP_HOURS,
) -> list[NormalizedConversation]:
    """Convenience helper: apply split_into_sessions to each conversation in an iterable."""
    out: list[NormalizedConversation] = []
    for conv in conversations:
        out.extend(split_into_sessions(conv, gap_hours=gap_hours))
    return out


# ─── Junk-conversation filter (S1) ───────────────────────────────────────────


def is_junk_conversation(
    conv: NormalizedConversation,
    min_messages: int = 2,
) -> bool:
    """
    Returns True if a conversation should be excluded from analysis as
    too noisy / too sparse to produce meaningful metrics.

    Today the only criterion is `len(messages) < min_messages`. A 1-message chat
    cannot tell us anything about the business's response — it's typically a
    misdirected message, accidental contact, or test.

    NOTE: zero-outbound conversations are NOT junk — those are exactly the
    "sin responder" cases we MUST surface in the report. Don't filter them.
    """
    return len(conv.messages) < min_messages


def filter_junk(
    conversations: Iterable[NormalizedConversation],
    min_messages: int = 2,
) -> list[NormalizedConversation]:
    return [c for c in conversations if not is_junk_conversation(c, min_messages=min_messages)]
