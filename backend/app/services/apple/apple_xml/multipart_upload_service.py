"""Service for S3 / MinIO multipart uploads of Apple Health XML exports.

Drives the four multipart phases from the backend so the browser only needs the
presigned per-part URLs:

    create  -> open a multipart upload, hand back the object key + a recommended part size
    sign    -> presign an ``upload_part`` URL for each requested part number
    complete-> assemble the parts into the final object
    abort   -> discard an incomplete upload and its parts

Object keys are always namespaced under ``<user_id>/raw/``; every call verifies the
key belongs to the requesting user so one user cannot touch another's upload.
"""

from logging import Logger, getLogger

from botocore.exceptions import ClientError
from fastapi import HTTPException, status

from app.schemas.providers.apple.apple_xml import (
    CompletedPart,
    MultipartCreateResponse,
    MultipartSignResponse,
    SignedPart,
    recommended_part_size,
)
from app.services.apple.apple_xml.aws_service import AWS_BUCKET_NAME, build_object_key, get_s3_client


class MultipartUploadService:
    def __init__(self, log: Logger) -> None:
        self.log = log
        self.s3_client = get_s3_client()

    def _require_client(self):  # noqa: ANN202
        if not self.s3_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="S3 client not configured",
            )
        return self.s3_client

    @staticmethod
    def _verify_owner(user_id: str, key: str) -> None:
        """Reject keys that don't belong to the requesting user."""
        if not key.startswith(f"{user_id}/"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Object key does not belong to this user",
            )

    def create(self, user_id: str, filename: str, content_type: str, file_size: int) -> MultipartCreateResponse:
        client = self._require_client()
        key = build_object_key(user_id, filename or None)

        try:
            response = client.create_multipart_upload(
                Bucket=AWS_BUCKET_NAME,
                Key=key,
                ContentType=content_type,
            )
        except ClientError as e:
            raise self._client_error(e, "Failed to create multipart upload") from e

        self.log.debug(f"Created multipart upload {response['UploadId']} for {key}")
        return MultipartCreateResponse(
            upload_id=response["UploadId"],
            key=key,
            bucket=AWS_BUCKET_NAME,  # ty:ignore[invalid-argument-type]
            part_size=recommended_part_size(file_size),
        )

    def sign_parts(
        self,
        user_id: str,
        key: str,
        upload_id: str,
        part_numbers: list[int],
        expiration_seconds: int,
    ) -> MultipartSignResponse:
        client = self._require_client()
        self._verify_owner(user_id, key)

        urls: list[SignedPart] = []
        for part_number in part_numbers:
            try:
                url = client.generate_presigned_url(
                    "upload_part",
                    Params={
                        "Bucket": AWS_BUCKET_NAME,
                        "Key": key,
                        "UploadId": upload_id,
                        "PartNumber": part_number,
                    },
                    ExpiresIn=expiration_seconds,
                )
            except ClientError as e:
                raise self._client_error(e, "Failed to sign upload part") from e
            urls.append(SignedPart(part_number=part_number, url=url))

        return MultipartSignResponse(urls=urls)

    def complete(self, user_id: str, key: str, upload_id: str, parts: list[CompletedPart]) -> str:
        """Complete the upload and return the finalized object key."""
        client = self._require_client()
        self._verify_owner(user_id, key)

        ordered = sorted(parts, key=lambda p: p.part_number)
        multipart_parts = [{"ETag": part.etag, "PartNumber": part.part_number} for part in ordered]

        try:
            client.complete_multipart_upload(
                Bucket=AWS_BUCKET_NAME,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": multipart_parts},
            )
        except ClientError as e:
            raise self._client_error(e, "Failed to complete multipart upload") from e

        self.log.debug(f"Completed multipart upload {upload_id} for {key}")
        return key

    def abort(self, user_id: str, key: str, upload_id: str) -> None:
        client = self._require_client()
        self._verify_owner(user_id, key)

        try:
            client.abort_multipart_upload(Bucket=AWS_BUCKET_NAME, Key=key, UploadId=upload_id)
        except ClientError as e:
            raise self._client_error(e, "Failed to abort multipart upload") from e

        self.log.debug(f"Aborted multipart upload {upload_id} for {key}")

    @staticmethod
    def _client_error(error: ClientError, message: str) -> HTTPException:
        error_code = error.response["Error"]["Code"]
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{message}: {error_code}",
        )


multipart_upload_service = MultipartUploadService(getLogger(__name__))
