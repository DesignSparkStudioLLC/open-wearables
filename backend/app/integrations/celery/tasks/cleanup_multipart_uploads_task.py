"""Periodic cleanup for abandoned Apple XML multipart uploads."""

from datetime import UTC, datetime, timedelta
from logging import getLogger

from botocore.exceptions import ClientError
from celery import shared_task

from app.config import settings
from app.services.apple.apple_xml.aws_service import get_s3_client
from app.utils.structured_logging import log_structured

logger = getLogger(__name__)


def _is_apple_xml_key(key: str) -> bool:
    """Return whether a key belongs to the ``<user_id>/raw/`` Apple XML namespace."""
    parts = key.split("/", maxsplit=2)
    return len(parts) == 3 and bool(parts[0]) and parts[1] == "raw" and bool(parts[2])


def _is_stale(initiated: datetime, cutoff: datetime) -> bool:
    if initiated.tzinfo is None:
        initiated = initiated.replace(tzinfo=UTC)
    return initiated <= cutoff


@shared_task
def cleanup_stale_apple_xml_multipart_uploads() -> dict[str, int | str]:
    """Abort incomplete Apple XML multipart uploads older than the configured limit."""
    client = get_s3_client()
    bucket = settings.aws_bucket_name
    if not client or not bucket:
        log_structured(
            logger,
            "warning",
            "Skipped Apple XML multipart cleanup because S3 is not configured",
            provider="apple_xml",
            action="multipart_cleanup_skipped",
        )
        return {"status": "skipped", "scanned": 0, "aborted": 0, "failed": 0}

    cutoff = datetime.now(UTC) - timedelta(hours=settings.apple_xml_multipart_max_age_hours)
    scanned = 0
    aborted = 0
    failed = 0

    paginator = client.get_paginator("list_multipart_uploads")
    for page in paginator.paginate(Bucket=bucket):
        for upload in page.get("Uploads", []):
            key = str(upload.get("Key", ""))
            upload_id = str(upload.get("UploadId", ""))
            initiated = upload.get("Initiated")
            if not _is_apple_xml_key(key) or not upload_id or not isinstance(initiated, datetime):
                continue

            scanned += 1
            if not _is_stale(initiated, cutoff):
                continue

            try:
                client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
                aborted += 1
            except ClientError as error:
                error_code = str(error.response.get("Error", {}).get("Code", "UnknownError"))
                if error_code == "NoSuchUpload":
                    # Another caller or a bucket lifecycle rule already cleaned it up.
                    continue
                failed += 1
                log_structured(
                    logger,
                    "error",
                    "Failed to clean up stale Apple XML multipart upload",
                    provider="apple_xml",
                    action="multipart_cleanup_failed",
                    bucket=bucket,
                    key=key,
                    upload_id=upload_id,
                    error_code=error_code,
                )

    log_structured(
        logger,
        "info",
        "Finished Apple XML multipart cleanup",
        provider="apple_xml",
        action="multipart_cleanup_completed",
        bucket=bucket,
        scanned=scanned,
        aborted=aborted,
        failed=failed,
    )
    return {"status": "completed", "scanned": scanned, "aborted": aborted, "failed": failed}
