from datetime import UTC, datetime
from logging import getLogger

import boto3
from botocore.exceptions import NoCredentialsError

from app.config import settings
from app.services.s3_client import create_s3_client
from app.utils.structured_logging import log_structured

AWS_BUCKET_NAME = settings.aws_bucket_name
AWS_REGION = settings.aws_region
logger = getLogger(__name__)


def get_s3_client():  # noqa: ANN201
    """Return an S3 client for the Apple XML upload flow, or None when unconfigured.

    Credentials are required (MinIO uses them too), which keeps the "storage not
    configured -> 503" behaviour that callers rely on. When ``AWS_ENDPOINT_URL``
    is set the client points at that S3-compatible server (e.g. MinIO).
    """
    if not (settings.aws_access_key_id and settings.aws_secret_access_key):
        log_structured(logger, "warning", "AWS credentials not configured")
        return None
    return create_s3_client(settings.aws_endpoint_url)


def get_sns_client():  # noqa: ANN201
    try:
        return boto3.client(
            "sns",
            region_name=AWS_REGION,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key.get_secret_value(),  # ty:ignore[unresolved-attribute]
        )
    except (NoCredentialsError, AttributeError):
        log_structured(logger, "warning", "AWS credentials not configured")
        return None


def build_object_key(user_id: str, filename: str | None = None) -> str:
    """Build the S3 object key for a user's uploaded Apple Health XML file.

    Keys are always namespaced under ``<user_id>/raw/`` so uploads can be attributed
    back to a user and access can be scoped per user.
    """
    if filename:
        clean_filename = "".join(c for c in filename if c.isalnum() or c in ".-_")
        if clean_filename:
            return f"{user_id}/raw/{clean_filename}"
    # Compact, URL-safe UTC timestamp (no spaces/colons) so the key needs no encoding.
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{user_id}/raw/{timestamp}.xml"
