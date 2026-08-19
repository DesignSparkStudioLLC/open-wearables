"""Tests for raw payload storage backends."""

import json
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.config import settings
from app.services import raw_payload_storage
from app.utils import crypto


@pytest.fixture(autouse=True)
def _reset_module_state() -> None:
    """Reset module-level globals before each test."""
    raw_payload_storage._storage_backend = "disabled"
    raw_payload_storage._max_size_bytes = 10 * 1024 * 1024
    raw_payload_storage._s3_bucket = None
    raw_payload_storage._s3_prefix = "raw-payloads"
    raw_payload_storage._s3_client = None


@pytest.fixture(autouse=True)
def _encryption_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default to plaintext so tests don't depend on the developer's DATA_ENCRYPTION_KEY.

    The encryption-specific tests opt in by setting a key themselves.
    """
    monkeypatch.setattr(settings, "data_encryption_key", None)
    crypto.reset_cache()
    yield
    crypto.reset_cache()


class TestConfigure:
    def test_configure_disabled(self) -> None:
        raw_payload_storage.configure("disabled", 1024)
        assert raw_payload_storage._storage_backend == "disabled"

    def test_configure_log(self) -> None:
        raw_payload_storage.configure("log", 2048)
        assert raw_payload_storage._storage_backend == "log"
        assert raw_payload_storage._max_size_bytes == 2048

    def test_configure_s3_without_bucket_falls_back_to_disabled(self) -> None:
        raw_payload_storage.configure("s3", 1024, s3_bucket=None)
        assert raw_payload_storage._storage_backend == "disabled"

    def test_configure_s3_with_bucket(self) -> None:
        mock_client = MagicMock()
        with patch.object(raw_payload_storage, "_create_s3_client", return_value=mock_client):
            raw_payload_storage.configure("s3", 1024, s3_bucket="my-bucket", s3_prefix="payloads")

        assert raw_payload_storage._storage_backend == "s3"
        assert raw_payload_storage._s3_bucket == "my-bucket"
        assert raw_payload_storage._s3_prefix == "payloads"
        assert raw_payload_storage._s3_client is mock_client

    def test_configure_s3_client_creation_fails(self) -> None:
        with patch.object(raw_payload_storage, "_create_s3_client", return_value=None):
            raw_payload_storage.configure("s3", 1024, s3_bucket="my-bucket")

        assert raw_payload_storage._storage_backend == "disabled"


class TestStoreRawPayload:
    def test_disabled_is_noop(self) -> None:
        raw_payload_storage.configure("disabled", 1024)
        # Should not raise
        raw_payload_storage.store_raw_payload(source="webhook", provider="garmin", payload={"key": "val"})

    def test_payload_exceeding_max_size_is_skipped(self, capsys: pytest.CaptureFixture[str]) -> None:
        raw_payload_storage.configure("log", 10)  # 10 bytes max
        raw_payload_storage.store_raw_payload(source="webhook", provider="garmin", payload={"big": "payload"})
        captured = capsys.readouterr()
        assert "raw_payload" not in captured.out

    def test_log_backend_outputs_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        raw_payload_storage.configure("log", 10 * 1024 * 1024)
        raw_payload_storage.store_raw_payload(
            source="webhook",
            provider="garmin",
            payload={"test": True},
            user_id="user-123",
            trace_id="trace-abc",
        )
        captured = capsys.readouterr()
        entry = json.loads(captured.out.strip())
        assert entry["message"] == "raw_payload"
        assert entry["source"] == "webhook"
        assert entry["provider"] == "garmin"
        assert entry["user_id"] == "user-123"
        assert entry["trace_id"] == "trace-abc"

    def test_s3_backend_uploads_payload(self) -> None:
        mock_client = MagicMock()
        mock_client.put_object.return_value = {"ETag": "test-etag"}

        with patch.object(raw_payload_storage, "_create_s3_client", return_value=mock_client):
            raw_payload_storage.configure("s3", 10 * 1024 * 1024, s3_bucket="test-bucket", s3_prefix="raw")

        raw_payload_storage.store_raw_payload(
            source="webhook",
            provider="garmin",
            payload={"activity": "running"},
            user_id="user-456",
            trace_id="trace-xyz",
        )

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert "garmin/webhook/" in call_kwargs["Key"]
        assert "/user-456/" in call_kwargs["Key"]
        assert call_kwargs["Key"].endswith(".json")
        assert call_kwargs["ContentType"] == "application/json"
        assert call_kwargs["Metadata"]["provider"] == "garmin"
        assert call_kwargs["Metadata"]["user_id"] == "user-456"
        assert call_kwargs["Metadata"]["trace_id"] == "trace-xyz"

        body = call_kwargs["Body"].decode("utf-8")
        assert json.loads(body) == {"activity": "running"}

    def test_s3_backend_handles_upload_error(self) -> None:
        mock_client = MagicMock()
        mock_client.put_object.side_effect = Exception("S3 error")

        with patch.object(raw_payload_storage, "_create_s3_client", return_value=mock_client):
            raw_payload_storage.configure("s3", 10 * 1024 * 1024, s3_bucket="test-bucket")

        # Should not raise - errors are logged
        raw_payload_storage.store_raw_payload(source="sdk", provider="apple", payload="raw-xml-data")

    def test_s3_backend_unknown_user_fallback(self) -> None:
        mock_client = MagicMock()
        mock_client.put_object.return_value = {"ETag": "test-etag"}

        with patch.object(raw_payload_storage, "_create_s3_client", return_value=mock_client):
            raw_payload_storage.configure("s3", 10 * 1024 * 1024, s3_bucket="test-bucket")

        raw_payload_storage.store_raw_payload(source="webhook", provider="garmin", payload={"x": 1})

        call_kwargs = mock_client.put_object.call_args[1]
        assert "/_unknown/" in call_kwargs["Key"]

    def test_s3_backend_pre_serialized_string(self) -> None:
        mock_client = MagicMock()
        mock_client.put_object.return_value = {"ETag": "test-etag"}

        with patch.object(raw_payload_storage, "_create_s3_client", return_value=mock_client):
            raw_payload_storage.configure("s3", 10 * 1024 * 1024, s3_bucket="test-bucket")

        raw_payload_storage.store_raw_payload(source="sdk", provider="apple", payload='{"pre":"serialized"}')

        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Body"] == b'{"pre":"serialized"}'

    def test_s3_backend_applies_server_side_encryption(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "aws_sse_algorithm", "AES256")
        mock_client = MagicMock()
        mock_client.put_object.return_value = {"ETag": "test-etag"}

        with patch.object(raw_payload_storage, "_create_s3_client", return_value=mock_client):
            raw_payload_storage.configure("s3", 10 * 1024 * 1024, s3_bucket="test-bucket")

        raw_payload_storage.store_raw_payload(source="webhook", provider="garmin", payload={"x": 1})

        assert mock_client.put_object.call_args[1]["ServerSideEncryption"] == "AES256"


class TestRawPayloadEncryption:
    @pytest.fixture(autouse=True)
    def _reset_cipher(self) -> None:
        crypto.reset_cache()
        yield
        crypto.reset_cache()

    def test_payload_is_encrypted_when_key_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "data_encryption_key", SecretStr(Fernet.generate_key().decode()))
        crypto.reset_cache()

        mock_client = MagicMock()
        mock_client.put_object.return_value = {"ETag": "test-etag"}
        with patch.object(raw_payload_storage, "_create_s3_client", return_value=mock_client):
            raw_payload_storage.configure("s3", 10 * 1024 * 1024, s3_bucket="test-bucket")

        raw_payload_storage.store_raw_payload(source="sdk", provider="apple", payload={"activity": "running"})

        call_kwargs = mock_client.put_object.call_args[1]
        # Body is ciphertext, not the plaintext JSON...
        assert call_kwargs["Body"] != b'{"activity": "running"}'
        assert call_kwargs["ContentType"] == "application/octet-stream"
        assert call_kwargs["Metadata"]["encryption"] == "fernet"
        assert call_kwargs["Metadata"]["original_content_type"] == "application/json"
        # ...that round-trips back to the original payload.
        assert json.loads(crypto.decrypt(call_kwargs["Body"])) == {"activity": "running"}

    def test_fit_file_is_encrypted_when_key_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "data_encryption_key", SecretStr(Fernet.generate_key().decode()))
        crypto.reset_cache()

        mock_client = MagicMock()
        mock_client.put_object.return_value = {"ETag": "test-etag"}
        with patch.object(raw_payload_storage, "_create_s3_client", return_value=mock_client):
            raw_payload_storage.configure("disabled", 10 * 1024 * 1024, s3_bucket="test-bucket", fit_files_enabled=True)

        raw_payload_storage.store_fit_file(
            provider="garmin", fit_bytes=b"\x0e\x10FITbinary", user_id="user-1", activity_id="act-1"
        )

        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Body"] != b"\x0e\x10FITbinary"
        assert call_kwargs["Metadata"]["encryption"] == "fernet"
        assert crypto.decrypt(call_kwargs["Body"]) == b"\x0e\x10FITbinary"

    def test_invalid_runtime_key_never_falls_back_to_plaintext(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "data_encryption_key", SecretStr("invalid"))
        crypto.reset_cache()

        mock_client = MagicMock()
        with patch.object(raw_payload_storage, "_create_s3_client", return_value=mock_client):
            raw_payload_storage.configure("s3", 10 * 1024 * 1024, s3_bucket="test-bucket")

        raw_payload_storage.store_raw_payload(source="sdk", provider="apple", payload={"sensitive": True})

        mock_client.put_object.assert_not_called()

    def test_invalid_runtime_key_never_stores_plaintext_fit_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "data_encryption_key", SecretStr("invalid"))
        crypto.reset_cache()

        mock_client = MagicMock()
        with patch.object(raw_payload_storage, "_create_s3_client", return_value=mock_client):
            raw_payload_storage.configure("disabled", 1024, s3_bucket="test-bucket", fit_files_enabled=True)

        raw_payload_storage.store_fit_file(
            provider="garmin", fit_bytes=b"sensitive-fit", user_id="user-1", activity_id="activity-1"
        )

        mock_client.put_object.assert_not_called()
