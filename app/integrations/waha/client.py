import asyncio
import base64
import logging
from typing import Optional

import httpx

_MESSAGES_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

from app.integrations.waha.exceptions import WahaAuthError, WahaError, WahaSessionNotFoundError
from app.integrations.waha.models import WahaChatOverview, WahaMessage, WahaSessionInfo, WahaSessionStatus

logger = logging.getLogger(__name__)


class WahaClient:
    def __init__(self, base_url: str, api_key: str):
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-Api-Key": api_key},
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _check(self, response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise WahaAuthError("Invalid or missing WAHA API key.", response.status_code)
        if response.status_code == 404:
            raise WahaSessionNotFoundError("Session not found in WAHA.", response.status_code)
        if response.status_code >= 400:
            raise WahaError(f"WAHA API error {response.status_code}: {response.text}", response.status_code)

    def _json(self, response: httpx.Response) -> dict:
        """Parse JSON from response, raising WahaError on empty or invalid body."""
        try:
            return response.json()
        except Exception as exc:
            raise WahaError(
                f"WAHA returned non-JSON response (status {response.status_code}): {response.text!r:.200}",
                response.status_code,
            ) from exc

    async def create_session(self, name: str, client_id: str) -> WahaSessionInfo:
        """
        Create and immediately start a WAHA NOWEB session.
        markOnline=False is non-negotiable — prevents online presence emission
        and the associated ban risk.
        """
        body = {
            "name": name,
            "start": True,
            "config": {
                "noweb": {
                    "markOnline": False,
                    "store": {
                        "enabled": True,
                        "fullSync": True,
                    },
                },
                "client": {
                    "deviceName": "DeepLook",
                    "browserName": "Chrome",
                },
                "metadata": {
                    "client_id": str(client_id),
                },
            },
        }
        r = await self._client.post("/api/sessions", json=body)
        self._check(r)
        # WAHA Plus may return 202 with empty body when start=True triggers async startup
        if not r.content.strip():
            return await self.get_session(name)
        return WahaSessionInfo.model_validate(self._json(r))

    async def get_session(self, name: str) -> WahaSessionInfo:
        r = await self._client.get(f"/api/sessions/{name}")
        self._check(r)
        return WahaSessionInfo.model_validate(self._json(r))

    async def start_session(self, name: str) -> WahaSessionInfo:
        r = await self._client.post(f"/api/sessions/{name}/start")
        self._check(r)
        return WahaSessionInfo.model_validate(self._json(r))

    async def restart_session(self, name: str) -> WahaSessionInfo:
        """
        Restart a session — clears FAILED state and triggers fresh QR generation.
        Equivalent to stop+start; credentials on disk are preserved so a previously
        paired account resumes without re-scanning. The primary use is recovering
        sessions that hit "QR refs attempts ended" (user didn't scan in time).
        """
        r = await self._client.post(f"/api/sessions/{name}/restart")
        self._check(r)
        if not r.content.strip():
            return await self.get_session(name)
        return WahaSessionInfo.model_validate(self._json(r))

    async def get_qr_base64(self, name: str) -> str:
        """Return QR as a data URI string (data:image/png;base64,...)."""
        r = await self._client.get(f"/api/{name}/auth/qr", params={"format": "image"})
        self._check(r)
        return "data:image/png;base64," + base64.b64encode(r.content).decode()

    async def check_is_business_account(self, name: str, own_jid: str) -> bool | None:
        """
        Returns True if the connected WhatsApp account is a Business account,
        False if it's definitively a personal account, or None if every probe
        failed and the result is genuinely undetermined.

        Callers with WAHA_REQUIRE_BUSINESS_ACCOUNT=true should treat None as
        a block (fail-safe): if we can't prove it's Business, we don't allow it.

        Strategy (all probes are read-only, zero ban risk):
          1. /api/{session}/contacts/{jid}              → isBusiness / isEnterprise flags
          2. /api/{session}/contacts/{jid}/about        → businessProfile presence
          3. /api/{session}/contacts/{jid}/check-exists → type/isBusiness on newer WAHA
          4. /api/{session}/contacts/check-exists?phone → same via query param variant
        """
        probes = [
            f"/api/{name}/contacts/{own_jid}",
            f"/api/{name}/contacts/{own_jid}/about",
            f"/api/{name}/contacts/{own_jid}/business-profile",
        ]

        # Normalise JID → bare phone for the query-param variant
        phone = own_jid.split("@")[0]
        probes.append(f"/api/{name}/contacts/check-exists?phone={phone}")

        for url in probes:
            try:
                r = await self._client.get(url)
                logger.debug(
                    "check_is_business [session=%s jid=%s] %s → %s",
                    name, own_jid, url, r.status_code,
                )
                if r.status_code not in (200, 201):
                    continue
                data = r.json()
                if not isinstance(data, dict):
                    continue

                logger.debug("check_is_business response: %s", data)

                # Any of these fields being truthy = Business confirmed
                if (data.get("isBusiness")
                        or data.get("isEnterprise")
                        or data.get("businessProfile")
                        or data.get("type") == "business"):
                    return True

                # Explicit False only when the key is present and falsy
                # (absence means the endpoint just doesn't carry that info)
                if "isBusiness" in data:
                    return False

            except Exception as exc:
                logger.debug("check_is_business probe %s failed: %s", url, exc)

        logger.warning(
            "check_is_business: could not determine account type for session=%s jid=%s "
            "(all probes returned no isBusiness flag). Returning None — caller decides.",
            name, own_jid,
        )
        return None

    async def list_chats(self, name: str, limit: int = 1000, offset: int = 0) -> list[WahaChatOverview]:
        r = await self._client.get(
            f"/api/{name}/chats",
            params={"limit": limit, "offset": offset, "sortBy": "conversationTimestamp", "sortOrder": "desc", "merge": True},
        )
        self._check(r)
        return [WahaChatOverview.model_validate(c) for c in self._json(r)]

    async def get_chat_messages(
        self,
        name: str,
        chat_id: str,
        limit: int = 1000,
        since_ts: Optional[int] = None,
        offset: int = 0,
    ) -> list[WahaMessage]:
        params: dict = {"limit": limit, "offset": offset, "downloadMedia": False, "merge": True}
        if since_ts is not None:
            params["filter.timestamp.gte"] = since_ts
        r = await self._client.get(
            f"/api/{name}/chats/{chat_id}/messages",
            params=params,
            timeout=_MESSAGES_TIMEOUT,
        )
        self._check(r)
        return [WahaMessage.model_validate(m) for m in self._json(r)]

    async def stop_session(self, name: str, logout: bool = False) -> None:
        """
        Stop the session. With logout=False (default) credentials are preserved
        on disk so the next start() resumes without a new QR scan.
        Only pass logout=True when the user explicitly unlinks their account.
        """
        r = await self._client.post(f"/api/sessions/{name}/stop", json={"logout": logout})
        if r.status_code not in (200, 201, 404):
            self._check(r)

    async def logout_session(self, name: str) -> None:
        """Wipe stored credentials. Use only on user-initiated 'Desvincular'."""
        r = await self._client.post(f"/api/sessions/{name}/logout")
        if r.status_code not in (200, 201, 404):
            self._check(r)

    async def delete_session(self, name: str) -> None:
        """Delete the session record from WAHA entirely."""
        r = await self._client.delete(f"/api/sessions/{name}")
        if r.status_code not in (200, 201, 404):
            self._check(r)

    async def get_or_create_session(self, name: str, client_id: str) -> WahaSessionInfo:
        """
        Idempotent: return the existing session if it's already there,
        otherwise create it. Handles WAHA Core's 422 "already exists" gracefully.
        """
        try:
            return await self.get_session(name)
        except WahaSessionNotFoundError:
            return await self.create_session(name, client_id)

    async def wait_for_working(
        self, name: str, timeout_seconds: int = 60, poll_interval: float = 2.0
    ) -> WahaSessionStatus:
        """Poll until status reaches WORKING, SCAN_QR_CODE, or FAILED — or timeout.
        401/403 from WAHA are treated as transient during WEBJS engine startup and retried."""
        elapsed = 0.0
        while elapsed < timeout_seconds:
            try:
                info = await self.get_session(name)
                if info.status in (WahaSessionStatus.WORKING, WahaSessionStatus.SCAN_QR_CODE, WahaSessionStatus.FAILED):
                    return info.status
            except WahaAuthError:
                logger.debug("wait_for_working: transient 401 from WAHA for session %s — retrying", name)
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        info = await self.get_session(name)
        return info.status


_instance: WahaClient | None = None


def get_waha_client() -> WahaClient:
    """Lazy singleton — call aclose() at app shutdown."""
    global _instance
    if _instance is None:
        from app.config import settings
        _instance = WahaClient(base_url=settings.waha_base_url, api_key=settings.waha_api_key)
    return _instance
