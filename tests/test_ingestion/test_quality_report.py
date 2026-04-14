"""Tests for ParseQualityReport generation."""
from pathlib import Path

import pytest

from app.ingestion.parsers.txt_parser import TxtParser
from app.ingestion.quality import aggregate_quality_reports
from app.models.schemas import ParseQualityReport

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_quality_report_generated():
    content = (FIXTURES / "sample_chat_spanish.txt").read_bytes()
    parser = TxtParser()
    batch = await parser.parse(
        content,
        client_id="test",
        business_identifiers=["Wellness By Diego Omar"],
        filename="sample_chat_spanish.txt",
    )
    meta = batch.raw_metadata.get("quality_report")
    assert meta is not None
    report = ParseQualityReport(**meta)
    assert report.parsed_messages > 0
    assert report.system_messages_filtered > 0  # encryption notice
    assert report.confidence_score > 0.0
    assert report.date_range_start is not None
    assert report.date_range_end is not None


@pytest.mark.asyncio
async def test_quality_report_detects_business():
    content = (FIXTURES / "sample_chat_spanish.txt").read_bytes()
    parser = TxtParser()
    batch = await parser.parse(
        content,
        client_id="test",
        business_identifiers=["Wellness By Diego Omar"],
    )
    report = ParseQualityReport(**batch.raw_metadata["quality_report"])
    assert report.detected_business is not None
    assert len(report.detected_customers) > 0


@pytest.mark.asyncio
async def test_quality_report_auto_detect_warning():
    """No business_identifiers → confidence reduced + warning added."""
    content = (FIXTURES / "sample_chat_spanish.txt").read_bytes()
    parser = TxtParser()
    batch = await parser.parse(content, client_id="test", business_identifiers=[])
    report = ParseQualityReport(**batch.raw_metadata["quality_report"])
    assert report.confidence_score < 1.0
    assert any("auto-detected" in w.lower() or "Auto-detected" in w for w in report.warnings)


def test_aggregate_quality_reports_single():
    r = ParseQualityReport(parsed_messages=10, confidence_score=0.9)
    result = aggregate_quality_reports([r])
    assert result.parsed_messages == 10
    assert result.confidence_score == 0.9


def test_aggregate_quality_reports_multiple():
    r1 = ParseQualityReport(parsed_messages=10, total_lines=50, confidence_score=1.0)
    r2 = ParseQualityReport(parsed_messages=8, total_lines=40, confidence_score=0.8)
    result = aggregate_quality_reports([r1, r2])
    assert result.parsed_messages == 18
    assert result.total_lines == 90
    assert result.confidence_score == pytest.approx(0.9)


def test_aggregate_empty():
    result = aggregate_quality_reports([])
    assert result.parsed_messages == 0
