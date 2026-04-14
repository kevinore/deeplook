"""Tests for report-related endpoints."""
import pytest


@pytest.mark.asyncio
async def test_report_status_not_found(client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/v1/reports/{fake_id}/status")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_report_download_not_found(client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/v1/reports/{fake_id}/download")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_job_status_not_found(client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/v1/jobs/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dashboard_stubs_return_200(client):
    """Dashboard Phase 2 stubs should return 200 without errors."""
    for path in [
        "/api/v1/dashboard/overview",
        "/api/v1/dashboard/sentiment",
        "/api/v1/dashboard/response-times",
        "/api/v1/dashboard/topics",
        "/api/v1/dashboard/conversations",
        "/api/v1/dashboard/alerts",
    ]:
        response = await client.get(path)
        assert response.status_code == 200, f"Failed for {path}"
