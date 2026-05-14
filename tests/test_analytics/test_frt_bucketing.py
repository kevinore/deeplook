"""
Comprehensive tests for FRT (First Response Time) distribution bucketing.

Tests the bucket_frt_distribution() function extracted from pdf_generator.py.

Key invariants tested:
  • unanswered=1 → no_reply bucket (regardless of FRT value)
  • FRT=null + unanswered=0 → excluded from all buckets (handled outside window)
  • inbound_count=0 → completely ignored
  • Bucket boundaries: <300, [300,1800), [1800,7200), ≥7200
  • CRITICAL: bucket["no_reply"] == sum(r.unanswered_count == 1) for any batch
"""
import pytest

from app.delivery.reports.pdf_generator import bucket_frt_distribution
from app.models.schemas import ConversationAnalysisResult


# ─── helper ──────────────────────────────────────────────────────────────────


def _r(
    inbound: int = 1,
    unanswered: int = 0,
    frt: float | None = None,
    conv_id: str = "c",
) -> ConversationAnalysisResult:
    return ConversationAnalysisResult(
        conversation_id=conv_id,
        inbound_count=inbound,
        outbound_count=1,
        unanswered_count=unanswered,
        first_response_time_seconds=frt,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Basic classification
# ══════════════════════════════════════════════════════════════════════════════


class TestBasicClassification:

    def test_empty_results(self):
        buckets, excluded = bucket_frt_distribution([])
        assert sum(buckets.values()) == 0
        assert excluded == 0

    def test_frt_under_300_is_lt_5min(self):
        buckets, _ = bucket_frt_distribution([_r(frt=180)])
        assert buckets["lt_5min"] == 1
        assert sum(b for k, b in buckets.items() if k != "lt_5min") == 0

    def test_frt_exactly_0_is_lt_5min(self):
        buckets, _ = bucket_frt_distribution([_r(frt=0)])
        assert buckets["lt_5min"] == 1

    def test_frt_exactly_299_is_lt_5min(self):
        buckets, _ = bucket_frt_distribution([_r(frt=299)])
        assert buckets["lt_5min"] == 1

    def test_frt_exactly_300_is_5_to_30min(self):
        """Boundary: 300s is NOT <5min, it's in [300, 1800)."""
        buckets, _ = bucket_frt_distribution([_r(frt=300)])
        assert buckets["5_to_30min"] == 1
        assert buckets["lt_5min"] == 0

    def test_frt_1799_is_5_to_30min(self):
        buckets, _ = bucket_frt_distribution([_r(frt=1799)])
        assert buckets["5_to_30min"] == 1

    def test_frt_exactly_1800_is_30min_to_2h(self):
        """Boundary: 1800s starts the 30min–2h bucket."""
        buckets, _ = bucket_frt_distribution([_r(frt=1800)])
        assert buckets["30min_to_2h"] == 1
        assert buckets["5_to_30min"] == 0

    def test_frt_7199_is_30min_to_2h(self):
        buckets, _ = bucket_frt_distribution([_r(frt=7199)])
        assert buckets["30min_to_2h"] == 1

    def test_frt_exactly_7200_is_gt_2h(self):
        """Boundary: 7200s starts the >2h bucket."""
        buckets, _ = bucket_frt_distribution([_r(frt=7200)])
        assert buckets["gt_2h"] == 1
        assert buckets["30min_to_2h"] == 0

    def test_frt_very_large_is_gt_2h(self):
        buckets, _ = bucket_frt_distribution([_r(frt=86400)])  # 24h
        assert buckets["gt_2h"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# no_reply bucket rules
# ══════════════════════════════════════════════════════════════════════════════


class TestNoReplyBucket:

    def test_unanswered_1_goes_to_no_reply_even_with_valid_frt(self):
        """unanswered_count=1 overrides FRT — conversation is unanswered."""
        buckets, _ = bucket_frt_distribution([_r(inbound=1, unanswered=1, frt=150)])
        assert buckets["no_reply"] == 1
        assert buckets["lt_5min"] == 0

    def test_unanswered_1_with_frt_none_goes_to_no_reply(self):
        buckets, _ = bucket_frt_distribution([_r(inbound=1, unanswered=1, frt=None)])
        assert buckets["no_reply"] == 1

    def test_unanswered_1_with_large_frt_goes_to_no_reply(self):
        buckets, _ = bucket_frt_distribution([_r(inbound=1, unanswered=1, frt=99999)])
        assert buckets["no_reply"] == 1
        assert buckets["gt_2h"] == 0

    def test_unanswered_0_with_frt_none_excluded_not_no_reply(self):
        """FRT=null but unanswered=0 means replied outside analysis window — excluded."""
        buckets, excluded = bucket_frt_distribution([_r(inbound=1, unanswered=0, frt=None)])
        assert buckets["no_reply"] == 0
        assert excluded == 1
        assert sum(buckets.values()) == 0

    def test_multiple_unanswered_all_go_to_no_reply(self):
        results = [_r(inbound=1, unanswered=1, frt=None) for _ in range(5)]
        buckets, _ = bucket_frt_distribution(results)
        assert buckets["no_reply"] == 5


# ══════════════════════════════════════════════════════════════════════════════
# Outbound-only exclusion
# ══════════════════════════════════════════════════════════════════════════════


class TestOutboundOnly:

    def test_inbound_0_skipped_entirely(self):
        """Business-initiated conversation with no client reply — not counted anywhere."""
        buckets, excluded = bucket_frt_distribution([_r(inbound=0, unanswered=0, frt=None)])
        assert sum(buckets.values()) == 0
        assert excluded == 0

    def test_inbound_0_with_frt_also_skipped(self):
        buckets, excluded = bucket_frt_distribution([_r(inbound=0, frt=60)])
        assert sum(buckets.values()) == 0
        assert excluded == 0

    def test_mixed_inbound_0_and_1(self):
        results = [
            _r(inbound=0, frt=60),     # skipped
            _r(inbound=1, frt=200),    # lt_5min
        ]
        buckets, _ = bucket_frt_distribution(results)
        assert buckets["lt_5min"] == 1
        assert sum(buckets.values()) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Key invariant: no_reply == total unanswered in the batch
# ══════════════════════════════════════════════════════════════════════════════


class TestKeyInvariant:

    def test_no_reply_equals_sum_of_unanswered_count(self):
        """The most critical correctness invariant in the whole FRT section."""
        results = [
            _r(inbound=1, unanswered=1, frt=None),   # unanswered
            _r(inbound=1, unanswered=1, frt=300),    # unanswered (FRT ignored)
            _r(inbound=1, unanswered=0, frt=60),     # answered fast
            _r(inbound=1, unanswered=0, frt=None),   # answered outside window
            _r(inbound=0),                            # outbound-only: ignored
        ]
        buckets, excluded = bucket_frt_distribution(results)
        total_unanswered = sum(1 for r in results if r.inbound_count > 0 and r.unanswered_count == 1)
        assert buckets["no_reply"] == total_unanswered

    def test_frt_null_answered_count_matches_excluded(self):
        results = [
            _r(inbound=1, unanswered=0, frt=None),   # excluded
            _r(inbound=1, unanswered=0, frt=None),   # excluded
            _r(inbound=1, unanswered=1, frt=None),   # no_reply
        ]
        buckets, excluded = bucket_frt_distribution(results)
        frt_null_answered_expected = sum(
            1 for r in results
            if r.inbound_count > 0 and r.first_response_time_seconds is None and r.unanswered_count == 0
        )
        assert excluded == frt_null_answered_expected
        assert excluded == 2

    def test_total_buckets_plus_excluded_equals_with_inbound(self):
        """All conversations with inbound>0 must be in buckets OR excluded."""
        results = [
            _r(inbound=1, unanswered=1, frt=None),   # no_reply
            _r(inbound=1, unanswered=0, frt=60),     # lt_5min
            _r(inbound=1, unanswered=0, frt=500),    # 5_to_30min
            _r(inbound=1, unanswered=0, frt=2000),   # 30min_to_2h
            _r(inbound=1, unanswered=0, frt=8000),   # gt_2h
            _r(inbound=1, unanswered=0, frt=None),   # excluded
            _r(inbound=0, frt=100),                   # outbound-only: skipped
        ]
        buckets, excluded = bucket_frt_distribution(results)
        with_inbound = sum(1 for r in results if r.inbound_count > 0)
        assert sum(buckets.values()) + excluded == with_inbound


# ══════════════════════════════════════════════════════════════════════════════
# Full batch with all bucket types
# ══════════════════════════════════════════════════════════════════════════════


class TestFullBatch:

    def test_all_bucket_types_in_one_batch(self):
        results = [
            _r(inbound=1, unanswered=0, frt=60, conv_id="a"),     # lt_5min
            _r(inbound=1, unanswered=0, frt=60, conv_id="b"),     # lt_5min
            _r(inbound=1, unanswered=0, frt=900, conv_id="c"),    # 5_to_30min
            _r(inbound=1, unanswered=0, frt=900, conv_id="d"),    # 5_to_30min
            _r(inbound=1, unanswered=0, frt=900, conv_id="e"),    # 5_to_30min
            _r(inbound=1, unanswered=0, frt=3600, conv_id="f"),   # 30min_to_2h
            _r(inbound=1, unanswered=0, frt=3600, conv_id="g"),   # 30min_to_2h
            _r(inbound=1, unanswered=0, frt=9000, conv_id="h"),   # gt_2h
            _r(inbound=1, unanswered=1, frt=None, conv_id="i"),   # no_reply
            _r(inbound=1, unanswered=1, frt=None, conv_id="j"),   # no_reply
            _r(inbound=1, unanswered=1, frt=None, conv_id="k"),   # no_reply
            _r(inbound=1, unanswered=0, frt=None, conv_id="l"),   # excluded
            _r(inbound=0, frt=100, conv_id="m"),                   # outbound-only
        ]
        buckets, excluded = bucket_frt_distribution(results)

        assert buckets["lt_5min"] == 2
        assert buckets["5_to_30min"] == 3
        assert buckets["30min_to_2h"] == 2
        assert buckets["gt_2h"] == 1
        assert buckets["no_reply"] == 3
        assert excluded == 1

    def test_motisss_like_distribution(self):
        """Reproduce the Motisss corrected distribution: 2/3/2/1/33, excluded=12."""
        results = (
            [_r(inbound=1, unanswered=0, frt=60)] * 2 +    # lt_5min
            [_r(inbound=1, unanswered=0, frt=900)] * 3 +   # 5_to_30min
            [_r(inbound=1, unanswered=0, frt=3600)] * 2 +  # 30min_to_2h
            [_r(inbound=1, unanswered=0, frt=9000)] * 1 +  # gt_2h
            [_r(inbound=1, unanswered=1, frt=None)] * 33 + # no_reply
            [_r(inbound=1, unanswered=0, frt=None)] * 12 + # excluded
            [_r(inbound=0)] * 26                            # outbound-only
        )
        buckets, excluded = bucket_frt_distribution(results)
        assert buckets["lt_5min"] == 2
        assert buckets["5_to_30min"] == 3
        assert buckets["30min_to_2h"] == 2
        assert buckets["gt_2h"] == 1
        assert buckets["no_reply"] == 33
        assert excluded == 12
        # Total buckets + excluded = conversations with inbound
        assert sum(buckets.values()) + excluded == 53
