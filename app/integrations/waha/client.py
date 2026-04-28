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
                        "fullSync": False,
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
        return WahaSessionInfo.model_validate(r.json())

    async def get_session(self, name: str) -> WahaSessionInfo:
        r = await self._client.get(f"/api/sessions/{name}")
        self._check(r)
        return WahaSessionInfo.model_validate(r.json())

    async def start_session(self, name: str) -> WahaSessionInfo:
        r = await self._client.post(f"/api/sessions/{name}/start")
        self._check(r)
        return WahaSessionInfo.model_validate(r.json())

    async def get_qr_base64(self, name: str) -> str:
        """Return QR as a data URI string (data:image/png;base64,...)."""
        r = await self._client.get(f"/api/{name}/auth/qr", params={"format": "image"})
        self._check(r)
        return "data:image/png;base64," + base64.b64encode(r.content).decode()

    async def list_chats(self, name: str, limit: int = 1000, offset: int = 0) -> list[WahaChatOverview]:
        r = await self._client.get(
            f"/api/{name}/chats",
            params={"limit": limit, "offset": offset, "sortBy": "conversationTimestamp", "sortOrder": "desc", "merge": True},
        )
        self._check(r)
        return [WahaChatOverview.model_validate(c) for c in r.json()]

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
        return [WahaMessage.model_validate(m) for m in r.json()]

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
