import json
from json import JSONDecodeError

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from pydantic import ValidationError

from app.config import settings
from app.integrations.celery.tasks.process_aws_upload_task import process_aws_upload
from app.integrations.celery.tasks.process_xml_upload_task import process_xml_upload
from app.schemas.providers.apple.apple_xml import (
    MultipartAbortRequest,
    MultipartCompleteRequest,
    MultipartCompleteResponse,
    MultipartCreateRequest,
    MultipartCreateResponse,
    MultipartSignRequest,
    MultipartSignResponse,
    PresignedURLRequest,
    PresignedURLResponse,
    SNSNotification,
)
from app.schemas.responses.upload import UploadDataResponse
from app.services import ApiKeyDep
from app.services.apple.apple_xml.aws_service import AWS_BUCKET_NAME
from app.services.apple.apple_xml.multipart_upload_service import multipart_upload_service
from app.services.apple.apple_xml.presigned_url_service import presigned_url_service
from app.services.apple.apple_xml.sns_service import sns_service

router = APIRouter()


@router.post("/users/{user_id}/import/apple/xml/s3")
def import_xml_presigned_url(
    user_id: str,
    request: PresignedURLRequest,
    _api_key: ApiKeyDep,
) -> PresignedURLResponse:
    """Generate presigned URL for XML file upload and trigger processing task."""
    return presigned_url_service.create_presigned_url(user_id, request)


@router.post("/users/{user_id}/import/apple/xml/s3/multipart/create")
def create_multipart_upload(
    user_id: str,
    request: MultipartCreateRequest,
    _api_key: ApiKeyDep,
) -> MultipartCreateResponse:
    """Start a multipart upload for a (potentially very large) XML file to S3/MinIO."""
    return multipart_upload_service.create(
        user_id=user_id,
        filename=request.filename,
        content_type=request.content_type,
        file_size=request.file_size,
    )


@router.post("/users/{user_id}/import/apple/xml/s3/multipart/sign")
def sign_multipart_parts(
    user_id: str,
    request: MultipartSignRequest,
    _api_key: ApiKeyDep,
) -> MultipartSignResponse:
    """Presign upload URLs for a batch of parts of an in-progress multipart upload."""
    return multipart_upload_service.sign_parts(
        user_id=user_id,
        key=request.key,
        upload_id=request.upload_id,
        part_numbers=request.part_numbers,
        expiration_seconds=request.expiration_seconds,
    )


@router.post("/users/{user_id}/import/apple/xml/s3/multipart/complete")
def complete_multipart_upload(
    user_id: str,
    request: MultipartCompleteRequest,
    _api_key: ApiKeyDep,
) -> MultipartCompleteResponse:
    """Finalize a multipart upload and, in client-driven mode, dispatch processing.

    When ``APPLE_XML_UPLOAD_COMPLETION_MODE`` is ``"sns"`` the import task is instead
    triggered by the S3 bucket event, so this endpoint only finalizes the object.
    """
    key = multipart_upload_service.complete(
        user_id=user_id,
        key=request.key,
        upload_id=request.upload_id,
        parts=request.parts,
    )

    task_id: str | None = None
    if settings.apple_xml_upload_completion_mode == "client":
        task = process_aws_upload.delay(
            bucket_name=AWS_BUCKET_NAME,
            object_key=key,
            user_id=user_id,
        )
        task_id = task.id

    return MultipartCompleteResponse(
        status="processing" if task_id else "uploaded",
        key=key,
        bucket=AWS_BUCKET_NAME,  # ty:ignore[invalid-argument-type]
        task_id=task_id,
    )


@router.post("/users/{user_id}/import/apple/xml/s3/multipart/abort")
def abort_multipart_upload(
    user_id: str,
    request: MultipartAbortRequest,
    _api_key: ApiKeyDep,
) -> dict[str, str]:
    """Abort an incomplete multipart upload and discard its parts."""
    multipart_upload_service.abort(user_id=user_id, key=request.key, upload_id=request.upload_id)
    return {"status": "aborted", "key": request.key}


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


@router.post("/sns/notification", status_code=status.HTTP_202_ACCEPTED)
async def receive_sns_notification(
    request: Request,
) -> UploadDataResponse:
    """Handle all SNS messages (subscription confirmation + S3 upload notifications)."""
    body = await request.body()
    try:
        notification = SNSNotification.model_validate(json.loads(body))
    except (ValidationError, JSONDecodeError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    result = await sns_service.handle_sns_notification(notification)

    if result.status_code not in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED):
        raise HTTPException(status_code=result.status_code, detail=result.response)
    return result
