import asyncio
import logging
from functools import lru_cache

import jwt
from jwt import PyJWKClient, exceptions as jwt_exceptions

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    if not settings.clerk_jwks_url:
        raise RuntimeError("CLERK_JWKS_URL is not configured.")
    # cache_keys=True keeps fetched keys in memory; lifespan=3600 re-fetches after 1 h
    return PyJWKClient(settings.clerk_jwks_url, cache_keys=True, lifespan=3600)


def _verify_sync(token: str) -> dict:
    if not settings.clerk_issuer:
        raise RuntimeError("CLERK_ISSUER is not configured.")
    client = _jwks_client()

    # Decode header + claims without verification first so we can log useful diagnostics
    try:
        unverified = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
        logger.debug(
            "Token claims (unverified) — iss=%r exp=%r sub=%r",
            unverified.get("iss"),
            unverified.get("exp"),
            unverified.get("sub"),
        )
        if unverified.get("iss") != settings.clerk_issuer:
            logger.warning(
                "Issuer mismatch: token iss=%r but CLERK_ISSUER=%r",
                unverified.get("iss"),
                settings.clerk_issuer,
            )
    except Exception:
        pass  # if even unverified decode fails the token is malformed

    signing_key = client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=settings.clerk_issuer,
        # Clerk does not include aud by default; disable audience check unless you
        # configure an explicit audience in your Clerk JWT template.
        options={"verify_aud": False},
    )


async def verify_token(token: str) -> dict:
    """Verify a Clerk-issued JWT and return its payload. Runs sync work off the event loop."""
    return await asyncio.to_thread(_verify_sync, token)


async def warm_jwks_cache() -> None:
    """Pre-fetch Clerk's public keys at startup so the first request is not blocked."""
    def _fetch() -> None:
        client = _jwks_client()
        client.fetch_data()

    await asyncio.to_thread(_fetch)
    logger.info("Clerk JWKS cache warmed from %s", settings.clerk_jwks_url)
