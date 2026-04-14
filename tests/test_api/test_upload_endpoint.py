"""Tests for the POST /api/v1/upload endpoint."""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_upload_requires_files(client):
    response = await client.post(
        "/api/v1/upload",
        data={"business_name": "Test Biz", "business_identifiers": "Negocio"},
    )
    # Should fail with 422 (no files) or 400
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_upload_rejects_non_txt(client):
    response = await client.post(
        "/api/v1/upload",
        data={"business_name": "Test Biz", "business_identifiers": "Negocio"},
        files={"files": ("chat.pdf", b"%PDF-fake-content", "application/pdf")},
    )
    assert response.status_code in (422, 500)


@pytest.mark.asyncio
async def test_health_check_before_upload(client):
    """Sanity: health endpoint must be up before testing upload."""
    response = await client.get("/health")
    assert response.status_code == 200
