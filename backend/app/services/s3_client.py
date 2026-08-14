"""Shared factory for boto3 S3 clients.

Both the Apple Health XML upload flow and raw payload storage talk to S3 (or an
S3-compatible server such as MinIO). Centralising client creation here keeps their
endpoint / addressing / signature configuration identical, so anything that works
against AWS S3 works against MinIO and vice versa.
"""

from logging import getLogger
from typing import Any

logger = getLogger(__name__)


def create_s3_client(endpoint_url: str | None = None) -> Any:
    """Create a boto3 S3 client from the app's AWS settings.

    When ``endpoint_url`` is provided (e.g. a MinIO server), the client is configured
    with path-style addressing and SigV4 signing so presigned URLs and multipart
    uploads behave identically to AWS S3.

    Explicit credentials are used when configured; otherwise boto3 falls back to its
    default credential chain (env vars, instance role, ...). Returns ``None`` if the
    client cannot be created.
    """
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import NoCredentialsError

        from app.config import settings

        kwargs: dict[str, Any] = {"region_name": settings.aws_region}

        if settings.aws_access_key_id and settings.aws_secret_access_key:
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key.get_secret_value()

        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
            # MinIO and most self-hosted S3 servers only support path-style addressing.
            kwargs["config"] = Config(signature_version="s3v4", s3={"addressing_style": "path"})

        return boto3.client("s3", **kwargs)
    except (NoCredentialsError, AttributeError) as e:
        logger.warning("Cannot create S3 client: %s", e)
        return None
