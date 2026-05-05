-- =====================================================================
-- Product usage metrics
-- How much value is the product actually delivering?
-- =====================================================================


-- ─── Reports generated (lifetime) ─────────────────────────────────────
SELECT COUNT(*) AS reports
FROM analysis_jobs
WHERE status = 'completed';


-- ─── Reports per day (last 60 days) ───────────────────────────────────
-- Line chart. Watch this go up over time as connections accumulate.
SELECT date_trunc('day', completed_at)::date AS day,
       COUNT(*)                              AS reports
FROM analysis_jobs
WHERE status = 'completed'
  AND completed_at > NOW() - INTERVAL '60 days'
GROUP BY 1
ORDER BY 1;


-- ─── Reports per plan tier ────────────────────────────────────────────
-- Are paid plans actually being used? If basic users barely run reports,
-- the value prop may be mismatched.
SELECT c.plan,
       COUNT(j.id)                           AS reports,
       AVG(j.total_conversations)::numeric(10,1) AS avg_convs_per_report
FROM clients c
LEFT JOIN analysis_jobs j ON j.client_id = c.id AND j.status = 'completed'
WHERE c.is_active
GROUP BY c.plan
ORDER BY reports DESC;


-- ─── AI cost vs revenue (gross-margin sanity check) ───────────────────
-- The ratio matters: if AI cost is approaching revenue, plans are
-- under-priced or you're hitting the wrong AI provider.
-- USD-COP ~ 4000 in 2026; adjust the divisor if rates drift heavily.
SELECT
  COALESCE(SUM(j.total_cost_usd), 0)                                              AS ai_cost_usd_lifetime,
  (SELECT COALESCE(SUM(amount_in_cents), 0) / 100.0 / 4000.0
   FROM payment_sessions WHERE status = 'approved')                               AS revenue_usd_approx,
  (SELECT COALESCE(SUM(amount_in_cents), 0) / 100.0 / 4000.0
   FROM payment_sessions WHERE status = 'approved')
  - COALESCE(SUM(j.total_cost_usd), 0)                                            AS gross_profit_usd
FROM analysis_jobs j;


-- ─── AI cost per report (last 30 days) ────────────────────────────────
-- Spot if a model change or prompt change blew up costs.
SELECT date_trunc('day', completed_at)::date AS day,
       COUNT(*)                              AS reports,
       AVG(total_cost_usd)::numeric(10,4)    AS avg_cost_per_report_usd,
       SUM(total_cost_usd)::numeric(10,4)    AS total_cost_usd
FROM analysis_jobs
WHERE status = 'completed'
  AND completed_at > NOW() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;


-- ─── WhatsApp connection health ───────────────────────────────────────
-- Distribution of WAHA session statuses across the platform.
SELECT status, COUNT(*) AS connections
FROM whatsapp_connections
GROUP BY status
ORDER BY connections DESC;


-- ─── Stale connections (haven't synced in >48h) ───────────────────────
-- Candidates for the "reconnect your WhatsApp" email.
SELECT c.email,
       c.business_name,
       wc.status,
       wc.last_sync_at,
       NOW() - wc.last_sync_at AS time_since_last_sync
FROM whatsapp_connections wc
JOIN clients c ON c.id = wc.client_id
WHERE wc.last_sync_at < NOW() - INTERVAL '48 hours'
ORDER BY wc.last_sync_at ASC;
