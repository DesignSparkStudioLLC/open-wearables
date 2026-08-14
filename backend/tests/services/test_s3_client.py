"""Tests for the shared boto3 S3 client factory."""

from unittest.mock import patch

import pytest
from pydantic import SecretStr

from app.config import settings
from app.services.s3_client import create_s3_client


@pytest.fixture
def _with_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "aws_access_key_id", "test-key")
    monkeypatch.setattr(settings, "aws_secret_access_key", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "aws_region", "eu-north-1")


@pytest.mark.usefixtures("_with_credentials")
class TestCreateS3Client:
    def test_endpoint_url_enables_path_style_and_sigv4(self) -> None:
        """A custom endpoint (MinIO) must use path-style addressing + SigV4."""
        with patch("boto3.client") as mock_client:
            create_s3_client("http://minio:9000")

        _, kwargs = mock_client.call_args
        assert kwargs["endpoint_url"] == "http://minio:9000"
        assert kwargs["region_name"] == "eu-north-1"
        assert kwargs["aws_access_key_id"] == "test-key"
        assert kwargs["aws_secret_access_key"] == "test-secret"
        config = kwargs["config"]
        assert config.signature_version == "s3v4"
        assert config.s3["addressing_style"] == "path"

    def test_no_endpoint_uses_defaults(self) -> None:
        """Against AWS S3 (no endpoint), no path-style override is applied."""
        with patch("boto3.client") as mock_client:
            create_s3_client()

        _, kwargs = mock_client.call_args
        assert "endpoint_url" not in kwargs
        assert "config" not in kwargs

    def test_returns_none_on_no_credentials_error(self) -> None:
        from botocore.exceptions import NoCredentialsError

        with patch("boto3.client", side_effect=NoCredentialsError()):
            assert create_s3_client() is None


class TestCreateS3ClientWithoutCredentials:
    def test_missing_credentials_are_omitted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without explicit credentials, boto3's default credential chain is used."""
        monkeypatch.setattr(settings, "aws_access_key_id", None)
        monkeypatch.setattr(settings, "aws_secret_access_key", None)

        with patch("boto3.client") as mock_client:
            create_s3_client()

        _, kwargs = mock_client.call_args
        assert "aws_access_key_id" not in kwargs
        assert "aws_secret_access_key" not in kwargs
