from fastapi import APIRouter, HTTPException, UploadFile, status

from app.integrations.celery.tasks.process_aws_upload_task import process_aws_upload
from app.integrations.celery.tasks.process_xml_upload_task import process_xml_upload
from app.schemas.providers.apple.apple_xml import (
    PresignedURLRequest,
    PresignedURLResponse,
    S3CompleteRequest,
)
from app.services import ApiKeyDep
from app.services.apple.apple_xml.aws_service import AWS_BUCKET_NAME
from app.services.apple.apple_xml.presigned_url_service import presigned_url_service

router = APIRouter()


@router.post("/users/{user_id}/import/apple/xml/s3")
def import_xml_presigned_url(
    user_id: str,
    request: PresignedURLRequest,
    _api_key: ApiKeyDep,
) -> PresignedURLResponse:
    """Generate presigned URL for XML file upload."""
    return presigned_url_service.create_presigned_url(user_id, request)


@router.post("/users/{user_id}/import/apple/xml/s3/complete", status_code=status.HTTP_202_ACCEPTED)
def complete_xml_s3_upload(
    user_id: str,
    request: S3CompleteRequest,
    _api_key: ApiKeyDep,
) -> dict[str, str]:
    """Client confirms a presigned S3 upload finished; dispatch processing directly.

    Replaces the S3 -> SNS -> webhook flow, which cannot be configured on Railway and is
    heavy to set up on AWS. The presign step returns the file_key; the client posts it back
    here once the upload to S3 succeeds.
    """
    file_key = request.file_key
    # The presign step always scopes keys to "{user_id}/raw/...", so reject anything that
    # does not belong to this user to prevent triggering processing on arbitrary objects.
    if not file_key.startswith(f"{user_id}/"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="file_key does not belong to this user")

    presigned_url_service.assert_object_exists(file_key)

    task = process_aws_upload.delay(bucket_name=AWS_BUCKET_NAME, object_key=file_key, user_id=user_id)

    return {
        "status": "processing",
        "task_id": task.id,
        "user_id": user_id,
    }


@router.post("/users/{user_id}/import/apple/xml/direct")
def import_xml_file(
    user_id: str,
    file: UploadFile,
    _api_key: ApiKeyDep,
) -> dict[str, str]:
    """Import XML file into the database."""
    file_contents = file.file.read()
    filename = file.filename or "upload.xml"

    task = process_xml_upload.delay(file_contents=file_contents, filename=filename, user_id=user_id)

    return {
        "status": "processing",
        "task_id": task.id,
        "user_id": user_id,
    }
