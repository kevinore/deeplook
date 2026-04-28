import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.clerk import verify_token

logger = logging.getLogger(__name__)

# auto_error=False so we can return 401 (unauthenticated) instead of FastAPI's
# default 403 (forbidden) when the Authorization header is missing entirely.
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    """Minimal verified identity extracted from a Clerk JWT."""
    user_id: str       # Clerk user ID, e.g. "user_2abc123"
    session_id: str | None = None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """
    FastAPI dependency that enforces Clerk JWT authentication.

    Raises 401 when:
    - Authorization header is absent
    - Token is missing, malformed, expired, or fails signature verification
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = await verify_token(credentials.credentials)
    except Exception as exc:
        # Log the specific error type so operators can diagnose issuer/signature/expiry issues
        logger.warning("Clerk token verification failed [%s]: %s", type(exc).__name__, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        user_id=payload["sub"],
        session_id=payload.get("sid"),
    )


async def assert_client_owner(
    client_id: str,
    user: CurrentUser,
    db: AsyncSession,
):
    """
    Fetch a client and verify it belongs to the authenticated user.
    Always raises 404 — never 403 — to avoid leaking that a resource
    exists but belongs to a different user.
    """
    from app.repositories.client_repo import ClientRepository
    client = await ClientRepository(db).get_by_owner(client_id, user.user_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")
    return client
