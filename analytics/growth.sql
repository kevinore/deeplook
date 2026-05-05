-- =====================================================================
-- Growth metrics
-- Paste any of these into Metabase as a new SQL Question.
-- =====================================================================


-- ─── Total active clients ─────────────────────────────────────────────
-- Single number, good for a Scalar visualization.
SELECT COUNT(*) AS total_clients
FROM clients
WHERE is_active = TRUE;


-- ─── New signups per day (last 90 days) ───────────────────────────────
-- Best as a Line chart — Metabase auto-detects date axis.
SELECT date_trunc('day', created_at)::date AS day,
       COUNT(*)                            AS signups
FROM clients
WHERE created_at > NOW() - INTERVAL '90 days'
GROUP BY 1
ORDER BY 1;


-- ─── Plan distribution ────────────────────────────────────────────────
-- Best as a Pie / Donut chart.
SELECT plan, COUNT(*) AS clients
FROM clients
WHERE is_active = TRUE
GROUP BY plan
ORDER BY clients DESC;


-- ─── Onboarding funnel ────────────────────────────────────────────────
-- One row, four counts. Visualize as a Funnel chart in Metabase
-- (column 1 = step name, column 2 = count) — to use Funnel viz, you
-- may want to UNPIVOT into rows. The single-row version below is
-- best as a "Combo" of four Scalar cards on a Dashboard.
SELECT
  COUNT(*) FILTER (WHERE c.is_active)                                                                       AS signed_up,
  COUNT(*) FILTER (WHERE wc.id IS NOT NULL)                                                                 AS connected_whatsapp,
  COUNT(*) FILTER (WHERE EXISTS (
    SELECT 1 FROM analysis_jobs j WHERE j.client_id = c.id AND j.status = 'completed'
  ))                                                                                                        AS got_first_report,
  COUNT(*) FILTER (WHERE c.plan <> 'free')                                                                  AS on_paid_plan
FROM clients c
LEFT JOIN whatsapp_connections wc ON wc.client_id = c.id
WHERE c.is_active;


-- ─── Funnel — row-per-step variant (works with Funnel viz) ────────────
SELECT 'Signed up'                  AS step, 1 AS step_order, COUNT(*) FILTER (WHERE c.is_active) AS clients FROM clients c
UNION ALL
SELECT 'Connected WhatsApp'         AS step, 2 AS step_order, COUNT(*) FROM clients c JOIN whatsapp_connections wc ON wc.client_id = c.id WHERE c.is_active
UNION ALL
SELECT 'Generated first report'     AS step, 3 AS step_order, COUNT(DISTINCT c.id) FROM clients c JOIN analysis_jobs j ON j.client_id = c.id WHERE c.is_active AND j.status = 'completed'
UNION ALL
SELECT 'On a paid plan'             AS step, 4 AS step_order, COUNT(*) FROM clients c WHERE c.is_active AND c.plan <> 'free'
ORDER BY step_order;
