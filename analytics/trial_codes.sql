-- =====================================================================
-- Trial code metrics
-- Are the codes actually driving conversions?
-- =====================================================================


-- ─── Codes minted vs. redeemed ────────────────────────────────────────
SELECT
  COUNT(*)                                                  AS minted,
  COUNT(*) FILTER (WHERE redeemed_at IS NOT NULL)           AS redeemed,
  COUNT(*) FILTER (
    WHERE redeemed_at IS NULL
      AND (expires_at IS NULL OR expires_at > NOW())
      AND is_active
  )                                                         AS still_redeemable,
  COUNT(*) FILTER (
    WHERE redeemed_at IS NULL
      AND expires_at IS NOT NULL
      AND expires_at <= NOW()
  )                                                         AS expired_unused
FROM trial_codes;


-- ─── Redemption rate per campaign (uses the `note` field) ─────────────
-- Mint codes with `--note "Lanzamiento mayo"` and you can compare
-- conversion across campaigns here.
SELECT
  COALESCE(note, '(sin nota)')                                              AS campaign,
  COUNT(*)                                                                  AS minted,
  COUNT(*) FILTER (WHERE redeemed_at IS NOT NULL)                           AS redeemed,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE redeemed_at IS NOT NULL)::numeric
          / NULLIF(COUNT(*), 0),
    1
  )                                                                         AS redemption_pct
FROM trial_codes
GROUP BY note
ORDER BY minted DESC;


-- ─── Trial → Paid conversion ──────────────────────────────────────────
-- Did clients who used a trial code later upgrade to a paid plan?
SELECT
  COUNT(*)                                                                  AS trials_redeemed,
  COUNT(*) FILTER (
    WHERE EXISTS (
      SELECT 1 FROM payment_sessions p
      WHERE p.client_id = c.id AND p.status = 'approved'
    )
  )                                                                         AS later_paid,
  ROUND(
    100.0 * COUNT(*) FILTER (
      WHERE EXISTS (
        SELECT 1 FROM payment_sessions p
        WHERE p.client_id = c.id AND p.status = 'approved'
      )
    )::numeric / NULLIF(COUNT(*), 0),
    1
  )                                                                         AS trial_to_paid_pct
FROM clients c
WHERE c.trial_redeemed_at IS NOT NULL;


-- ─── Codes redeemed in the last 30 days ───────────────────────────────
-- Detail view — who redeemed what, when.
SELECT tc.code,
       tc.plan,
       tc.duration_days,
       tc.note,
       tc.redeemed_at,
       c.email     AS redeemer_email,
       c.business_name
FROM trial_codes tc
LEFT JOIN clients c ON c.id = tc.redeemed_by_client_id
WHERE tc.redeemed_at > NOW() - INTERVAL '30 days'
ORDER BY tc.redeemed_at DESC;
