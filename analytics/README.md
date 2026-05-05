# Analytics queries

Ready-to-paste SQL for the Metabase dashboard described in the main README.

## How to use

1. Start Metabase: `docker compose up -d metabase` and open `http://localhost:3001`.
2. In Metabase: **+ New → SQL query**.
3. Open one of the `.sql` files in this folder, copy the query block (everything below a heading comment up to the next `-- ───` divider), and paste it.
4. Run it, save it as a Question, and pin it to a Dashboard.

## Files

| File                  | What's inside                                                                |
| --------------------- | ---------------------------------------------------------------------------- |
| `growth.sql`          | Active clients, signups/day, plan distribution, onboarding funnel            |
| `revenue.sql`         | Lifetime revenue, monthly revenue, MRR, conversion %, revenue per plan, failed payments |
| `product_usage.sql`   | Reports generated, AI cost vs revenue, WhatsApp connection health, stale connections |
| `trial_codes.sql`     | Codes minted/redeemed, per-campaign redemption rate, trial → paid conversion |
| `churn.sql`           | Plans expired without renewal, winback list, cohort retention                |

## Conventions

- Each query has a header comment explaining what it shows and which Metabase visualization fits best.
- Plan prices are hardcoded (160k / 250k / 400k COP) — if you change pricing in `app/billing/router.py`, update `revenue.sql` MRR query to match.
- USD-COP rate in `product_usage.sql` is approximated at 4000; tweak if rates drift.
- All queries are read-only — safe to run against production.
