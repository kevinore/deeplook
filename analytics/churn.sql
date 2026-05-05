-- =====================================================================
-- Churn & retention metrics
-- Who's leaving, and why?
-- =====================================================================


-- ─── Plans that expired in the last 30 days without renewing ──────────
-- A churn signal: was paying, now downgraded to free.
SELECT COUNT(*) AS churned_last_30d
FROM clients
WHERE plan = 'free'
  AND plan_expires_at IS NOT NULL
  AND plan_expires_at < NOW()
  AND plan_expires_at > NOW() - INTERVAL '30 days';


-- ─── Currently expired clients (any time) ─────────────────────────────
-- Who to target with a winback campaign.
SELECT email,
       business_name,
       plan_expires_at,
       NOW() - plan_expires_at AS expired_for
FROM clients
WHERE is_active = TRUE
  AND plan = 'free'
  AND plan_expires_at IS NOT NULL
  AND plan_expires_at < NOW()
ORDER BY plan_expires_at DESC;


-- ─── Active subscribers expiring in the next 7 days ───────────────────
-- Renewal opportunity — RenewalBanner should already nudge them in-app.
SELECT email,
       business_name,
       plan,
       plan_expires_at,
       plan_expires_at - NOW() AS time_remaining
FROM clients
WHERE is_active = TRUE
  AND plan <> 'free'
  AND plan_expires_at IS NOT NULL
  AND plan_expires_at BETWEEN NOW() AND NOW() + INTERVAL '7 days'
ORDER BY plan_expires_at ASC;


-- ─── Cohort retention: signups by month, % still active ───────────────
-- A coarse retention view. Run this monthly and compare cohorts.
SELECT
  date_trunc('month', created_at)::date            AS signup_month,
  COUNT(*)                                         AS signed_up,
  COUNT(*) FILTER (WHERE is_active = TRUE)         AS still_active,
  COUNT(*) FILTER (
    WHERE is_active = TRUE AND plan <> 'free'
  )                                                AS still_paying,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE is_active = TRUE AND plan <> 'free')::numeric
          / NULLIF(COUNT(*), 0),
    1
  )                                                AS paying_pct
FROM clients
WHERE created_at > NOW() - INTERVAL '12 months'
GROUP BY 1
ORDER BY 1;
