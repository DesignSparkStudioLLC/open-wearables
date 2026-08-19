"""Tests for the Apple XML presigned-POST service, focused on SSE enforcement."""

from logging import getLogger
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.config import settings
from app.schemas.providers.apple.apple_xml import PresignedURLRequest
from app.services.apple.apple_xml.presigned_url_service import PresignedURLService


def _service(client: MagicMock) -> PresignedURLService:
    service = PresignedURLService(getLogger(__name__))
    service.s3_client = client
    # Same object for the presigning client by default, so single-client assertions hold.
    service.public_s3_client = client
    return service


def _client() -> MagicMock:
    client = MagicMock()
    client.head_bucket.return_value = {}
    client.generate_presigned_post.return_value = {"url": "https://storage/bucket", "fields": {}}
    return client


class TestPresignedPostSSE:
    def test_sse_added_to_fields_and_conditions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "aws_sse_algorithm", "AES256")
        client = _client()

        _service(client).create_presigned_url("user-1", PresignedURLRequest(filename="export.xml"))

        kwargs = client.generate_presigned_post.call_args[1]
        assert kwargs["Fields"]["x-amz-server-side-encryption"] == "AES256"
        assert {"x-amz-server-side-encryption": "AES256"} in kwargs["Conditions"]

    def test_no_sse_fields_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "aws_sse_algorithm", "")
        client = _client()

        _service(client).create_presigned_url("user-1", PresignedURLRequest(filename="export.xml"))

        kwargs = client.generate_presigned_post.call_args[1]
        assert "x-amz-server-side-encryption" not in kwargs["Fields"]
        dict_conditions = [cond for cond in kwargs["Conditions"] if isinstance(cond, dict)]
        assert all("x-amz-server-side-encryption" not in cond for cond in dict_conditions)

    def test_kms_key_is_pinned_in_fields_and_policy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "aws_sse_algorithm", "aws:kms")
        monkeypatch.setattr(settings, "aws_sse_kms_key_id", "key-123")
        client = _client()

        _service(client).create_presigned_url("user-1", PresignedURLRequest(filename="export.xml"))

        kwargs = client.generate_presigned_post.call_args[1]
        expected = {"x-amz-server-side-encryption-aws-kms-key-id": "key-123"}
        assert kwargs["Fields"]["x-amz-server-side-encryption-aws-kms-key-id"] == "key-123"
        assert expected in kwargs["Conditions"]


class TestPublicEndpoint:
    """The presigned form must come from the browser-facing (public) client, while bucket
    validation (head_bucket) uses the internal client."""

    def test_presign_uses_public_client_and_validates_via_internal(self) -> None:
        internal = MagicMock()
        internal.head_bucket.return_value = {}
        public = MagicMock()
        public.generate_presigned_post.return_value = {"url": "http://localhost:8333/bucket", "fields": {}}

        service = PresignedURLService(getLogger(__name__))
        service.s3_client = internal
        service.public_s3_client = public

        service.create_presigned_url("user-1", PresignedURLRequest(filename="export.xml"))

        internal.head_bucket.assert_called_once()
        public.generate_presigned_post.assert_called_once()
        internal.generate_presigned_post.assert_not_called()

    def test_missing_public_client_falls_back_to_internal(self) -> None:
        internal = _client()
        service = _service(internal)
        service.public_s3_client = None

        service.create_presigned_url("user-1", PresignedURLRequest(filename="export.xml"))

        internal.generate_presigned_post.assert_called_once()


def test_missing_bucket_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "aws_bucket_name", None)
    client = _client()

    with pytest.raises(HTTPException) as exc:
        _service(client).create_presigned_url("user-1", PresignedURLRequest(filename="export.xml"))

    assert exc.value.status_code == 503
    assert exc.value.detail == "S3 bucket not configured"
    client.head_bucket.assert_not_called()
