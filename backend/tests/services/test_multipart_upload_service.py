"""Tests for the Apple XML multipart upload service."""

from logging import getLogger
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from app.schemas.providers.apple.apple_xml import CompletedPart
from app.services.apple.apple_xml.multipart_upload_service import MultipartUploadService

USER_ID = "user-123"


def _service(client: MagicMock | None) -> MultipartUploadService:
    service = MultipartUploadService(getLogger(__name__))
    service.s3_client = client
    return service


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "Operation")


class TestCreate:
    def test_create_returns_upload_metadata(self) -> None:
        client = MagicMock()
        client.create_multipart_upload.return_value = {"UploadId": "upload-1"}
        service = _service(client)

        result = service.create(USER_ID, "export.xml", "application/xml", file_size=50 * 1024 * 1024)

        assert result.upload_id == "upload-1"
        assert result.key.startswith(f"{USER_ID}/raw/")
        assert result.bucket == "test-bucket"
        assert result.part_size > 0
        client.create_multipart_upload.assert_called_once()

    def test_create_without_client_raises_503(self) -> None:
        service = _service(None)
        with pytest.raises(HTTPException) as exc:
            service.create(USER_ID, "export.xml", "application/xml", file_size=1024 * 1024 * 5)
        assert exc.value.status_code == 503

    def test_create_client_error_raises_500(self) -> None:
        client = MagicMock()
        client.create_multipart_upload.side_effect = _client_error("InternalError")
        service = _service(client)
        with pytest.raises(HTTPException) as exc:
            service.create(USER_ID, "export.xml", "application/xml", file_size=1024 * 1024 * 5)
        assert exc.value.status_code == 500


class TestSignParts:
    def test_sign_parts_returns_one_url_per_part(self) -> None:
        client = MagicMock()
        client.generate_presigned_url.side_effect = ["url-1", "url-2", "url-3"]
        service = _service(client)
        key = f"{USER_ID}/raw/export.xml"

        result = service.sign_parts(USER_ID, key, "upload-1", [1, 2, 3], expiration_seconds=3600)

        assert [p.part_number for p in result.urls] == [1, 2, 3]
        assert [p.url for p in result.urls] == ["url-1", "url-2", "url-3"]
        assert client.generate_presigned_url.call_count == 3

    def test_sign_parts_rejects_foreign_key(self) -> None:
        service = _service(MagicMock())
        with pytest.raises(HTTPException) as exc:
            service.sign_parts(USER_ID, "other-user/raw/x.xml", "upload-1", [1], expiration_seconds=3600)
        assert exc.value.status_code == 403


class TestComplete:
    def test_complete_sorts_parts_and_returns_key(self) -> None:
        client = MagicMock()
        service = _service(client)
        key = f"{USER_ID}/raw/export.xml"
        parts = [
            CompletedPart(part_number=2, etag="etag-2"),
            CompletedPart(part_number=1, etag="etag-1"),
        ]

        returned_key = service.complete(USER_ID, key, "upload-1", parts)

        assert returned_key == key
        _, kwargs = client.complete_multipart_upload.call_args
        sent_parts = kwargs["MultipartUpload"]["Parts"]
        assert [p["PartNumber"] for p in sent_parts] == [1, 2]

    def test_complete_rejects_foreign_key(self) -> None:
        service = _service(MagicMock())
        with pytest.raises(HTTPException) as exc:
            service.complete(USER_ID, "other/raw/x.xml", "upload-1", [CompletedPart(part_number=1, etag="e")])
        assert exc.value.status_code == 403

    def test_complete_client_error_raises_500(self) -> None:
        client = MagicMock()
        client.complete_multipart_upload.side_effect = _client_error("NoSuchUpload")
        service = _service(client)
        key = f"{USER_ID}/raw/export.xml"
        with pytest.raises(HTTPException) as exc:
            service.complete(USER_ID, key, "upload-1", [CompletedPart(part_number=1, etag="e")])
        assert exc.value.status_code == 500


class TestAbort:
    def test_abort_calls_s3(self) -> None:
        client = MagicMock()
        service = _service(client)
        key = f"{USER_ID}/raw/export.xml"

        service.abort(USER_ID, key, "upload-1")

        client.abort_multipart_upload.assert_called_once_with(Bucket="test-bucket", Key=key, UploadId="upload-1")

    def test_abort_rejects_foreign_key(self) -> None:
        service = _service(MagicMock())
        with pytest.raises(HTTPException) as exc:
            service.abort(USER_ID, "other/raw/x.xml", "upload-1")
        assert exc.value.status_code == 403
