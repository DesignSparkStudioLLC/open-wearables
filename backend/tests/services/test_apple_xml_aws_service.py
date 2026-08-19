"""Tests for Apple XML object-store configuration helpers."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app.config import settings
from app.services.apple.apple_xml.aws_service import (
    build_object_key,
    get_public_s3_client,
    get_s3_client,
    require_bucket_name,
)


def test_build_object_key_is_unique_for_same_user_and_filename() -> None:
    first = build_object_key("user-1", "export.xml")
    second = build_object_key("user-1", "export.xml")

    assert first != second
    assert first.startswith("user-1/raw/")
    assert first.endswith("-export.xml")


def test_build_object_key_sanitizes_filename() -> None:
    key = build_object_key("user-1", "../Apple Health/export.xml")

    assert key.startswith("user-1/raw/")
    assert "/Apple" not in key
    assert key.endswith("-..AppleHealthexport.xml")


@pytest.fixture(autouse=True)
def _clear_s3_client_caches() -> Generator[None, None, None]:
    get_s3_client.cache_clear()
    get_public_s3_client.cache_clear()
    yield
    get_s3_client.cache_clear()
    get_public_s3_client.cache_clear()


@pytest.fixture
def _with_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "aws_access_key_id", "test-key")
    monkeypatch.setattr(settings, "aws_secret_access_key", SecretStr("test-secret"))


def test_require_bucket_name_returns_configured_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "aws_bucket_name", "apple-xml")

    assert require_bucket_name() == "apple-xml"


def test_require_bucket_name_rejects_missing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "aws_bucket_name", None)

    with pytest.raises(HTTPException) as exc:
        require_bucket_name()

    assert exc.value.status_code == 503
    assert exc.value.detail == "S3 bucket not configured"


@pytest.mark.usefixtures("_with_credentials")
def test_internal_s3_client_is_created_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "aws_endpoint_url", "http://seaweedfs:8333")
    client = MagicMock()

    with patch("app.services.apple.apple_xml.aws_service.create_s3_client", return_value=client) as create_client:
        assert get_s3_client() is client
        assert get_s3_client() is client

    create_client.assert_called_once_with("http://seaweedfs:8333")


@pytest.mark.usefixtures("_with_credentials")
def test_public_s3_client_is_cached_separately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "aws_endpoint_url", "http://seaweedfs:8333")
    monkeypatch.setattr(settings, "aws_public_endpoint_url", "http://localhost:8333")
    public_client = MagicMock()

    with patch(
        "app.services.apple.apple_xml.aws_service.create_s3_client",
        return_value=public_client,
    ) as create_client:
        assert get_public_s3_client() is public_client
        assert get_public_s3_client() is public_client

    create_client.assert_called_once_with("http://localhost:8333")
