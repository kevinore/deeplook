import calendar
from dataclasses import dataclass
from datetime import datetime, timezone

# Single source of truth for plan limits.
# Mirrors PLANES_Y_PRECIOS.md exactly.
PLAN_LIMITS: dict[str, dict] = {
    "free": {
        "reports_per_month": 0,
        "conversations_per_report": 0,
        "lookback_days": 0,
        "manual_upload": False,
        "trends_dashboard": False,
    },
    "basic": {
        "reports_per_month": 1,
        "conversations_per_report": 100,
        "lookback_days": 30,
        "manual_upload": False,
        "trends_dashboard": False,
    },
    "plus": {
        "reports_per_month": 2,
        "conversations_per_report": 300,
        "lookback_days": 90,
        "manual_upload": True,
        "trends_dashboard": True,
    },
    "enterprise": {
        "reports_per_month": 4,
        "conversations_per_report": 1000,
        "lookback_days": 180,
        "manual_upload": True,
        "trends_dashboard": True,
    },
}


@dataclass
class QuotaStatus:
    plan: str
    billing_period_start: datetime
    billing_period_end: datetime
    reports_limit: int
    reports_used: int
    reports_remaining: int
    conversations_per_report: int
    lookback_days: int
    manual_upload: bool
    trends_dashboard: bool


def _add_one_month(year: int, month: int, anchor_day: int) -> datetime:
    """Return midnight UTC for anchor_day one month ahead, clamping to the month's length."""
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    days_in_next = calendar.monthrange(next_year, next_month)[1]
    return datetime(next_year, next_month, min(anchor_day, days_in_next), tzinfo=timezone.utc)


def get_billing_period(plan_started_at: datetime | None) -> tuple[datetime, datetime]:
    """
    Return (period_start, period_end) for the current billing period.

    Billing periods are subscription-anniversary based: if the user activated their
    plan on the 26th of some month, every period runs from the 26th to the 26th.

    Falls back to calendar-month (1st → 1st) when plan_started_at is None.
    """
    now = datetime.now(tz=timezone.utc)

    if plan_started_at is None:
        # Calendar-month fallback
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            period_end = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            period_end = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return period_start, period_end

    anchor_day = plan_started_at.day
    year, month = now.year, now.month

    # Clamp anchor to the actual number of days in the current month
    days_in_current = calendar.monthrange(year, month)[1]
    effective_day = min(anchor_day, days_in_current)
    period_start_candidate = datetime(year, month, effective_day, tzinfo=timezone.utc)

    if now >= period_start_candidate:
        # At or after anchor day → period runs [anchor this month → anchor next month]
        period_start = period_start_candidate
        period_end = _add_one_month(year, month, anchor_day)
    else:
        # Before anchor day → period started last month
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1
        days_in_prev = calendar.monthrange(prev_year, prev_month)[1]
        period_start = datetime(prev_year, prev_month, min(anchor_day, days_in_prev), tzinfo=timezone.utc)
        period_end = period_start_candidate

    return period_start, period_end


def build_quota_status(
    plan: str,
    jobs_used_this_period: int,
    plan_started_at: datetime | None = None,
) -> QuotaStatus:
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["basic"])
    reports_limit = limits["reports_per_month"]
    period_start, period_end = get_billing_period(plan_started_at)
    return QuotaStatus(
        plan=plan,
        billing_period_start=period_start,
        billing_period_end=period_end,
        reports_limit=reports_limit,
        reports_used=jobs_used_this_period,
        reports_remaining=max(0, reports_limit - jobs_used_this_period),
        conversations_per_report=limits["conversations_per_report"],
        lookback_days=limits["lookback_days"],
        manual_upload=limits["manual_upload"],
        trends_dashboard=limits["trends_dashboard"],
    )
