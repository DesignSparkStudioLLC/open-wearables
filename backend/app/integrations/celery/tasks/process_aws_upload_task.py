from logging import getLogger
from pathlib import Path
from typing import Any, BinaryIO

from celery import shared_task
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.schemas.providers.apple.apple_xml import CompletedPart
from app.services import event_record_service
from app.services.apple.apple_xml.aws_service import get_s3_client
from app.services.apple.apple_xml.multipart_upload_service import multipart_upload_service
from app.services.apple.apple_xml.xml_service import XMLService
from app.services.apple.healthkit.sleep_service import handle_sleep_data
from app.services.timeseries_service import timeseries_service
from app.services.user_service import user_service
from app.utils.exceptions import ResourceNotFoundError
from app.utils.sentry_helpers import log_and_capture_error

logger = getLogger(__name__)


def _process_aws_upload(bucket_name: str, object_key: str, user_id: str) -> dict[str, str]:
    """Stream an S3 XML object into the importer without using local disk."""
    s3_client = get_s3_client()
    if not s3_client:
        err = RuntimeError("S3 client not configured — cannot process AWS upload")
        log_and_capture_error(
            err,
            logger,
            "S3 client unavailable in process_aws_upload task",
            extra={"bucket_name": bucket_name, "object_key": object_key, "user_id": user_id},
        )
        raise err

    with SessionLocal() as db:
        # Validate that the user exists before opening a potentially multi-gigabyte object.
        try:
            _ = user_service.get(db, user_id, raise_404=True)
        except ResourceNotFoundError as e:
            log_and_capture_error(
                e,
                logger,
                "Skipping import for non-existent user",
                extra={"user_id": user_id},
            )
            return {
                "status": "skipped",
                "reason": str(e),
            }

        response: dict[str, Any] = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        body: BinaryIO = response["Body"]
        try:
            _import_xml_data(db, body, user_id)
        except Exception:
            db.rollback()
            raise
        finally:
            body.close()

        return {
            "bucket": bucket_name,
            "input_key": object_key,
            "user_id": user_id,
            "status": "success",
            "message": "Import completed successfully",
        }


@shared_task
def process_aws_upload(bucket_name: str, object_key: str, user_id: str) -> dict[str, str]:
    """Process an XML file uploaded to S3 and import it into Postgres."""
    return _process_aws_upload(bucket_name, object_key, user_id)


@shared_task
def complete_and_process_aws_upload(
    *,
    bucket_name: str,
    object_key: str,
    upload_id: str,
    parts: list[dict[str, Any]],
    user_id: str,
) -> dict[str, str]:
    """Finalize a client-driven multipart upload and process it in one queued job.

    Publishing this task happens before the multipart upload is completed. If the broker
    is unavailable, the upload therefore remains incomplete and can still be retried or
    aborted instead of becoming an untracked finalized object.
    """
    completed_parts = [CompletedPart.model_validate(part) for part in parts]
    multipart_upload_service.complete_upload(
        user_id=user_id,
        key=object_key,
        upload_id=upload_id,
        parts=completed_parts,
        bucket_name=bucket_name,
    )
    return _process_aws_upload(bucket_name, object_key, user_id)


def _import_xml_data(db: Session, xml_source: str | Path | BinaryIO, user_id: str) -> None:
    """
    Parse XML file and import data to database using XMLExporter.

    Args:
        db: Database session
        xml_source: Path or binary stream containing the XML file
        user_id: User ID to associate with the data
    """
    normalized_source = Path(xml_source) if isinstance(xml_source, str) else xml_source
    xml_service = XMLService(normalized_source, getLogger(__name__))

    for time_series_records, workouts, sync_request in xml_service.parse_xml(user_id):
        for record, detail in workouts:
            created_record = event_record_service.create(db, record)
            detail_for_record = detail.model_copy(update={"record_id": created_record.id})
            event_record_service.create_detail(db, detail_for_record)
        if time_series_records:
            timeseries_service.bulk_create_samples(db, time_series_records)
            db.commit()
        if sync_request and sync_request.data.sleep:
            handle_sleep_data(db, sync_request, user_id)
