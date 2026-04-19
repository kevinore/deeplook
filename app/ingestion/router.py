import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.pipeline import store_batch
from app.dependencies import get_db
from app.exceptions import ParseError, ValidationError
from app.ingestion.parsers.txt_parser import TxtParser
from app.ingestion.quality import aggregate_quality_reports
from app.ingestion.validators import extract_txt_files, validate_batch, validate_upload_file, validate_zip_file
from app.models.schemas import ParseQualityReport, UploadResponse
from app.repositories.analysis_repo import AnalysisJobRepository
from app.workers.analysis_worker import run_analysis_job

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Ingestion"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=202,
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file", "business_name", "client_id"],
                        "properties": {
                            "file": {
                                "type": "string",
                                "format": "binary",
                                "description": "ZIP archive containing WhatsApp .txt export files",
                            },
                            "business_name": {"type": "string"},
                            "business_identifiers": {"type": "string", "default": ""},
                            "client_id": {"type": "string", "format": "uuid", "description": "UUID from the clients table"},
                        },
                    }
                }
            },
            "required": True,
        }
    },
)
async def upload_files(
    file: UploadFile,
    business_name: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    business_identifiers: Annotated[str, Form()] = "",
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """
    Upload a ZIP archive containing WhatsApp .txt export files for analysis.

    - file: ZIP file with one or more .txt chat exports
    - business_name: display name of the business
    - business_identifiers: comma-separated names/phones the business uses in chats
    - client_id: client identifier (from clients table)
    """
    identifiers = [i.strip() for i in business_identifiers.split(",") if i.strip()]

    try:
        uuid.UUID(client_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"client_id '{client_id}' is not a valid UUID. Pass the UUID from the clients table.",
        )

    zip_content = await file.read()
    zip_filename = file.filename or "upload.zip"

    # Validate and extract
    try:
        validate_zip_file(zip_filename, zip_content)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.reason)

    try:
        file_contents = extract_txt_files(zip_content)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.reason)

    if not file_contents:
        raise HTTPException(status_code=422, detail="ZIP contains no .txt files.")

    total_bytes = sum(len(c) for _, c in file_contents)

    # Validate batch-level constraints
    try:
        validate_batch(len(file_contents), total_bytes)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.reason)

    parser = TxtParser()
    quality_reports: list[ParseQualityReport] = []
    parse_errors: list[dict] = []
    all_batches = []

    for filename, content in file_contents:
        try:
            validate_upload_file(filename, content)
            batch = await parser.parse(
                content,
                client_id=client_id,
                business_identifiers=identifiers,
                filename=filename,
            )
            all_batches.append(batch)

            # Extract quality report from metadata if present
            meta = batch.raw_metadata.get("quality_report")
            if meta:
                quality_reports.append(ParseQualityReport(**meta))

        except (ParseError, ValidationError) as exc:
            parse_errors.append({"file": filename, "error": str(exc)})
        except Exception as exc:
            logger.exception("Unexpected error parsing %s", filename)
            parse_errors.append({"file": filename, "error": f"Unexpected error: {exc}"})

    if not all_batches:
        raise HTTPException(
            status_code=422,
            detail={"message": "All files failed to parse", "errors": parse_errors},
        )

    # Store to DB and create analysis job
    all_conv_ids: list[str] = []
    for batch in all_batches:
        pairs = await store_batch(batch, db)
        all_conv_ids.extend(conv_id for _, conv_id in pairs)

    total_conversations = len(all_conv_ids)

    # Create analysis job
    job_repo = AnalysisJobRepository(db)
    job = await job_repo.create(
        client_id=client_id,
        status="pending",
        job_type="full_analysis",
        total_conversations=total_conversations,
    )
    await db.commit()

    # Queue background task
    background_tasks.add_task(run_analysis_job, str(job.id), all_conv_ids)

    # Aggregate quality reports
    aggregated_quality = aggregate_quality_reports(quality_reports) if quality_reports else ParseQualityReport()

    return UploadResponse(
        job_id=job.id,
        files_received=len(file_contents),
        conversations_parsed=total_conversations,
        parse_errors=parse_errors,
        parse_quality=aggregated_quality,
        status="processing",
    )


@router.get("/webhook", tags=["Ingestion"])
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
) -> int | str:
    """Meta webhook verification (Phase 2)."""
    from app.config import settings
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        return int(hub_challenge or 0)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/webhook", status_code=200, tags=["Ingestion"])
async def receive_webhook(payload: dict, db: AsyncSession = Depends(get_db)) -> dict:
    """Meta Cloud API webhook receiver (Phase 2 — stub)."""
    return {"status": "received"}
