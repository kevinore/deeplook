"""
Aggregate ParseQualityReports from multiple files into a single batch report.
"""
from app.models.schemas import ParseQualityReport


def aggregate_quality_reports(reports: list[ParseQualityReport]) -> ParseQualityReport:
    """Merge individual file quality reports into one batch-level report."""
    if not reports:
        return ParseQualityReport()

    if len(reports) == 1:
        return reports[0]

    total_lines = sum(r.total_lines for r in reports)
    parsed_messages = sum(r.parsed_messages for r in reports)
    system_filtered = sum(r.system_messages_filtered for r in reports)
    continuation_merged = sum(r.continuation_lines_merged for r in reports)
    empty_skipped = sum(r.empty_lines_skipped for r in reports)

    all_senders: list[str] = []
    all_warnings: list[str] = []
    all_type_counts: dict[str, int] = {}
    all_direction_counts: dict[str, int] = {}
    date_starts = [r.date_range_start for r in reports if r.date_range_start]
    date_ends = [r.date_range_end for r in reports if r.date_range_end]

    for r in reports:
        all_senders.extend(r.unique_senders)
        all_warnings.extend(r.warnings)
        for k, v in r.message_type_counts.items():
            all_type_counts[k] = all_type_counts.get(k, 0) + v
        for k, v in r.direction_counts.items():
            all_direction_counts[k] = all_direction_counts.get(k, 0) + v

    avg_confidence = sum(r.confidence_score for r in reports) / len(reports)

    return ParseQualityReport(
        total_lines=total_lines,
        parsed_messages=parsed_messages,
        system_messages_filtered=system_filtered,
        continuation_lines_merged=continuation_merged,
        empty_lines_skipped=empty_skipped,
        unique_senders=list(dict.fromkeys(all_senders)),
        date_range_start=min(date_starts) if date_starts else None,
        date_range_end=max(date_ends) if date_ends else None,
        message_type_counts=all_type_counts,
        direction_counts=all_direction_counts,
        confidence_score=round(avg_confidence, 2),
        warnings=list(dict.fromkeys(all_warnings)),
    )
