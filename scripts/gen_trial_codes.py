"""
Generate trial codes that can be redeemed at POST /api/v1/billing/redeem-trial.

Usage:
    python scripts/gen_trial_codes.py [count] [--plan basic] [--days 30] [--note "Lanzamiento"]

Examples:
    python scripts/gen_trial_codes.py 10
    python scripts/gen_trial_codes.py 5 --plan basic --days 30 --note "Beta testers"
    python scripts/gen_trial_codes.py --code DEEPLOOK-VIP --days 60   # mint a specific code
"""
import argparse
import asyncio
import os
import secrets
import string
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ALPHABET = string.ascii_uppercase + string.digits
# Strip ambiguous characters so codes are easy to read aloud / type by hand
AMBIGUOUS = set("O01IL")
SAFE_ALPHABET = "".join(c for c in ALPHABET if c not in AMBIGUOUS)


def random_code(length: int = 10) -> str:
    return "".join(secrets.choice(SAFE_ALPHABET) for _ in range(length))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mint trial codes for DeepLook.")
    p.add_argument("count", nargs="?", type=int, default=1, help="How many codes to mint (default 1).")
    p.add_argument("--plan", default="basic", choices=["basic", "plus", "enterprise"], help="Plan granted by the code.")
    p.add_argument("--days", type=int, default=30, help="Trial duration in days, after redemption (default 30).")
    p.add_argument(
        "--valid-for-days",
        dest="valid_for_days",
        type=int,
        default=None,
        help="How many days the code itself can be redeemed for (default: same as --days). "
             "Pass 0 to make the code never expire.",
    )
    p.add_argument("--max-claims", dest="max_claims", type=int, default=1,
                   help="How many users can claim this code (default 1).")
    p.add_argument("--note", default=None, help="Internal note (e.g. campaign name).")
    p.add_argument("--code", default=None, help="Mint exactly this code instead of random ones (count is ignored).")
    p.add_argument("--length", type=int, default=10, help="Length of random codes (default 10).")
    return p.parse_args()


def _normalize_async_url(url: str) -> str:
    # asyncpg.connect() accepts postgresql://; SQLAlchemy uses postgresql+asyncpg://
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def main() -> int:
    args = parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        return 1

    if args.code:
        codes = [args.code.strip().upper()]
    else:
        codes = [random_code(args.length) for _ in range(args.count)]

    # Default the redemption window to match the trial duration.
    # `--valid-for-days 0` opts out and the code never expires.
    valid_for = args.valid_for_days if args.valid_for_days is not None else args.days
    expires_clause = "NOW() + ($5 || ' days')::interval" if valid_for > 0 else "NULL"

    # statement_cache_size=0 keeps us compatible with Supabase's transaction-mode pooler,
    # which doesn't support prepared statements across pooled connections.
    conn = await asyncpg.connect(_normalize_async_url(db_url), statement_cache_size=0)
    try:
        rows = []
        for code in codes:
            params = [code, args.plan, args.days, args.note]
            if valid_for > 0:
                params.append(str(valid_for))
            row = await conn.fetchrow(
                f"""
                INSERT INTO trial_codes (id, code, plan, duration_days, max_claims, claims_count, is_active, note, expires_at)
                VALUES (gen_random_uuid(), $1, $2, $3, $6, 0, true, $4, {expires_clause})
                ON CONFLICT (code) DO NOTHING
                RETURNING code, plan, duration_days, max_claims, note, expires_at
                """,
                *params, args.max_claims,
            )
            if row:
                rows.append(row)
            else:
                print(f"  (skip) {code} already exists", file=sys.stderr)

        if not rows:
            print("No codes minted.")
            return 0

        print(f"Minted {len(rows)} code(s):")
        for r in rows:
            note = f"  [{r['note']}]" if r["note"] else ""
            window = f"valid until {r['expires_at'].strftime('%Y-%m-%d')}" if r["expires_at"] else "no expiry"
            print(f"  {r['code']}  →  plan={r['plan']}  duration={r['duration_days']}d  max_claims={r['max_claims']}  ({window}){note}")
    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
