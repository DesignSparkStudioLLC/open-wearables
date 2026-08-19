"""Tests for cleanup of abandoned Apple XML multipart uploads."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.config import settings
from app.integrations.celery.tasks.cleanup_multipart_uploads_task import (
    cleanup_stale_apple_xml_multipart_uploads,
)


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "AbortMultipartUpload")


def _client_with_uploads(uploads: list[dict[str, object]]) -> MagicMock:
    client = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Uploads": uploads}]
    client.get_paginator.return_value = paginator
    return client


class TestCleanupStaleMultipartUploads:
    @patch("app.integrations.celery.tasks.cleanup_multipart_uploads_task.get_s3_client")
    def test_aborts_only_stale_apple_xml_uploads(
        self,
        mock_get_s3_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        mock_celery_app: MagicMock,
    ) -> None:
        monkeypatch.setattr(settings, "aws_bucket_name", "test-bucket")
        monkeypatch.setattr(settings, "apple_xml_multipart_max_age_hours", 48)
        now = datetime.now(UTC)
        stale = {"Key": "user-1/raw/export.xml", "UploadId": "stale", "Initiated": now - timedelta(hours=49)}
        recent = {"Key": "user-2/raw/export.xml", "UploadId": "recent", "Initiated": now - timedelta(hours=1)}
        unrelated = {
            "Key": "raw-payloads/oura/payload.json",
            "UploadId": "other",
            "Initiated": now - timedelta(days=10),
        }
        client = _client_with_uploads([stale, recent, unrelated])
        mock_get_s3_client.return_value = client

        result = cleanup_stale_apple_xml_multipart_uploads()

        assert result == {"status": "completed", "scanned": 2, "aborted": 1, "failed": 0}
        client.abort_multipart_upload.assert_called_once_with(
            Bucket="test-bucket",
            Key="user-1/raw/export.xml",
            UploadId="stale",
        )

    @patch("app.integrations.celery.tasks.cleanup_multipart_uploads_task.get_s3_client", return_value=None)
    def test_skips_when_storage_is_not_configured(
        self,
        mock_get_s3_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
        mock_celery_app: MagicMock,
    ) -> None:
        monkeypatch.setattr(settings, "aws_bucket_name", None)

        result = cleanup_stale_apple_xml_multipart_uploads()

        assert result == {"status": "skipped", "scanned": 0, "aborted": 0, "failed": 0}

    @pytest.mark.parametrize(
        ("error_code", "expected_failed"),
        [("NoSuchUpload", 0), ("AccessDenied", 1)],
    )
    @patch("app.integrations.celery.tasks.cleanup_multipart_uploads_task.get_s3_client")
    def test_handles_abort_races_and_errors(
        self,
        mock_get_s3_client: MagicMock,
        error_code: str,
        expected_failed: int,
        monkeypatch: pytest.MonkeyPatch,
        mock_celery_app: MagicMock,
    ) -> None:
        monkeypatch.setattr(settings, "aws_bucket_name", "test-bucket")
        monkeypatch.setattr(settings, "apple_xml_multipart_max_age_hours", 48)
        client = _client_with_uploads(
            [
                {
                    "Key": "user-1/raw/export.xml",
                    "UploadId": "stale",
                    "Initiated": datetime.now(UTC) - timedelta(hours=49),
                }
            ]
        )
        client.abort_multipart_upload.side_effect = _client_error(error_code)
        mock_get_s3_client.return_value = client

        result = cleanup_stale_apple_xml_multipart_uploads()

        assert result["aborted"] == 0
        assert result["failed"] == expected_failed
