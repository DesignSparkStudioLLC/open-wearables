"""Tests for application-level payload encryption (app/utils/crypto.py)."""

import pytest
from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr, ValidationError

from app.config import Settings, settings
from app.utils import crypto


@pytest.fixture(autouse=True)
def _reset_cipher_cache() -> None:
    """The cipher is process-cached; clear it around every test."""
    crypto.reset_cache()
    yield
    crypto.reset_cache()


def _set_key(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    monkeypatch.setattr(settings, "data_encryption_key", SecretStr(value) if value is not None else None)
    crypto.reset_cache()


class TestDisabled:
    def test_no_key_is_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_key(monkeypatch, None)
        assert crypto.is_enabled() is False

    def test_empty_key_is_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_key(monkeypatch, "   ")
        assert crypto.is_enabled() is False

    def test_encrypt_decrypt_are_noops_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_key(monkeypatch, None)
        assert crypto.encrypt(b"hello") == b"hello"
        assert crypto.decrypt(b"hello") == b"hello"

    def test_invalid_runtime_key_raises_instead_of_disabling_encryption(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_key(monkeypatch, "not-a-valid-fernet-key")
        with pytest.raises(ValueError, match="invalid Fernet key"):
            crypto.is_enabled()

    @pytest.mark.parametrize("configured", ["invalid", f"{Fernet.generate_key().decode()},"])
    def test_invalid_configured_key_fails_settings_validation(self, configured: str) -> None:
        with pytest.raises(ValidationError, match="DATA_ENCRYPTION_KEY"):
            Settings(_env_file=None, secret_key="test-secret", data_encryption_key=SecretStr(configured))


class TestRoundTrip:
    def test_encrypt_then_decrypt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_key(monkeypatch, Fernet.generate_key().decode())
        plaintext = b'{"heart_rate": 72}'

        token = crypto.encrypt(plaintext)

        assert token != plaintext  # actually encrypted
        assert crypto.decrypt(token) == plaintext

    def test_tampered_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_key(monkeypatch, Fernet.generate_key().decode())
        assert crypto.is_enabled() is True

        with pytest.raises(InvalidToken):
            crypto.decrypt(b"garbage-not-a-token")


class TestKeyRotation:
    def test_old_tokens_decrypt_after_rotation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        old_key = Fernet.generate_key().decode()
        new_key = Fernet.generate_key().decode()

        _set_key(monkeypatch, old_key)
        token = crypto.encrypt(b"payload")

        # Rotate: new key first (encrypts), old key retained (still decrypts).
        _set_key(monkeypatch, f"{new_key},{old_key}")
        assert crypto.decrypt(token) == b"payload"

        # Fresh writes use the new primary key and still round-trip.
        assert crypto.decrypt(crypto.encrypt(b"payload2")) == b"payload2"
