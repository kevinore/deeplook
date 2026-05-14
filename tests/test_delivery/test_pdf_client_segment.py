"""
Tests for build_client_frt_segments() in pdf_generator.

Core invariant:
  A conversation with FRT != None AND unanswered_count == 1 means the business
  initially responded (FRT is real) but the client later sent more messages that
  were never answered. bucket_frt_distribution() puts it in the 'no_reply' bucket.
  build_client_frt_segments() must do the same — exclude it from frt_count and median
  so both functions are consistent and "X de Y respondidas" is accurate.
"""

import statistics

import pytest

from app.delivery.reports.pdf_generator import (
    bucket_frt_distribution,
    build_client_frt_segments,
)
from app.models.schemas import ConversationAnalysisResult


# ─── helpers ────────────────────────────────────────────────────────────────


def _r(
    *,
    client_relationship: str | None = None,
    frt: float | None = None,
    unanswered: int = 0,
    inbound: int = 1,
    outbound: int = 1,
    conversation_id: str = "x",
) -> ConversationAnalysisResult:
    return ConversationAnalysisResult(
        conversation_id=conversation_id,
        client_relationship=client_relationship,
        first_response_time_seconds=frt,
        unanswered_count=unanswered,
        inbound_count=inbound,
        outbound_count=outbound,
    )


# ─── Section 1 — Empty and degenerate inputs ────────────────────────────────


class TestEmpty:
    def test_empty_results(self):
        seg = build_client_frt_segments([])
        assert seg["new_client_count"] == 0
        assert seg["returning_client_count"] == 0
        assert seg["new_client_inbound_count"] == 0
        assert seg["returning_client_inbound_count"] == 0
        assert seg["new_client_frt_count"] == 0
        assert seg["returning_client_frt_count"] == 0
        assert seg["median_frt_new_clients"] is None
        assert seg["median_frt_returning_clients"] is None
        assert seg["frt_multiplier"] is None
        assert seg["frt_segment_insight"] is None

    def test_no_new_clients_only_returning(self):
        seg = build_client_frt_segments([_r(client_relationship="returning", frt=300)])
        assert seg["new_client_count"] == 0
        assert seg["new_client_inbound_count"] == 0
        assert seg["new_client_frt_count"] == 0
        assert seg["median_frt_new_clients"] is None
        assert seg["frt_segment_insight"] is None  # no insight without new clients FRT

    def test_only_internal_and_uncertain_ignored(self):
        results = [
            _r(client_relationship="internal", frt=100),
            _r(client_relationship="uncertain", frt=200),
            _r(client_relationship=None, frt=300),
        ]
        seg = build_client_frt_segments(results)
        assert seg["new_client_count"] == 0
        assert seg["returning_client_count"] == 0
        assert seg["new_client_frt_count"] == 0
        assert seg["returning_client_frt_count"] == 0


# ─── Section 2 — Counting: new_client_count vs inbound vs frt ───────────────


class TestCounting:
    def test_new_all_outbound_only(self):
        """Outbound-only contacts: counted in new_client_count but NOT inbound_count."""
        results = [_r(client_relationship="new", frt=None, unanswered=0, inbound=0, outbound=3)]
        seg = build_client_frt_segments(results)
        assert seg["new_client_count"] == 1
        assert seg["new_client_inbound_count"] == 0
        assert seg["new_client_frt_count"] == 0

    def test_new_inbound_never_answered(self):
        """Client wrote in (inbound>0) but business never replied (frt=None, unanswered=1)."""
        results = [_r(client_relationship="new", frt=None, unanswered=1, inbound=2)]
        seg = build_client_frt_segments(results)
        assert seg["new_client_count"] == 1
        assert seg["new_client_inbound_count"] == 1
        assert seg["new_client_frt_count"] == 0  # never answered → 0 FRT count

    def test_new_inbound_fully_answered(self):
        """Business responded and conversation is current (unanswered=0)."""
        results = [_r(client_relationship="new", frt=300, unanswered=0, inbound=3)]
        seg = build_client_frt_segments(results)
        assert seg["new_client_count"] == 1
        assert seg["new_client_inbound_count"] == 1
        assert seg["new_client_frt_count"] == 1

    def test_inbound_count_includes_unanswered(self):
        """Denominator (inbound_count) includes unanswered chats — they DID write in."""
        results = [
            _r(client_relationship="new", frt=300, unanswered=0, inbound=5),   # answered
            _r(client_relationship="new", frt=None, unanswered=1, inbound=2),  # unanswered
            _r(client_relationship="new", frt=None, unanswered=1, inbound=1),  # unanswered
        ]
        seg = build_client_frt_segments(results)
        assert seg["new_client_inbound_count"] == 3   # all three have inbound > 0
        assert seg["new_client_frt_count"] == 1       # only the answered one

    def test_frt_count_never_exceeds_inbound_count(self):
        """Invariant: frt_count ≤ inbound_count always."""
        results = [
            _r(client_relationship="new", frt=100, unanswered=0),
            _r(client_relationship="new", frt=200, unanswered=0),
            _r(client_relationship="new", frt=None, unanswered=1),
            _r(client_relationship="new", frt=None, unanswered=0, inbound=0),  # outbound-only
        ]
        seg = build_client_frt_segments(results)
        assert seg["new_client_frt_count"] <= seg["new_client_inbound_count"]

    def test_outside_window_excluded_from_frt_count(self):
        """Null FRT + unanswered=0 + inbound>0 = responded outside analysis window.
        Included in inbound denominator but NOT in frt_count."""
        results = [
            _r(client_relationship="new", frt=None, unanswered=0, inbound=1),  # outside window
            _r(client_relationship="new", frt=300, unanswered=0, inbound=4),   # normal
        ]
        seg = build_client_frt_segments(results)
        assert seg["new_client_inbound_count"] == 2
        assert seg["new_client_frt_count"] == 1  # only the one with measured FRT

    def test_multiple_new_conversations(self):
        results = [_r(client_relationship="new", frt=i * 100, unanswered=0) for i in range(1, 6)]
        seg = build_client_frt_segments(results)
        assert seg["new_client_count"] == 5
        assert seg["new_client_inbound_count"] == 5
        assert seg["new_client_frt_count"] == 5


# ─── Section 3 — THE BUG: FRT exists AND unanswered == 1 ────────────────────


class TestFrtPlusUnansweredBug:
    """
    The core bug: a conversation where business replied initially (FRT != None)
    but the client later sent more messages that were never answered (unanswered=1).
    bucket_frt_distribution puts these in 'no_reply'.
    build_client_frt_segments MUST exclude them from frt_count and median.
    """

    def test_frt_present_but_unanswered_excluded_from_frt_count(self):
        r = _r(client_relationship="new", frt=1314, unanswered=1, inbound=3)
        seg = build_client_frt_segments([r])
        assert seg["new_client_frt_count"] == 0

    def test_frt_present_but_unanswered_excluded_from_median(self):
        results = [
            _r(client_relationship="new", frt=100, unanswered=0),   # answered
            _r(client_relationship="new", frt=1314, unanswered=1),  # bug case: should NOT skew median
            _r(client_relationship="new", frt=1870, unanswered=1),  # bug case: should NOT skew median
        ]
        seg = build_client_frt_segments(results)
        # Only the answered one contributes → median == 100s
        assert seg["new_client_frt_count"] == 1
        assert seg["median_frt_new_clients"] == 100

    def test_two_bug_cases_inflate_median_if_not_filtered(self):
        """Demonstrate that without the fix, median would be 629s (10.5min) not 304s (5min).
        This reproduces the exact numbers from job 1763ef45."""
        answered = [130, 228, 304, 629, 5116]       # 5 properly answered
        unanswered_with_frt = [1314, 1870]           # 2 bug cases
        all_frt = sorted(answered + unanswered_with_frt)

        # Current WRONG median (without fix) would be:
        wrong_median = statistics.median(all_frt)
        assert abs(wrong_median - 629) < 1  # 629s ≈ 10.5min (what report showed)

        # Correct median (with fix, answered-only):
        correct_median = statistics.median(answered)
        assert abs(correct_median - 304) < 1  # 304s ≈ 5min

    def test_bug_case_does_count_in_inbound_denominator(self):
        """A conversation with FRT+unanswered=1 still had inbound messages → counts in denominator."""
        r = _r(client_relationship="new", frt=1314, unanswered=1, inbound=3)
        seg = build_client_frt_segments([r])
        assert seg["new_client_inbound_count"] == 1  # client DID write in
        assert seg["new_client_frt_count"] == 0      # but counts as unanswered

    def test_bug_case_consistent_with_frt_distribution(self):
        """After fix: new_client_frt_count == count of new clients in FRT time buckets."""
        results = [
            _r(client_relationship="new", frt=130, unanswered=0, inbound=5),
            _r(client_relationship="new", frt=228, unanswered=0, inbound=3),
            _r(client_relationship="new", frt=304, unanswered=0, inbound=2),
            _r(client_relationship="new", frt=1314, unanswered=1, inbound=3),   # bug case
            _r(client_relationship="new", frt=1870, unanswered=1, inbound=13),  # bug case
            _r(client_relationship="new", frt=None, unanswered=1, inbound=1),
            _r(client_relationship="returning", frt=305, unanswered=0, inbound=2),
        ]
        seg = build_client_frt_segments(results)
        buckets, _ = bucket_frt_distribution(results)

        # All conversations with FRT in time buckets:
        # new: 130(lt_5min), 228(lt_5min), 304(5_to_30min) = 3 new in time buckets
        # returning: 305(5_to_30min) = 1 returning in time bucket
        new_in_buckets = buckets["lt_5min"] + buckets["5_to_30min"] + buckets["30min_to_2h"] + buckets["gt_2h"]
        # (This includes returning too, so we need to count new specifically)
        # Verify: new_client_frt_count matches new clients' entries in time buckets
        assert seg["new_client_frt_count"] == 3

        # Verify distribution: 2 bug cases + 1 null-unanswered = 3 in no_reply for new
        # plus 0 returning unanswered, total no_reply = 3
        assert buckets["no_reply"] == 3

    def test_full_job_1763ef45_reproduction(self):
        """Exact numbers from job 1763ef45 that triggered the bug report.
        Before fix: 7 de 20, median 10min, multiplier 2.1x
        After fix:  5 de 20, median 5min, multiplier 1.0x
        """
        results = [
            # 10 new never-responded (null FRT, unanswered=1, inbound=1)
            *[_r(client_relationship="new", frt=None, unanswered=1, inbound=1,
                 conversation_id=f"nu-{i}") for i in range(10)],
            # 1 new never-responded (inbound=2)
            _r(client_relationship="new", frt=None, unanswered=1, inbound=2, conversation_id="nu-10"),
            # 1 new never-responded (inbound=4)
            _r(client_relationship="new", frt=None, unanswered=1, inbound=4, conversation_id="nu-11"),
            # 2 new: FRT exists BUT unanswered=1 (the bug cases)
            _r(client_relationship="new", frt=1314, unanswered=1, inbound=3, conversation_id="bug-1"),
            _r(client_relationship="new", frt=1870, unanswered=1, inbound=13, conversation_id="bug-2"),
            # 16 new outbound-only
            *[_r(client_relationship="new", frt=None, unanswered=0, inbound=0, outbound=1,
                 conversation_id=f"out-{i}") for i in range(16)],
            # 1 new outside window (null FRT, unanswered=0, inbound=1)
            _r(client_relationship="new", frt=None, unanswered=0, inbound=1, conversation_id="ow-1"),
            # 5 new properly answered
            _r(client_relationship="new", frt=130, unanswered=0, inbound=18, conversation_id="ans-1"),
            _r(client_relationship="new", frt=228, unanswered=0, inbound=10, conversation_id="ans-2"),
            _r(client_relationship="new", frt=304, unanswered=0, inbound=9, conversation_id="ans-3"),
            _r(client_relationship="new", frt=629, unanswered=0, inbound=2, conversation_id="ans-4"),
            _r(client_relationship="new", frt=5116, unanswered=0, inbound=4, conversation_id="ans-5"),
            # 1 returning properly answered
            _r(client_relationship="returning", frt=305, unanswered=0, inbound=2, conversation_id="ret-1"),
            # 1 uncertain unanswered
            _r(client_relationship="uncertain", frt=None, unanswered=1, inbound=1, conversation_id="unc-1"),
            # 1 uncertain outbound-only
            _r(client_relationship="uncertain", frt=None, unanswered=0, inbound=0, conversation_id="unc-2"),
        ]

        seg = build_client_frt_segments(results)

        # new_client_count: all new rows = 10+1+1+2+16+1+5 = 36
        assert seg["new_client_count"] == 36
        # new_client_inbound_count: new with inbound > 0 = 10+1+1+2+1+5 = 20
        assert seg["new_client_inbound_count"] == 20
        # new_client_frt_count: only answered new (not unanswered) with FRT = 5
        assert seg["new_client_frt_count"] == 5  # was 7 before fix
        # median FRT new (answered only): median([130,228,304,629,5116]) = 304s ≈ 5min
        assert seg["median_frt_new_clients"] == 304  # was 629s before fix
        # returning
        assert seg["returning_client_count"] == 1
        assert seg["returning_client_frt_count"] == 1
        assert seg["median_frt_returning_clients"] == 305
        # multiplier: 304/305 ≈ 1.0 (consistent)
        assert seg["frt_multiplier"] == 1.0  # was 2.1 before fix
        # insight should say "similar speeds"
        assert "similares" in seg["frt_segment_insight"]


# ─── Section 4 — FRT median computation ─────────────────────────────────────


class TestMedian:
    def test_median_single_value(self):
        seg = build_client_frt_segments([_r(client_relationship="new", frt=300, unanswered=0)])
        assert seg["median_frt_new_clients"] == 300

    def test_median_odd_count(self):
        results = [_r(client_relationship="new", frt=v, unanswered=0, conversation_id=f"r{i}")
                   for i, v in enumerate([100, 200, 300, 400, 500])]
        seg = build_client_frt_segments(results)
        assert seg["median_frt_new_clients"] == 300

    def test_median_even_count(self):
        results = [_r(client_relationship="new", frt=v, unanswered=0, conversation_id=f"r{i}")
                   for i, v in enumerate([100, 200, 300, 400])]
        seg = build_client_frt_segments(results)
        assert seg["median_frt_new_clients"] == 250  # avg of middle two

    def test_median_none_when_all_unanswered(self):
        results = [
            _r(client_relationship="new", frt=None, unanswered=1),
            _r(client_relationship="new", frt=500, unanswered=1),  # FRT but unanswered → excluded
        ]
        seg = build_client_frt_segments(results)
        assert seg["median_frt_new_clients"] is None

    def test_median_none_when_no_new_clients(self):
        seg = build_client_frt_segments([_r(client_relationship="returning", frt=300)])
        assert seg["median_frt_new_clients"] is None

    def test_median_uses_float_values(self):
        results = [_r(client_relationship="new", frt=61.5, unanswered=0)]
        seg = build_client_frt_segments(results)
        assert seg["median_frt_new_clients"] == 61.5

    def test_returning_median_independent_of_new(self):
        results = [
            _r(client_relationship="new", frt=100, unanswered=0, conversation_id="n1"),
            _r(client_relationship="returning", frt=1000, unanswered=0, conversation_id="r1"),
        ]
        seg = build_client_frt_segments(results)
        assert seg["median_frt_new_clients"] == 100
        assert seg["median_frt_returning_clients"] == 1000


# ─── Section 5 — frt_multiplier ─────────────────────────────────────────────


class TestMultiplier:
    def test_multiplier_computed_correctly(self):
        results = [
            _r(client_relationship="new", frt=600, unanswered=0, conversation_id="n1"),
            _r(client_relationship="returning", frt=200, unanswered=0, conversation_id="r1"),
        ]
        seg = build_client_frt_segments(results)
        assert seg["frt_multiplier"] == 3.0  # 600/200 = 3.0

    def test_multiplier_rounds_to_one_decimal(self):
        results = [
            _r(client_relationship="new", frt=220, unanswered=0, conversation_id="n1"),
            _r(client_relationship="returning", frt=100, unanswered=0, conversation_id="r1"),
        ]
        seg = build_client_frt_segments(results)
        assert seg["frt_multiplier"] == 2.2  # 220/100 = 2.2 exactly

    def test_multiplier_none_when_no_returning(self):
        seg = build_client_frt_segments([_r(client_relationship="new", frt=500, unanswered=0)])
        assert seg["frt_multiplier"] is None

    def test_multiplier_none_when_returning_has_no_frt(self):
        results = [
            _r(client_relationship="new", frt=500, unanswered=0, conversation_id="n1"),
            _r(client_relationship="returning", frt=None, unanswered=1, conversation_id="r1"),
        ]
        seg = build_client_frt_segments(results)
        assert seg["frt_multiplier"] is None  # returning has no qualifying FRT

    def test_multiplier_none_when_new_has_no_frt(self):
        results = [
            _r(client_relationship="new", frt=None, unanswered=1, conversation_id="n1"),
            _r(client_relationship="returning", frt=300, unanswered=0, conversation_id="r1"),
        ]
        seg = build_client_frt_segments(results)
        assert seg["frt_multiplier"] is None  # no new client FRT → no insight either

    def test_multiplier_none_when_returning_frt_all_unanswered(self):
        """returning has FRT values but all are unanswered → excluded → multiplier None."""
        results = [
            _r(client_relationship="new", frt=300, unanswered=0, conversation_id="n1"),
            _r(client_relationship="returning", frt=100, unanswered=1, conversation_id="r1"),
        ]
        seg = build_client_frt_segments(results)
        assert seg["frt_multiplier"] is None

    def test_multiplier_less_than_one_when_new_faster(self):
        results = [
            _r(client_relationship="new", frt=100, unanswered=0, conversation_id="n1"),
            _r(client_relationship="returning", frt=300, unanswered=0, conversation_id="r1"),
        ]
        seg = build_client_frt_segments(results)
        assert seg["frt_multiplier"] == round(100 / 300, 1)

    def test_multiplier_equal_speeds(self):
        results = [
            _r(client_relationship="new", frt=300, unanswered=0, conversation_id="n1"),
            _r(client_relationship="returning", frt=300, unanswered=0, conversation_id="r1"),
        ]
        seg = build_client_frt_segments(results)
        assert seg["frt_multiplier"] == 1.0


# ─── Section 6 — frt_segment_insight text ───────────────────────────────────


class TestInsightText:
    def test_only_new_clients_no_multiplier(self):
        seg = build_client_frt_segments([_r(client_relationship="new", frt=600, unanswered=0)])
        assert seg["frt_segment_insight"] is not None
        assert "tardas en promedio" in seg["frt_segment_insight"]
        assert "10min" in seg["frt_segment_insight"]

    def test_insight_singular_cliente(self):
        seg = build_client_frt_segments([_r(client_relationship="new", frt=300, unanswered=0)])
        assert "1 cliente nuevo" in seg["frt_segment_insight"]

    def test_insight_plural_clientes(self):
        results = [
            _r(client_relationship="new", frt=300, unanswered=0, conversation_id="n1"),
            _r(client_relationship="new", frt=400, unanswered=0, conversation_id="n2"),
        ]
        seg = build_client_frt_segments(results)
        assert "2 clientes nuevos" in seg["frt_segment_insight"]

    def test_insight_multiplier_gte_3(self):
        results = [
            _r(client_relationship="new", frt=900, unanswered=0, conversation_id="n1"),
            _r(client_relationship="returning", frt=300, unanswered=0, conversation_id="r1"),
        ]
        seg = build_client_frt_segments(results)
        assert seg["frt_multiplier"] == 3.0
        assert "primera impresión es donde más se pierden ventas" in seg["frt_segment_insight"]

    def test_insight_multiplier_between_15_and_3(self):
        results = [
            _r(client_relationship="new", frt=450, unanswered=0, conversation_id="n1"),
            _r(client_relationship="returning", frt=200, unanswered=0, conversation_id="r1"),
        ]
        seg = build_client_frt_segments(results)
        assert 1.5 <= seg["frt_multiplier"] < 3.0
        assert "oportunidad de mejorar la primera impresión" in seg["frt_segment_insight"]

    def test_insight_multiplier_lt_15_similar_speeds(self):
        results = [
            _r(client_relationship="new", frt=300, unanswered=0, conversation_id="n1"),
            _r(client_relationship="returning", frt=305, unanswered=0, conversation_id="r1"),
        ]
        seg = build_client_frt_segments(results)
        assert seg["frt_multiplier"] < 1.5
        assert "similares" in seg["frt_segment_insight"]

    def test_insight_none_when_new_has_no_qualifying_frt(self):
        results = [
            _r(client_relationship="new", frt=None, unanswered=1),
            _r(client_relationship="new", frt=500, unanswered=1),   # FRT but unanswered → excluded
        ]
        seg = build_client_frt_segments(results)
        assert seg["frt_segment_insight"] is None

    def test_insight_none_when_no_new_clients(self):
        seg = build_client_frt_segments([_r(client_relationship="returning", frt=300)])
        assert seg["frt_segment_insight"] is None

    def test_insight_references_multiplier_value(self):
        results = [
            _r(client_relationship="new", frt=600, unanswered=0, conversation_id="n1"),
            _r(client_relationship="returning", frt=200, unanswered=0, conversation_id="r1"),
        ]
        seg = build_client_frt_segments(results)
        assert "3.0x" in seg["frt_segment_insight"]


# ─── Section 7 — Consistency with bucket_frt_distribution ───────────────────


class TestConsistencyWithBuckets:
    """
    After the fix, the count of new clients with measurable FRT must equal
    the count of new clients that appear in the time-based FRT buckets
    (lt_5min + 5_to_30min + 30min_to_2h + gt_2h).
    """

    def _new_clients_in_time_buckets(self, new_results):
        """Count how many new-client conversations land in FRT time buckets."""
        buckets, _ = bucket_frt_distribution(new_results)
        return buckets["lt_5min"] + buckets["5_to_30min"] + buckets["30min_to_2h"] + buckets["gt_2h"]

    def test_all_answered_consistent(self):
        results = [_r(client_relationship="new", frt=v, unanswered=0, conversation_id=f"n{i}")
                   for i, v in enumerate([60, 300, 600, 3600, 10000])]
        seg = build_client_frt_segments(results)
        in_buckets = self._new_clients_in_time_buckets(results)
        assert seg["new_client_frt_count"] == in_buckets

    def test_bug_cases_consistent(self):
        results = [
            _r(client_relationship="new", frt=130, unanswered=0, conversation_id="n1"),
            _r(client_relationship="new", frt=228, unanswered=0, conversation_id="n2"),
            _r(client_relationship="new", frt=1314, unanswered=1, conversation_id="bug1"),  # bug
            _r(client_relationship="new", frt=1870, unanswered=1, conversation_id="bug2"),  # bug
            _r(client_relationship="new", frt=None, unanswered=1, conversation_id="n3"),
        ]
        seg = build_client_frt_segments(results)
        in_buckets = self._new_clients_in_time_buckets(results)
        assert seg["new_client_frt_count"] == in_buckets == 2

    def test_no_reply_count_consistent(self):
        """no_reply bucket count == conversations with unanswered_count == 1 and inbound > 0."""
        results = [
            _r(client_relationship="new", frt=1314, unanswered=1, inbound=3, conversation_id="bug1"),
            _r(client_relationship="new", frt=None, unanswered=1, inbound=1, conversation_id="n1"),
            _r(client_relationship="new", frt=None, unanswered=1, inbound=1, conversation_id="n2"),
            _r(client_relationship="new", frt=300, unanswered=0, inbound=5, conversation_id="n3"),
        ]
        buckets, _ = bucket_frt_distribution(results)
        assert buckets["no_reply"] == 3  # both bug + 2 null FRT

    def test_excluded_count_is_outside_window(self):
        """Null FRT, unanswered=0, inbound>0 → excluded from all buckets."""
        results = [
            _r(client_relationship="new", frt=None, unanswered=0, inbound=1, conversation_id="ow"),
            _r(client_relationship="new", frt=300, unanswered=0, inbound=5, conversation_id="n"),
        ]
        _, excluded = bucket_frt_distribution(results)
        seg = build_client_frt_segments(results)
        assert excluded == 1
        assert seg["new_client_frt_count"] == 1  # only the answered one


# ─── Section 8 — Multiple conversations, same type ──────────────────────────


class TestMultipleConversations:
    def test_multiple_new_different_frt_median(self):
        values = [120, 180, 240, 360, 480]
        results = [_r(client_relationship="new", frt=v, unanswered=0, conversation_id=f"n{i}")
                   for i, v in enumerate(values)]
        seg = build_client_frt_segments(results)
        assert seg["new_client_frt_count"] == 5
        assert seg["median_frt_new_clients"] == 240

    def test_mix_new_returning_internal_uncertain(self):
        results = [
            _r(client_relationship="new", frt=200, unanswered=0, conversation_id="n1"),
            _r(client_relationship="new", frt=400, unanswered=0, conversation_id="n2"),
            _r(client_relationship="returning", frt=100, unanswered=0, conversation_id="r1"),
            _r(client_relationship="internal", frt=50, unanswered=0, conversation_id="i1"),
            _r(client_relationship="uncertain", frt=75, unanswered=0, conversation_id="u1"),
        ]
        seg = build_client_frt_segments(results)
        assert seg["new_client_count"] == 2
        assert seg["new_client_frt_count"] == 2
        assert seg["returning_client_count"] == 1
        assert seg["returning_client_frt_count"] == 1
        assert seg["median_frt_new_clients"] == 300  # (200+400)/2
        assert seg["median_frt_returning_clients"] == 100

    def test_many_unanswered_reduces_frt_count_dramatically(self):
        answered = [_r(client_relationship="new", frt=300, unanswered=0, conversation_id=f"a{i}")
                    for i in range(3)]
        unanswered = [_r(client_relationship="new", frt=None, unanswered=1, conversation_id=f"u{i}")
                      for i in range(12)]
        results = answered + unanswered
        seg = build_client_frt_segments(results)
        assert seg["new_client_inbound_count"] == 15
        assert seg["new_client_frt_count"] == 3
        # Label would correctly say "3 de 15 conversaciones respondidas"

    def test_all_unanswered_with_frt_none_means_no_insight(self):
        results = [_r(client_relationship="new", frt=None, unanswered=1, conversation_id=f"n{i}")
                   for i in range(5)]
        seg = build_client_frt_segments(results)
        assert seg["new_client_frt_count"] == 0
        assert seg["median_frt_new_clients"] is None
        assert seg["frt_segment_insight"] is None
