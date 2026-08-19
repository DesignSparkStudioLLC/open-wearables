"""Tests for the shared boto3 S3 client factory."""

import json
from unittest.mock import patch

import pytest
from botocore.exceptions import NoCredentialsError
from pydantic import SecretStr, ValidationError

from app.config import Settings, settings
from app.services.s3_client import create_s3_client, sse_post_fields, sse_put_kwargs


@pytest.fixture
def _with_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "aws_access_key_id", "test-key")
    monkeypatch.setattr(settings, "aws_secret_access_key", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "aws_region", "eu-north-1")
    monkeypatch.setattr(settings, "aws_endpoint_url", None)


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

    def test_shared_endpoint_is_used_when_no_override_is_passed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "aws_endpoint_url", "http://seaweedfs:8333")

        with patch("boto3.client") as mock_client:
            create_s3_client()

        _, kwargs = mock_client.call_args
        assert kwargs["endpoint_url"] == "http://seaweedfs:8333"
        assert kwargs["config"].s3["addressing_style"] == "path"

    def test_explicit_endpoint_overrides_shared_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "aws_endpoint_url", "http://seaweedfs:8333")

        with patch("boto3.client") as mock_client:
            create_s3_client("http://other-storage:9000")

        _, kwargs = mock_client.call_args
        assert kwargs["endpoint_url"] == "http://other-storage:9000"

    def test_returns_none_on_no_credentials_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("boto3.client", side_effect=NoCredentialsError()):
            assert create_s3_client() is None

        log_entry = json.loads(capsys.readouterr().out)
        assert log_entry["level"] == "warning"
        assert log_entry["message"] == "Cannot create S3 client"
        assert log_entry["error_type"] == "NoCredentialsError"


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


class TestServerSideEncryption:
    def test_settings_default_is_upgrade_safe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AWS_SSE_ALGORITHM", raising=False)
        configured_settings = Settings(_env_file=None, secret_key="test-secret")

        assert configured_settings.aws_sse_algorithm is None

    def test_aes256_fields_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "aws_sse_algorithm", "AES256")
        assert sse_put_kwargs() == {"ServerSideEncryption": "AES256"}
        assert sse_post_fields() == {"x-amz-server-side-encryption": "AES256"}

    def test_kms_includes_key_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "aws_sse_algorithm", "aws:kms")
        monkeypatch.setattr(settings, "aws_sse_kms_key_id", "key-123")

        assert sse_put_kwargs() == {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": "key-123"}
        fields = sse_post_fields()
        assert fields["x-amz-server-side-encryption"] == "aws:kms"
        assert fields["x-amz-server-side-encryption-aws-kms-key-id"] == "key-123"

    @pytest.mark.parametrize("value", ["", "  ", "none", "NONE", None])
    def test_disabled_returns_empty(self, monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
        monkeypatch.setattr(settings, "aws_sse_algorithm", value)
        assert sse_put_kwargs() == {}
        assert sse_post_fields() == {}

    @pytest.mark.parametrize(
        ("configured", "expected"),
        [("aes256", "AES256"), ("AWS:KMS", "aws:kms"), ("none", None), ("", None)],
    )
    def test_settings_normalizes_supported_values(self, configured: str, expected: str | None) -> None:
        configured_settings = Settings(
            _env_file=None,
            secret_key="test-secret",
            aws_sse_algorithm=configured,  # ty:ignore[invalid-argument-type]
        )

        assert configured_settings.aws_sse_algorithm == expected

    def test_settings_rejects_unknown_algorithm(self) -> None:
        with pytest.raises(ValidationError, match="AWS_SSE_ALGORITHM"):
            Settings(
                _env_file=None,
                secret_key="test-secret",
                aws_sse_algorithm="invalid",  # ty:ignore[invalid-argument-type]
            )
