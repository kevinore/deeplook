-- =====================================================================
-- Revenue metrics
-- Paste any of these into Metabase as a new SQL Question.
-- =====================================================================


-- ─── Lifetime revenue collected (COP) ─────────────────────────────────
-- Single number → Scalar visualization. Wompi stores cents, hence /100.
SELECT COALESCE(SUM(amount_in_cents), 0) / 100.0 AS revenue_cop
FROM payment_sessions
WHERE status = 'approved';


-- ─── Revenue per month (last 12 months) ───────────────────────────────
-- Best as a Bar chart with month on X, revenue on Y.
SELECT date_trunc('month', created_at)::date AS month,
       SUM(amount_in_cents) / 100.0          AS revenue_cop,
       COUNT(*)                              AS payments
FROM payment_sessions
WHERE status = 'approved'
  AND created_at > NOW() - INTERVAL '12 months'
GROUP BY 1
ORDER BY 1;


-- ─── Monthly Recurring Revenue (MRR) ──────────────────────────────────
-- Active paid subscribers × plan price. Plan prices in COP/month.
-- If you change pricing, update the multipliers here AND PLAN_DISPLAY in
-- app/billing/router.py — keep them in sync.
SELECT
    COUNT(*) FILTER (WHERE plan = 'basic')        * 160000
  + COUNT(*) FILTER (WHERE plan = 'plus')         * 250000
  + COUNT(*) FILTER (WHERE plan = 'enterprise')   * 400000
  AS mrr_cop
FROM clients
WHERE is_active = TRUE
  AND plan <> 'free'
  AND subscription_status = 'active'
  AND (plan_expires_at IS NULL OR plan_expires_at > NOW());


-- ─── Free → Paid conversion rate (lifetime, all clients) ──────────────
SELECT
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE plan <> 'free')::numeric
          / NULLIF(COUNT(*), 0),
    1
  ) AS paid_pct
FROM clients
WHERE is_active = TRUE;


-- ─── Revenue by plan (lifetime) ───────────────────────────────────────
-- Best as a Bar chart — see which plan generates the most cash.
SELECT plan,
       COUNT(*)                       AS payments,
       SUM(amount_in_cents) / 100.0   AS revenue_cop
FROM payment_sessions
WHERE status = 'approved'
GROUP BY plan
ORDER BY revenue_cop DESC;


-- ─── Failed payments (last 30 days) ───────────────────────────────────
-- Useful for spotting issues with Wompi or specific clients struggling
-- to complete checkout.
SELECT date_trunc('day', created_at)::date AS day,
       COUNT(*) FILTER (WHERE status = 'declined') AS declined,
       COUNT(*) FILTER (WHERE status = 'voided')   AS voided,
       COUNT(*) FILTER (WHERE status = 'error')    AS errored,
       COUNT(*) FILTER (WHERE status = 'pending')  AS still_pending
FROM payment_sessions
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;
